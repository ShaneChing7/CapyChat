"""网络通信层：UDP广播、TCP P2P、文件传输、协议定义。"""

from .protocol import (
    DEFAULT_UDP_PORT, DEFAULT_TCP_PORT, BROADCAST_ADDR,
    MAX_UDP_SIZE, TCP_CHUNK_SIZE,
    HEARTBEAT_INTERVAL, OFFLINE_TIMEOUT,
    MSG_USER_ONLINE, MSG_USER_OFFLINE,
    MSG_USER_LIST_REQUEST, MSG_USER_LIST_RESPONSE,
    MSG_GROUP_MESSAGE,
    MSG_PRIVATE_MESSAGE, MSG_PRIVATE_IMAGE,
    MSG_FILE_TRANSFER_REQUEST, MSG_FILE_TRANSFER_RESPONSE,
    MSG_FILE_CHUNK, MSG_FILE_COMPLETE, MSG_FILE_CANCEL,
    UserInfo,
    build_udp_message, parse_udp_message,
    build_tcp_message,
    make_file_id, format_size, format_speed, format_time,
)

from .file_transfer import (
    FileTransferManager, FileTransfer, QueuedFile, TransferProgress,
    make_file_id as ft_make_file_id,
    build_file_chunk,
    compress_chunk, decompress_chunk,
)

from .udp_broadcast import UdpBroadcast
from .tcp_p2p import TcpP2P
