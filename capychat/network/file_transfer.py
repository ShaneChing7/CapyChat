"""文件传输管理器：分块传输、压缩、进度追踪、多文件队列、取消。

从 tcp_p2p.py 抽离，负责所有文件传输业务逻辑，通过 send_callback 解耦 socket 操作。
"""

import json
import os
import struct
import threading
import time
import hashlib
import zlib
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal

from .protocol import (
    TCP_CHUNK_SIZE,
    MSG_FILE_TRANSFER_REQUEST, MSG_FILE_TRANSFER_RESPONSE,
    MSG_FILE_CHUNK, MSG_FILE_COMPLETE, MSG_FILE_CANCEL,
    build_tcp_message,
)


# =============================================================================
# 压缩支持
# =============================================================================

COMPRESSION_THRESHOLD = 512  # 小于此字节数的 chunk 不压缩（压缩收益低）


def compress_chunk(data: bytes, level: int = 6) -> tuple:
    """压缩数据块。返回 (output_data, was_compressed)。"""
    if len(data) < COMPRESSION_THRESHOLD:
        return data, False
    try:
        compressed = zlib.compress(data, level)
        if len(compressed) < len(data):
            return compressed, True
    except Exception:
        pass
    return data, False


def decompress_chunk(data: bytes, compressed: bool) -> bytes:
    """按需解压数据块。"""
    if not compressed:
        return data
    return zlib.decompress(data)


# =============================================================================
# 数据类
# =============================================================================

@dataclass
class FileTransfer:
    """传输中的文件状态（接收端和发送端共用）。"""
    file_id: str
    file_name: str
    file_size: int
    file_ext: str
    total_chunks: int
    sender: str
    peer_addr: str = ""
    compressed: bool = False
    received_bytes: int = 0
    start_time: float = field(default_factory=time.time)
    chunk_times: list = field(default_factory=list)
    cancelled: bool = False


@dataclass
class QueuedFile:
    """多文件队列中的待发送项。"""
    file_id: str
    addr: str           # "ip:port"
    file_path: str      # 本地路径
    file_name: str
    file_size: int
    status: str = "waiting"   # waiting | sending | done | cancelled | error
    error_msg: str = ""


class TransferProgress:
    """传输进度快照，通过 Signal 发送到 UI 层。

    注意：不使用 __slots__，因为 PySide6 跨线程信号传参需要 __dict__。
    """
    # 字段: file_id, file_name, file_size, received_bytes, speed,
    #       eta_seconds, done, cancelled, error_msg, compressed, direction

    def __init__(self, file_id="", file_name="", file_size=0,
                 received_bytes=0, speed=0.0, eta_seconds=-1.0,
                 done=False, cancelled=False, error_msg="",
                 compressed=False, direction="download"):
        self.file_id = file_id
        self.file_name = file_name
        self.file_size = file_size
        self.received_bytes = received_bytes
        self.speed = speed
        self.eta_seconds = eta_seconds
        self.done = done
        self.cancelled = cancelled
        self.error_msg = error_msg
        self.compressed = compressed
        self.direction = direction


# =============================================================================
# 工具函数
# =============================================================================

def make_file_id(filename: str, size: int) -> str:
    raw = f"{filename}_{size}_{time.time()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def build_file_chunk(file_id: str, chunk_index: int, total: int,
                     data: bytes, compressed: bool = False) -> bytes:
    """构建文件块消息帧：[4字节头长度][JSON头][二进制数据]"""
    header = json.dumps({
        "type": MSG_FILE_CHUNK,
        "file_id": file_id,
        "chunk_index": chunk_index,
        "total_chunks": total,
        "data_size": len(data),
        "compressed": compressed,
    }, ensure_ascii=False).encode()
    return struct.pack("!I", len(header)) + header + data


# =============================================================================
# FileTransferManager
# =============================================================================

