"""消息协议定义：消息类型常量、数据类、序列化/反序列化工具。"""

import json
import struct
import time
import hashlib
import os
from dataclasses import dataclass, field
from typing import Optional

from .crypto import encrypt, try_decrypt, PLAINTEXT_FLAG

# =============================================================================
# 网络常量
# =============================================================================
DEFAULT_UDP_PORT = 9000
DEFAULT_TCP_PORT = 9001
BROADCAST_ADDR = "255.255.255.255"
MAX_UDP_SIZE = 60000
TCP_CHUNK_SIZE = 65536
HEARTBEAT_INTERVAL = 5
OFFLINE_TIMEOUT = 15

# =============================================================================
# 消息类型
# =============================================================================

# --- UDP 消息类型 ---
MSG_USER_ONLINE = "user_online"
MSG_USER_OFFLINE = "user_offline"
MSG_USER_LIST_REQUEST = "user_list_request"
MSG_USER_LIST_RESPONSE = "user_list_response"
MSG_GROUP_MESSAGE = "group_message"

# --- TCP P2P 消息类型 ---
MSG_PRIVATE_MESSAGE = "private_message"
MSG_PRIVATE_IMAGE = "private_image"
MSG_FILE_TRANSFER_REQUEST = "file_transfer_request"
MSG_FILE_TRANSFER_RESPONSE = "file_transfer_response"
MSG_FILE_CHUNK = "file_chunk"
MSG_FILE_COMPLETE = "file_complete"
MSG_FILE_CANCEL = "file_cancel"


# =============================================================================
# 数据类
# =============================================================================

@dataclass
class UserInfo:
    username: str
    ip: str
    tcp_port: int
    avatar: str = ""          # 头像标识（""=首字母，"fox"=SVG）
    last_seen: float = field(default_factory=time.time)


# FileTransfer / TransferProgress / QueuedFile 已移至 file_transfer.py
# make_file_id / build_file_chunk 已移至 file_transfer.py
# 此处保留消息类型常量、UDP/TCP 消息构建器、格式化函数。


# =============================================================================
# 消息构建与解析
# =============================================================================

def build_udp_message(msg_type: str, key: Optional[bytes] = None,
                      **kwargs) -> bytes:
    """构建 UDP 消息。如果提供 key 则加密。"""
    msg = {"type": msg_type, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
    msg.update(kwargs)
    raw = json.dumps(msg, ensure_ascii=False).encode()
    if key:
        raw = encrypt(raw, key)
    else:
        raw = PLAINTEXT_FLAG + raw
    if len(raw) > MAX_UDP_SIZE:
        raise ValueError(f"UDP message exceeds {MAX_UDP_SIZE} bytes")
    return raw


def parse_udp_message(data: bytes, key: Optional[bytes] = None) -> dict:
    """解析 UDP 消息。自动检测并解密。"""
    plain, _ = try_decrypt(data, key)
    return json.loads(plain.decode())


def build_tcp_message(msg_type: str, key: Optional[bytes] = None,
                      **kwargs) -> bytes:
    """构建 TCP 消息帧：[4字节长度][数据]。如果提供 key 则加密。"""
    msg = {"type": msg_type, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
    msg.update(kwargs)
    raw = json.dumps(msg, ensure_ascii=False).encode()
    if key:
        raw = encrypt(raw, key)
    else:
        raw = PLAINTEXT_FLAG + raw
    return struct.pack("!I", len(raw)) + raw


def parse_tcp_message(data: bytes, key: Optional[bytes] = None) -> dict:
    """解析 TCP 消息数据（不含4字节长度前缀）。自动检测并解密。"""
    plain, _ = try_decrypt(data, key)
    return json.loads(plain.decode())


# build_tcp_chunk / build_file_chunk → 见 file_transfer.py


def make_file_id(filename: str, size: int) -> str:
    raw = f"{filename}_{size}_{time.time()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_speed(bytes_per_sec: float) -> str:
    return f"{format_size(int(bytes_per_sec))}/s"


def format_time(seconds: float) -> str:
    if seconds < 0:
        return "--"
    if seconds < 60:
        return f"{int(seconds)}秒"
    elif seconds < 3600:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}分{s}秒"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}小时{m}分"
