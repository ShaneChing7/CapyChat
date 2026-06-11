"""TCP P2P 模块：P2P连接管理、私聊消息、文件传输委托。

文件传输逻辑已抽离至 file_transfer.py — 本模块只负责连接管理和消息路由。
"""

import json
import socket
import struct
import threading
import time
import os
from typing import Optional

from PySide6.QtCore import QObject, Signal

from .protocol import (
    DEFAULT_TCP_PORT,
    MSG_PRIVATE_MESSAGE, MSG_PRIVATE_IMAGE,
    MSG_FILE_TRANSFER_REQUEST, MSG_FILE_TRANSFER_RESPONSE,
    MSG_FILE_CHUNK, MSG_FILE_COMPLETE, MSG_FILE_CANCEL,
    build_tcp_message, parse_tcp_message,
)

from .file_transfer import FileTransferManager


class TcpP2P(QObject):
    """TCP P2P 连接管理 + 私聊消息 + 文件传输协调。

    文件传输由 FileTransferManager 处理，本类充当：
    1. Socket 层 — 监听、连接、收发原始数据
    2. 路由器 — 将文件消息分发给 FileTransferManager
    3. 信号桥 — 转发 FileTransferManager 的信号给 UI
    """

    # --- 私聊消息信号 ---
    private_message_received = Signal(str, str, int, str, str)
    # username, ip, port, content, timestamp
    private_image_received = Signal(str, str, int, str, str, str)
    # username, ip, port, data, ext, filename

    # --- 文件传输信号（与 FileTransferManager 信号签名一致）---
    file_request = Signal(str, str, str, int, str, int, str)
    # file_id, sender, sender_ip, sender_port, file_name, file_size, file_ext
    file_progress = Signal(object)            # TransferProgress
    file_received = Signal(str, str, str)      # file_id, file_path, file_name
    file_sent = Signal(str, str)               # file_id, file_name
    file_cancelled = Signal(str)               # file_id

    # --- 连接状态 ---
    peer_connected = Signal(str, str)          # username, address
    peer_disconnected = Signal(str)            # address
    error = Signal(str)

    def __init__(self, username: str, local_ip: str,
                 tcp_port: int = DEFAULT_TCP_PORT,
                 encryption_key: Optional[bytes] = None):
        super().__init__()
        self.username = username
        self.local_ip = local_ip
        self.tcp_port = tcp_port
        self._key = encryption_key
        self.running = False

        # --- Socket ---
        self._server_socket: socket.socket | None = None
        self._connections: dict[str, socket.socket] = {}  # "ip:port" -> socket
        self._conn_info: dict[str, str] = {}               # "ip:port" -> username
        self._conn_lock = threading.Lock()
        self._send_lock = threading.Lock()

        # --- 后台线程 ---
        self._accept_thread: threading.Thread | None = None

        # --- 文件传输管理器 ---
        recv_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "received")
        self.file_mgr = FileTransferManager(
            recv_dir=recv_dir,
            send_callback=self._send_tcp,
            sender_name=username,
            sender_port=tcp_port,
            encryption_key=self._key)

        # 转发文件传输信号
        self.file_mgr.file_request.connect(self.file_request.emit)
        self.file_mgr.file_progress.connect(self.file_progress.emit)
        self.file_mgr.file_received.connect(self.file_received.emit)
        self.file_mgr.file_sent.connect(self.file_sent.emit)
        self.file_mgr.file_cancelled.connect(self.file_cancelled.emit)

    # ==================================================================
    # 启动 / 停止
    # ==================================================================

    def start(self):
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.settimeout(1.0)
        self._server_socket.bind(("", self.tcp_port))
        self._server_socket.listen(10)
        self.running = True
        self._accept_thread = threading.Thread(target=self._accept_loop,
                                               daemon=True)
        self._accept_thread.start()
        print(f"[TCP P2P] 监听启动 - {self.local_ip}:{self.tcp_port}")

    def stop(self):
        self.running = False
        with self._conn_lock:
            for sock in list(self._connections.values()):
                try:
                    sock.close()
                except Exception:
                    pass
            self._connections.clear()
            self._conn_info.clear()
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None
        print("[TCP P2P] 已停止")

    # ==================================================================
    # 连接到对等点
    # ==================================================================

    def connect_to_peer(self, peer_ip: str, peer_port: int) -> bool:
        addr = f"{peer_ip}:{peer_port}"
        with self._conn_lock:
            if addr in self._connections:
                return True

        last_error = None
        for attempt in range(3):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3.0)
                sock.connect((peer_ip, peer_port))
                sock.settimeout(None)
                with self._conn_lock:
                    self._connections[addr] = sock
                threading.Thread(target=self._recv_loop,
                                 args=(sock, addr), daemon=True).start()
                self.peer_connected.emit("", addr)
                print(f"[TCP P2P] 已连接到 {addr}")
                return True
            except Exception as e:
                last_error = e
                if attempt < 2:
                    time.sleep(0.5)

        self.error.emit(
            f"无法连接到 {addr}（重试3次均失败）。\n"
            f"请检查：\n"
            f"  1. 对方是否在同一局域网\n"
            f"  2. 对方防火墙是否放行 TCP {peer_port}\n"
            f"  3. 对方IP地址是否正确\n"
            f"原始错误: {last_error}")
        return False

    # ==================================================================
    # 私聊消息
    # ==================================================================

    def send_private_message(self, peer_ip: str, peer_port: int,
                              content: str) -> bool:
        addr = f"{peer_ip}:{peer_port}"
        if not self._ensure_connected(peer_ip, peer_port):
            return False
        return self._send_tcp(addr, build_tcp_message(MSG_PRIVATE_MESSAGE, key=self._key,
            username=self.username, content=content,
            sender_port=self.tcp_port))

    def send_private_image(self, peer_ip: str, peer_port: int,
                            image_data: str, image_ext: str,
                            file_name: str) -> bool:
        addr = f"{peer_ip}:{peer_port}"
        if not self._ensure_connected(peer_ip, peer_port):
            return False
        return self._send_tcp(addr, build_tcp_message(MSG_PRIVATE_IMAGE, key=self._key,
            username=self.username, image_data=image_data,
            image_ext=image_ext, file_name=file_name,
            sender_port=self.tcp_port))

    # ==================================================================
    # 文件传输（委托给 FileTransferManager）
    # ==================================================================

    def send_file(self, peer_ip: str, peer_port: int, file_path: str) -> Optional[str]:
        """发送文件，返回 file_id 用于追踪进度，失败返回 None。"""
        addr = f"{peer_ip}:{peer_port}"
        if not os.path.exists(file_path):
            self.error.emit(f"文件不存在: {file_path}")
            return None
        if not self._ensure_connected(peer_ip, peer_port):
            return None
        return self.file_mgr.send_file(addr, file_path)

    def send_files(self, peer_ip: str, peer_port: int,
                   file_paths: list[str]):
        addr = f"{peer_ip}:{peer_port}"
        if not self._ensure_connected(peer_ip, peer_port):
            return
        self.file_mgr.send_files(addr, file_paths)

    def respond_file_request(self, file_id: str, peer_addr: str, accept: bool):
        self.file_mgr.respond_file_request(file_id, peer_addr, accept)

    def cancel_transfer(self, peer_addr: str, file_id: str):
        self.file_mgr.cancel_transfer(peer_addr, file_id)

    # ==================================================================
    # 内部 — 连接管理
    # ==================================================================

    def _ensure_connected(self, peer_ip: str, peer_port: int) -> bool:
        addr = f"{peer_ip}:{peer_port}"
        with self._conn_lock:
            if addr in self._connections:
                return True
        return self.connect_to_peer(peer_ip, peer_port)

    def _accept_loop(self):
        while self.running:
            try:
                client_sock, addr = self._server_socket.accept()
                peer_addr = f"{addr[0]}:{addr[1]}"
                with self._conn_lock:
                    if peer_addr in self._connections:
                        client_sock.close()
                        continue
                    self._connections[peer_addr] = client_sock
                threading.Thread(target=self._recv_loop,
                                 args=(client_sock, peer_addr),
                                 daemon=True).start()
                self.peer_connected.emit("", peer_addr)
                print(f"[TCP P2P] 新连接: {peer_addr}")
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.error.emit(f"接受连接失败: {e}")

    # ==================================================================
    # 内部 — 接收循环
    # ==================================================================

    def _recv_loop(self, sock: socket.socket, peer_addr: str):
        sock.settimeout(None)
        buf = b""
        while self.running:
            try:
                # 读取4字节长度头
                while len(buf) < 4:
                    chunk = sock.recv(4 - len(buf))
                    if not chunk:
                        raise ConnectionError("连接断开")
                    buf += chunk
                header_len = struct.unpack("!I", buf[:4])[0]
                buf = buf[4:]

                # 读取JSON头部
                while len(buf) < header_len:
                    chunk = sock.recv(header_len - len(buf))
                    if not chunk:
                        raise ConnectionError("连接断开")
                    buf += chunk
                header_bytes = buf[:header_len]
                buf = buf[header_len:]

                header = parse_tcp_message(header_bytes, key=self._key)
                msg_type = header.get("type")

                if msg_type == MSG_FILE_CHUNK:
                    # 读取二进制数据
                    data_size = header.get("data_size", 0)
                    while len(buf) < data_size:
                        chunk = sock.recv(data_size - len(buf))
                        if not chunk:
                            raise ConnectionError("连接断开")
                        buf += chunk
                    chunk_data = buf[:data_size]
                    buf = buf[data_size:]
                    # 委托给 FileTransferManager
                    self.file_mgr.handle_chunk(header, chunk_data, peer_addr)
                else:
                    self._handle_message(header, peer_addr)

            except ConnectionError:
                break
            except Exception as e:
                self.error.emit(f"接收错误 ({peer_addr}): {e}")
                break

        # 清理连接
        sock.close()
        with self._conn_lock:
            self._connections.pop(peer_addr, None)
            self._conn_info.pop(peer_addr, None)
        self.peer_disconnected.emit(peer_addr)
        print(f"[TCP P2P] 断开连接: {peer_addr}")

    # ==================================================================
    # 内部 — 消息路由
    # ==================================================================

    def _handle_message(self, msg: dict, peer_addr: str):
        msg_type = msg.get("type")
        sender = msg.get("username", "")
        timestamp = msg.get("timestamp", "")

        if sender:
            with self._conn_lock:
                self._conn_info[peer_addr] = sender

        # --- 私聊消息（本类处理）---
        if msg_type == MSG_PRIVATE_MESSAGE:
            content = msg.get("content", "")
            sender_port = msg.get("sender_port",
                                  int(peer_addr.split(":")[1]))
            self.private_message_received.emit(
                sender, peer_addr.split(":")[0], sender_port,
                content, timestamp)

        elif msg_type == MSG_PRIVATE_IMAGE:
            image_data = msg.get("image_data", "")
            image_ext = msg.get("image_ext", "")
            file_name = msg.get("file_name", "")
            sender_port = msg.get("sender_port",
                                  int(peer_addr.split(":")[1]))
            self.private_image_received.emit(
                sender, peer_addr.split(":")[0], sender_port,
                image_data, image_ext, file_name)

        # --- 文件传输消息（委托给 FileTransferManager）---
        elif msg_type in (MSG_FILE_TRANSFER_REQUEST,
                          MSG_FILE_TRANSFER_RESPONSE,
                          MSG_FILE_COMPLETE,
                          MSG_FILE_CANCEL):
            self.file_mgr.handle_message(msg, peer_addr)

    # ==================================================================
    # 内部 — 发送
    # ==================================================================

    def _send_tcp(self, addr: str, data: bytes) -> bool:
        """通过已建立的TCP连接发送数据（供 FileTransferManager 回调）。"""
        with self._conn_lock:
            sock = self._connections.get(addr)
        if not sock:
            return False
        try:
            with self._send_lock:
                sock.sendall(data)
            return True
        except Exception as e:
            self.error.emit(f"发送到 {addr} 失败: {e}")
            with self._conn_lock:
                self._connections.pop(addr, None)
            try:
                sock.close()
            except Exception:
                pass
            return False