class FileTransferManager(QObject):
    """文件传输管理器。

    职责：发送/接收文件、分块传输、压缩、进度追踪、多文件队列、取消。

    通过 send_callback 与 socket 层解耦——manager 只管"发什么数据"，
    不管"怎么发"，由外层（TcpP2P）提供实际发送能力。
    """

    # --- 信号（与 TcpP2P 兼容，由 TcpP2P 转发给 UI）---
    file_request = Signal(str, str, str, int, str, int, str)
    # file_id, sender, sender_ip, sender_port, file_name, file_size, file_ext
    file_progress = Signal(object)           # TransferProgress
    file_received = Signal(str, str, str)     # file_id, file_path, file_name
    file_sent = Signal(str, str)              # file_id, file_name
    file_cancelled = Signal(str)              # file_id

    def __init__(self, recv_dir: str,
                 send_callback: Callable[[str, bytes], bool],
                 sender_name: str = "",
                 sender_port: int = 0,
                 encryption_key: Optional[bytes] = None):
        """
        Args:
            recv_dir: 接收文件的保存目录。
            send_callback: 发送回调，签名 (peer_addr, data) -> bool。
            sender_name: 发送者的用户名（填入文件请求中）。
            sender_port: 发送者的 TCP 监听端口（填入文件请求中）。
            encryption_key: AES-256 密钥（可选，用于加密控制消息）。
        """
        super().__init__()
        self._send = send_callback
        self._recv_dir = recv_dir
        self._sender_name = sender_name
        self._sender_port = sender_port
        self._key = encryption_key
        os.makedirs(self._recv_dir, exist_ok=True)

        # --- 传输状态 ---
        self._active_transfer: Optional[FileTransfer] = None
        self._pending_requests: dict[str, FileTransfer] = {}  # 等待用户决策的请求
        self._waiting_response: set[str] = set()              # 等待对方回应的发送
        self._transfer_queue: deque[QueuedFile] = deque()
        self._lock = threading.Lock()

        # --- 压缩设置 ---
        self.compression_enabled = True
        self.compression_level = 6

    # ==================================================================
    # 公共 API — 发送端
    # ==================================================================

    def send_file(self, peer_addr: str, file_path: str) -> Optional[str]:
        """发送单个文件。返回 file_id，失败返回 None。"""
        if not os.path.exists(file_path):
            return None

        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        _, ext = os.path.splitext(file_name)
        file_id = make_file_id(file_name, file_size)
        total_chunks = max(1, (file_size + TCP_CHUNK_SIZE - 1) // TCP_CHUNK_SIZE)

        qf = QueuedFile(
            file_id=file_id, addr=peer_addr, file_path=file_path,
            file_name=file_name, file_size=file_size, status="sending")

        with self._lock:
            self._transfer_queue.append(qf)
            if self._active_transfer is None:
                self._active_transfer = FileTransfer(
                    file_id=file_id, file_name=file_name, file_size=file_size,
                    file_ext=ext, total_chunks=total_chunks, sender="",
                    peer_addr=peer_addr, compressed=self.compression_enabled)
            self._waiting_response.add(file_id)

        # 发送请求（不立即传数据，等对方 accept）
        ok = self._send(peer_addr, build_tcp_message(MSG_FILE_TRANSFER_REQUEST, key=self._key,
            file_id=file_id, file_name=file_name, file_size=file_size,
            file_ext=ext, total_chunks=total_chunks, sender=self._sender_name,
            sender_port=self._sender_port,
            compressed=self.compression_enabled))
        if not ok:
            with self._lock:
                qf.status = "error"
                qf.error_msg = "发送请求失败"
                self._waiting_response.discard(file_id)
                if self._active_transfer and self._active_transfer.file_id == file_id:
                    self._active_transfer = None
            return None

        return file_id

    def send_files(self, peer_addr: str, file_paths: list[str]):
        """发送多个文件（自动排队）。"""
        for fp in file_paths:
            if not os.path.exists(fp):
                continue
            file_size = os.path.getsize(fp)
            file_name = os.path.basename(fp)
            file_id = make_file_id(file_name, file_size)
            qf = QueuedFile(
                file_id=file_id, addr=peer_addr, file_path=fp,
                file_name=file_name, file_size=file_size)
            with self._lock:
                self._transfer_queue.append(qf)
        self._process_queue()

    def cancel_transfer(self, peer_addr: str, file_id: str = ""):
        """取消传输。如果 file_id 为空则取消该地址的所有传输。"""
        with self._lock:
            # 取消活跃传输
            if self._active_transfer and self._active_transfer.peer_addr == peer_addr:
                if not file_id or self._active_transfer.file_id == file_id:
                    self._active_transfer.cancelled = True

            # 取消等待响应的发送
            if file_id:
                self._waiting_response.discard(file_id)
            else:
                self._waiting_response.clear()

            # 从队列中移除等待项
            removed = []
            keep = deque()
            for qf in self._transfer_queue:
                if qf.addr == peer_addr and qf.status == "waiting":
                    if not file_id or qf.file_id == file_id:
                        qf.status = "cancelled"
                        removed.append(qf.file_id)
                        continue
                keep.append(qf)
            self._transfer_queue = keep

        # 通知对方
        cancel_id = file_id if file_id else (removed[0] if removed else "")
        if cancel_id:
            self._send(peer_addr, build_tcp_message(MSG_FILE_CANCEL, key=self._key,
                        file_id=cancel_id))
        for fid in removed:
            self.file_cancelled.emit(fid)

    # ==================================================================
    # 公共 API — 接收端
    # ==================================================================

    def respond_file_request(self, file_id: str, peer_addr: str, accept: bool):
        """响应文件传输请求（接受或拒绝）。

        注意：peer_addr 可能是发送方携带的监听端口地址，
        但实际 TCP socket 是用临时端口连接的 ——
        必须用 _pending_requests 中存储的真实连接地址来发送回应。
        """
        with self._lock:
            ft = self._pending_requests.get(file_id)
        # 用实际 TCP 连接地址发送（而非监听端口地址）
        actual_addr = ft.peer_addr if ft else peer_addr
        self._send(actual_addr, build_tcp_message(MSG_FILE_TRANSFER_RESPONSE, key=self._key,
            file_id=file_id, accepted=accept))
        if accept:
            with self._lock:
                ft = self._pending_requests.pop(file_id, None)
                if ft is not None:
                    self._active_transfer = ft
        else:
            with self._lock:
                self._pending_requests.pop(file_id, None)

    # ==================================================================
    # 公共 API — 消息处理（由 TcpP2P 在其接收循环中调用）
    # ==================================================================

    def handle_message(self, msg: dict, peer_addr: str):
        """处理文件相关的非 chunk 消息。"""
        msg_type = msg.get("type")

        if msg_type == MSG_FILE_TRANSFER_REQUEST:
            self._on_request(msg, peer_addr)
        elif msg_type == MSG_FILE_TRANSFER_RESPONSE:
            self._on_response(msg)
        elif msg_type == MSG_FILE_COMPLETE:
            self._on_complete(msg)
        elif msg_type == MSG_FILE_CANCEL:
            self._on_cancel(msg)

    def handle_chunk(self, header: dict, data: bytes, peer_addr: str):
        """处理收到的文件数据块。"""
        file_id = header.get("file_id", "")
        compressed_flag = header.get("compressed", False)
        progress = None

        try:
            with self._lock:
                ft = self._active_transfer
                if ft is None or ft.file_id != file_id:
                    return
                if ft.cancelled:
                    return

                # 解压
                try:
                    chunk_data = decompress_chunk(data, compressed_flag)
                except Exception as e:
                    ft.cancelled = True
                    pg = TransferProgress(
                        file_id=ft.file_id, file_name=ft.file_name,
                        file_size=ft.file_size)
                    pg.error_msg = f"解压失败: {e}"
                    pg.cancelled = True
                    pg.compressed = compressed_flag
                    pg.direction = "download"
                    self._active_transfer = None
                    tmp = os.path.join(self._recv_dir, f".{file_id}.tmp")
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    self.file_progress.emit(pg)
                    self.file_cancelled.emit(file_id)
                    return

                if ft.received_bytes == 0:
                    ft.start_time = time.time()
                    ft.chunk_times = []

                ft.received_bytes += len(chunk_data)
                ft.chunk_times.append((time.time(), len(chunk_data)))

                # 写临时文件
                tmp_path = os.path.join(self._recv_dir, f".{file_id}.tmp")
                with open(tmp_path, "ab") as f:
                    f.write(chunk_data)

                # 计算并发射进度
                progress = self._calc_progress(ft)
                progress.compressed = compressed_flag
                progress.direction = "download"

                # 检查接收完成
                if ft.received_bytes >= ft.file_size:
                    progress.done = True
                    final_path = os.path.join(self._recv_dir, ft.file_name)
                    counter = 1
                    while os.path.exists(final_path):
                        name, ext = os.path.splitext(ft.file_name)
                        final_path = os.path.join(
                            self._recv_dir, f"{name}_{counter}{ext}")
                        counter += 1
                    try:
                        os.rename(tmp_path, final_path)
                    except OSError:
                        pass
                    self.file_received.emit(file_id, final_path, ft.file_name)
                    self._send(peer_addr, build_tcp_message(MSG_FILE_COMPLETE, key=self._key,
                               file_id=file_id))
                    self._active_transfer = None

        except Exception as e:
            # 块处理异常：取消传输但不终止连接
            with self._lock:
                if self._active_transfer and self._active_transfer.file_id == file_id:
                    self._active_transfer.cancelled = True
                    self._active_transfer = None
            pg = TransferProgress(file_id=file_id, error_msg=f"接收出错: {e}",
                                  cancelled=True)
            self.file_progress.emit(pg)
            self.file_cancelled.emit(file_id)
            tmp = os.path.join(self._recv_dir, f".{file_id}.tmp")
            try:
                os.remove(tmp)
            except OSError:
                pass
            return

        if progress is not None:
            self.file_progress.emit(progress)

    # ==================================================================
    # 内部 — 消息处理
    # ==================================================================

    def _on_request(self, msg: dict, peer_addr: str):
        file_id = msg.get("file_id", "")
        file_name = msg.get("file_name", "")
        file_size = msg.get("file_size", 0)
        file_ext = msg.get("file_ext", "")
        total_chunks = msg.get("total_chunks", 0)
        sender = msg.get("sender", "")
        compressed = msg.get("compressed", False)
        sender_port = msg.get("sender_port", 0)

        ip = peer_addr.split(":")[0]
        # 使用发送者携带的监听端口，而非 TCP 连接的临时端口
        port = sender_port if sender_port else int(peer_addr.split(":")[1])

        self.file_request.emit(
            file_id, sender, ip, port, file_name, file_size, file_ext)

        # 不立即设置 _active_transfer，等用户决策后再激活
        ft = FileTransfer(
            file_id=file_id, file_name=file_name,
            file_size=file_size, file_ext=file_ext,
            total_chunks=total_chunks, sender=sender,
            peer_addr=peer_addr, compressed=compressed)
        with self._lock:
            self._pending_requests[file_id] = ft

    def _on_response(self, msg: dict):
        accepted = msg.get("accepted", False)
        file_id = msg.get("file_id", "")
        with self._lock:
            self._waiting_response.discard(file_id)
        if accepted:
            # 对方同意 → 启动发送线程
            qf = None
            with self._lock:
                for q in self._transfer_queue:
                    if q.file_id == file_id and q.status == "sending":
                        qf = q
                        break
            if qf is not None:
                total_chunks = max(
                    1, (qf.file_size + TCP_CHUNK_SIZE - 1) // TCP_CHUNK_SIZE)
                threading.Thread(target=self._send_file_worker,
                                 args=(qf, total_chunks), daemon=True).start()
        else:
            # 对方拒绝
            with self._lock:
                if self._active_transfer and self._active_transfer.file_id == file_id:
                    self._active_transfer.cancelled = True
                    self._active_transfer = None
                for q in self._transfer_queue:
                    if q.file_id == file_id:
                        q.status = "cancelled"
                        break
            self.file_cancelled.emit(file_id)
            self._process_queue()

    def _on_complete(self, msg: dict):
        file_id = msg.get("file_id", "")
        with self._lock:
            if self._active_transfer and self._active_transfer.file_id == file_id:
                self._active_transfer.received_bytes = self._active_transfer.file_size
                self._active_transfer = None
            # 标记队列项为完成
            for qf in self._transfer_queue:
                if qf.file_id == file_id:
                    qf.status = "done"
                    break
        self._process_queue()

    def _on_cancel(self, msg: dict):
        file_id = msg.get("file_id", "")
        with self._lock:
            self._waiting_response.discard(file_id)
            self._pending_requests.pop(file_id, None)
            if self._active_transfer and self._active_transfer.file_id == file_id:
                self._active_transfer.cancelled = True
            for qf in self._transfer_queue:
                if qf.file_id == file_id:
                    qf.status = "cancelled"
                    break
        self.file_cancelled.emit(file_id)
        self._process_queue()

    # ==================================================================
    # 内部 — 发送工作线程
    # ==================================================================

    def _send_file_worker(self, qf: QueuedFile, total_chunks: int):
        """后台线程：分块读取并发送文件，实时上报进度。"""
        start_time = time.time()
        sent_bytes = 0
        recent_samples: list = []  # [(timestamp, bytes)]
        last_progress_time = start_time

        try:
            with open(qf.file_path, "rb") as f:
                for i in range(total_chunks):
                    # 检查取消
                    with self._lock:
                        if self._active_transfer and \
                           self._active_transfer.cancelled:
                            qf.status = "cancelled"
                            return

                    chunk_data = f.read(TCP_CHUNK_SIZE)
                    if not chunk_data:
                        break

                    # 压缩
                    compressed = False
                    if self.compression_enabled:
                        chunk_data, compressed = compress_chunk(
                            chunk_data, self.compression_level)

                    chunk_msg = build_file_chunk(
                        qf.file_id, i, total_chunks, chunk_data, compressed)

                    if not self._send(qf.addr, chunk_msg):
                        qf.status = "error"
                        qf.error_msg = "发送失败"
                        pg = TransferProgress(qf.file_id, qf.file_name, qf.file_size)
                        pg.error_msg = "发送失败"
                        pg.cancelled = True
                        pg.direction = "upload"
                        self.file_progress.emit(pg)
                        self.file_cancelled.emit(qf.file_id)
                        return

                    sent_bytes += len(chunk_data)
                    recent_samples.append((time.time(), len(chunk_data)))

                    # 控制进度上报频率：每 10 个 chunk 或 0.5 秒
                    now = time.time()
                    if i % 10 == 0 or now - last_progress_time >= 0.5 \
                       or i == total_chunks - 1:
                        self._emit_send_progress(
                            qf, sent_bytes, start_time, recent_samples)
                        last_progress_time = now

            # 发送完成
            qf.status = "done"
            pg = TransferProgress(qf.file_id, qf.file_name, qf.file_size)
            pg.received_bytes = sent_bytes
            pg.done = True
            pg.direction = "upload"
            self.file_progress.emit(pg)
            self.file_sent.emit(qf.file_id, qf.file_name)

        except Exception as e:
            qf.status = "error"
            qf.error_msg = str(e)
            pg = TransferProgress(qf.file_id, qf.file_name, qf.file_size)
            pg.error_msg = str(e)
            pg.cancelled = True
            pg.direction = "upload"
            self.file_progress.emit(pg)
            self.file_cancelled.emit(qf.file_id)

        finally:
            with self._lock:
                if self._active_transfer and \
                   self._active_transfer.file_id == qf.file_id:
                    self._active_transfer = None
            self._process_queue()

    def _emit_send_progress(self, qf: QueuedFile, sent_bytes: int,
                            start_time: float, recent_samples: list):
        """构造并发射发送端进度。"""
        pg = TransferProgress(qf.file_id, qf.file_name, qf.file_size)
        pg.received_bytes = sent_bytes
        pg.direction = "upload"

        elapsed = time.time() - start_time
        if elapsed > 0.2:
            if len(recent_samples) >= 2:
                # 用最近 N 个样本算瞬时速度
                window = recent_samples[-5:]
                t0, _ = window[0]
                tn, _ = window[-1]
                dt = tn - t0
                total_window = sum(s for _, s in window)
                pg.speed = total_window / dt if dt > 0 else sent_bytes / elapsed
            else:
                pg.speed = sent_bytes / elapsed
        else:
            pg.speed = 0

        remaining = qf.file_size - sent_bytes
        pg.eta_seconds = remaining / pg.speed if pg.speed > 0 else -1

        self.file_progress.emit(pg)

    # ==================================================================
    # 内部 — 队列管理
    # ==================================================================

    def _process_queue(self):
        """从队列中取出下一个 waiting 的文件开始发送。"""
        with self._lock:
            # 清理已完成/取消/出错的项
            self._transfer_queue = deque(
                qf for qf in self._transfer_queue
                if qf.status in ("waiting", "sending"))

            # 如果有活跃传输，等待其完成
            if self._active_transfer is not None:
                return

            # 找下一个 waiting 文件
            for qf in self._transfer_queue:
                if qf.status == "waiting":
                    qf.status = "sending"
                    _, ext = os.path.splitext(qf.file_name)
                    total_chunks = max(
                        1, (qf.file_size + TCP_CHUNK_SIZE - 1) // TCP_CHUNK_SIZE)

                    self._active_transfer = FileTransfer(
                        file_id=qf.file_id, file_name=qf.file_name,
                        file_size=qf.file_size, file_ext=ext,
                        total_chunks=total_chunks, sender="",
                        peer_addr=qf.addr,
                        compressed=self.compression_enabled)
                    self._waiting_response.add(qf.file_id)

                    # 发送请求（不立即传数据，等对方 accept）
                    self._send(qf.addr,
                        build_tcp_message(MSG_FILE_TRANSFER_REQUEST, key=self._key,
                            file_id=qf.file_id, file_name=qf.file_name,
                            file_size=qf.file_size, file_ext=ext,
                            total_chunks=total_chunks, sender=self._sender_name,
                            sender_port=self._sender_port,
                            compressed=self.compression_enabled))
                    return

    # ==================================================================
    # 内部 — 进度计算
    # ==================================================================

    def _calc_progress(self, ft: FileTransfer) -> TransferProgress:
        """根据 FileTransfer 状态计算进度对象。"""
        progress = TransferProgress(
            file_id=ft.file_id, file_name=ft.file_name,
            file_size=ft.file_size, received_bytes=ft.received_bytes)

        elapsed = time.time() - ft.start_time
        if elapsed > 0.2:
            recent = ft.chunk_times[-5:]
            if len(recent) >= 2:
                t0, _ = recent[0]
                tn, _ = recent[-1]
                dt = tn - t0
                total_recent = sum(s for _, s in recent)
                progress.speed = total_recent / dt if dt > 0 else 0
            else:
                progress.speed = ft.received_bytes / elapsed if elapsed > 0 else 0
        else:
            progress.speed = 0

        remaining = ft.file_size - ft.received_bytes
        progress.eta_seconds = (remaining / progress.speed
                                if progress.speed > 0 else -1)

        return progress
