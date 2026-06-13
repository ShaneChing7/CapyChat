"""UDP 广播模块：用户发现、心跳维护、群聊消息收发。"""

import socket
import threading
import time
from PySide6.QtCore import QObject, Signal

from typing import Optional

from .protocol import (
    DEFAULT_UDP_PORT, BROADCAST_ADDR, MAX_UDP_SIZE,
    HEARTBEAT_INTERVAL, OFFLINE_TIMEOUT,
    MSG_USER_ONLINE, MSG_USER_OFFLINE, MSG_USER_LIST_REQUEST,
    MSG_USER_LIST_RESPONSE, MSG_GROUP_MESSAGE,
    UserInfo, build_udp_message, parse_udp_message,
)


class UdpBroadcast(QObject):
    # 用户列表变化（avatar 参数：""=首字母，"fox"=SVG key）
    user_online = Signal(str, str, int, str)       # username, ip, tcp_port, avatar
    user_offline = Signal(str, str)                 # username, ip
    user_list_updated = Signal(list)                # [(username, ip, tcp_port, avatar), ...]

    # 群聊消息
    group_message_received = Signal(str, str, str, str)  # username, ip, content, timestamp

    # 错误信号
    error = Signal(str)

    def __init__(self, username: str, local_ip: str,
                 udp_port: int = DEFAULT_UDP_PORT, tcp_port: int = 9001,
                 encryption_key: Optional[bytes] = None,
                 avatar: str = ""):
        super().__init__()
        self.username = username
        self.local_ip = local_ip
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.avatar = avatar          # 当前用户头像标识
        self._key = encryption_key
        self.running = False
        self.socket: socket.socket | None = None
        self._users: dict[str, UserInfo] = {}  # key: "ip:tcp_port"
        self._users_lock = threading.Lock()
        self._recv_thread: threading.Thread | None = None
        self._heartbeat_thread: threading.Thread | None = None

        # 消息去重：Windows 多网卡可能收到重复广播
        self._seen_messages: set[tuple] = set()
        self._seen_lock = threading.Lock()
        self._dedup_max = 200  # 去重缓存上限

    def start(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.settimeout(1.0)
        try:
            self.socket.bind(("", self.udp_port))
        except OSError as e:
            self.error.emit(f"UDP端口 {self.udp_port} 绑定失败: {e}")
            raise

        self.running = True
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

        # 延迟片刻后广播上线消息（等待TCP服务端就绪）
        def _delayed_announce():
            time.sleep(0.3)
            if self.running:
                self._send_raw(build_udp_message(MSG_USER_ONLINE, key=self._key,
                    username=self.username, ip=self.local_ip, tcp_port=self.tcp_port,
                    avatar=self.avatar))
                self._send_raw(build_udp_message(MSG_USER_LIST_REQUEST, key=self._key,
                    username=self.username))
            # 二次请求：确保 UI 已初始化、信号已连接后再同步一次
            # 避免首次响应在 ChatController 就绪前到达导致列表被丢弃
            time.sleep(1.7)
            if self.running:
                self._send_raw(build_udp_message(MSG_USER_LIST_REQUEST, key=self._key,
                    username=self.username))
        threading.Thread(target=_delayed_announce, daemon=True).start()

        print(f"[UDP] 广播模块启动 - 端口:{self.udp_port}")

    def stop(self):
        self.running = False
        self._send_raw(build_udp_message(MSG_USER_OFFLINE, key=self._key,
            username=self.username, ip=self.local_ip))
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        print("[UDP] 广播模块已停止")

    def send_group_message(self, content: str) -> bool:
        try:
            msg = build_udp_message(MSG_GROUP_MESSAGE, key=self._key,
                username=self.username, ip=self.local_ip,
                content=content)
            return self._send_raw(msg)
        except ValueError as e:
            self.error.emit(str(e))
            return False

    def announce_now(self) -> None:
        """立即广播上线消息（头像变更等需要即时同步时调用）。

        与心跳不同，此方法立即发送，不等 HEARTBEAT_INTERVAL。
        """
        if not self.running:
            return
        self._send_raw(build_udp_message(
            MSG_USER_ONLINE, key=self._key,
            username=self.username, ip=self.local_ip,
            tcp_port=self.tcp_port, avatar=self.avatar))

    def sync_user_list(self) -> None:
        """强制重新发送当前用户列表信号。

        用于 UI 初始化完成后同步已在 _users 中但信号已被丢弃的在线用户。
        """
        if self.running:
            self._emit_user_list()

    def get_users(self) -> list:
        with self._users_lock:
            return [(u.username, u.ip, u.tcp_port)
                    for u in self._users.values()
                    if u.username != self.username]

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _send_raw(self, data: bytes) -> bool:
        try:
            self.socket.sendto(data, (BROADCAST_ADDR, self.udp_port))
            return True
        except Exception as e:
            self.error.emit(f"UDP发送失败: {e}")
            return False

    def _send_to(self, data: bytes, addr: tuple) -> bool:
        try:
            self.socket.sendto(data, addr)
            return True
        except Exception as e:
            self.error.emit(f"UDP发送到 {addr} 失败: {e}")
            return False

    def _recv_loop(self):
        while self.running:
            try:
                data, addr = self.socket.recvfrom(MAX_UDP_SIZE)
                if data:
                    self._handle_message(data, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self.error.emit(f"UDP接收错误: {e}")

    def _heartbeat_loop(self):
        # 首次心跳延迟，让TCP服务端完全就绪
        time.sleep(1.0)
        while self.running:
            if self.running:
                self._send_raw(build_udp_message(MSG_USER_ONLINE, key=self._key,
                    username=self.username, ip=self.local_ip,
                    tcp_port=self.tcp_port, avatar=self.avatar))
            # 清理离线用户（锁内操作字典，锁外发信号）
            now = time.time()
            gone = []
            with self._users_lock:
                for k, u in list(self._users.items()):
                    if now - u.last_seen > OFFLINE_TIMEOUT:
                        self._users.pop(k, None)
                        gone.append(u)
            for u in gone:
                self.user_offline.emit(u.username, u.ip)
            if gone:
                self._emit_user_list()
            time.sleep(HEARTBEAT_INTERVAL)

    def _handle_message(self, data: bytes, addr: tuple):
        try:
            msg = parse_udp_message(data, key=self._key)
        except Exception:
            return

        msg_type = msg.get("type")
        sender_ip = addr[0]

        if msg_type == MSG_USER_ONLINE:
            username = msg.get("username")
            tcp_port = msg.get("tcp_port", DEFAULT_UDP_PORT + 1)
            avatar = msg.get("avatar", "")  # 向后兼容：旧版消息无此字段
            if username and username != self.username:
                key = f"{sender_ip}:{tcp_port}"
                is_new = False
                avatar_changed = False
                with self._users_lock:
                    existing = self._users.get(key)
                    is_new = existing is None
                    # 检测头像变更（已在线用户更换头像时触发）
                    if existing is not None and existing.avatar != avatar:
                        avatar_changed = True
                    self._users[key] = UserInfo(
                        username=username, ip=sender_ip,
                        tcp_port=tcp_port, avatar=avatar,
                        last_seen=time.time()
                    )
                if is_new or avatar_changed:
                    self.user_online.emit(username, sender_ip, tcp_port, avatar)
                    self._emit_user_list()

        elif msg_type == MSG_USER_OFFLINE:
            username = msg.get("username")
            if username:
                gone = []
                with self._users_lock:
                    keys_to_remove = [
                        k for k, u in self._users.items()
                        if u.username == username and u.ip == sender_ip
                    ]
                    for k in keys_to_remove:
                        u = self._users.pop(k, None)
                        if u:
                            gone.append(u)
                for u in gone:
                    self.user_offline.emit(u.username, u.ip)
                if gone:
                    self._emit_user_list()

        elif msg_type == MSG_USER_LIST_REQUEST:
            self._send_to(
                build_udp_message(MSG_USER_LIST_RESPONSE, key=self._key,
                    username=self.username, ip=self.local_ip,
                    tcp_port=self.tcp_port),
                addr
            )

        elif msg_type == MSG_USER_LIST_RESPONSE:
            username = msg.get("username")
            tcp_port = msg.get("tcp_port", DEFAULT_UDP_PORT + 1)
            avatar = msg.get("avatar", "")
            if username and username != self.username:
                key = f"{sender_ip}:{tcp_port}"
                is_new = False
                avatar_changed = False
                with self._users_lock:
                    existing = self._users.get(key)
                    if existing is None:
                        self._users[key] = UserInfo(
                            username=username, ip=sender_ip,
                            tcp_port=tcp_port, avatar=avatar
                        )
                        is_new = True
                    else:
                        # 更新 last_seen（防止心跳清理前就过期）
                        existing.last_seen = time.time()
                        if existing.avatar != avatar:
                            existing.avatar = avatar
                            avatar_changed = True
                if is_new or avatar_changed:
                    self.user_online.emit(username, sender_ip, tcp_port, avatar)
                # 列表响应是显式的状态同步，始终触发列表更新
                # 修复：登录初期信号尚未连接时收到响应，之后心跳会因
                # is_new=False 而跳过通知 —— 所以这里必须无条件发送
                self._emit_user_list()

        elif msg_type == MSG_GROUP_MESSAGE:
            username = msg.get("username")
            content = msg.get("content")
            timestamp = msg.get("timestamp")
            if username and content and username != self.username:
                # 去重：同一秒内的同用户同内容消息只保留一条
                dedup_key = (username, sender_ip, content, timestamp)
                with self._seen_lock:
                    if dedup_key in self._seen_messages:
                        return
                    self._seen_messages.add(dedup_key)
                    if len(self._seen_messages) > self._dedup_max:
                        # 清理旧缓存：保留最近的100条
                        self._seen_messages = set(
                            list(self._seen_messages)[-100:])
                self.group_message_received.emit(
                    username, sender_ip, content, timestamp
                )

    def _emit_user_list(self):
        with self._users_lock:
            users = [
                (u.username, u.ip, u.tcp_port, u.avatar)
                for u in self._users.values()
                if u.username != self.username
            ]
        self.user_list_updated.emit(users)
