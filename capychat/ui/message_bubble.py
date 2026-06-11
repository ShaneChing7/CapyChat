"""消息气泡组件 — paintEvent 绘制不对称圆角背景 + 圆形头像。"""

import os

from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QVBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPixmap

from .theme import (PRIMARY, BG_MSG_OTHER, TEXT_PRIMARY,
                    TEXT_SECONDARY, TEXT_HINT, RADIUS_BUBBLE,
                    BUBBLE_CORNER_SMALL)
from .avatar_cache import AvatarWidget


class BubbleWidget(QWidget):
    """带不对称圆角的气泡背景 + 文字内容。

    is_mine=True  → PRIMARY 暖橙背景，右下角 4px 小圆角
    is_mine=False → BG_MSG_OTHER 暖灰背景，左下角 4px 小圆角

    布局用 margin 控制内边距（不用 CSS padding），确保 sizeHint 准确。
    self / other 气泡共用同一套尺寸逻辑，仅背景色和圆角方向不同。
    """

    _LABEL_MAX_W = 440  # 480 气泡总宽 - 16*2 内边距 - 少量余量

    def __init__(self, text="", is_mine=True, parent=None):
        super().__init__(parent)
        self._is_mine = is_mine

        # 水平：不超过内容自然宽度（短消息紧凑，长消息撑到 max）
        # 垂直：高度由内容撑开
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.setMaximumWidth(480)

        fg = "#ffffff" if is_mine else TEXT_PRIMARY
        self._label = QLabel(text)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(self._LABEL_MAX_W)
        self._label.setStyleSheet(f"""
            QLabel {{
                color: {fg};
                font-size: 15px;
                background: transparent;
                border: none;
                line-height: 1.6;
            }}
        """)

        # 用 layout margin 做内边距，Qt 能正确计入 sizeHint
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.addWidget(self._label)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        if w < 8 or h < 8:
            return

        r = RADIUS_BUBBLE
        s = BUBBLE_CORNER_SMALL

        p.setPen(Qt.NoPen)
        bg = QColor(PRIMARY) if self._is_mine else QColor(BG_MSG_OTHER)
        p.setBrush(bg)

        # 1) 全圆角矩形（四个角统一大圆角）
        p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # 2) 遮罩 — 用矩形覆盖目标角的大圆弧，使该角等效为小圆角
        if self._is_mine:
            # 右下角 → 覆盖底部 + 右侧的大圆弧
            p.drawRect(QRectF(w - r, h - s, r, s))
            p.drawRect(QRectF(w - s, h - r, s, r))
        else:
            # 左下角 → 覆盖底部 + 左侧的大圆弧
            p.drawRect(QRectF(0, h - s, r, s))
            p.drawRect(QRectF(0, h - r, s, r))

        p.end()

    def set_text(self, text: str) -> None:
        """运行时更新气泡文字。"""
        self._label.setText(text)
        self.updateGeometry()


class MessageBubbleWidget(QWidget):
    """一条完整的消息行：头像 + 发送者名 + 气泡 + 时间戳。

    is_mine=True  → 右对齐，自己的头像在右侧
    is_mine=False → 左对齐，对方头像在左侧
    """

    def __init__(self, sender="", content="", timestamp="",
                 is_mine=False, avatar_key="", parent=None):
        super().__init__(parent)
        self.initUI(sender, content, timestamp, is_mine, avatar_key)

    def initUI(self, sender, content, timestamp, is_mine, avatar_key):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # 头像 — 固定尺寸，不受拉伸影响
        avatar = AvatarWidget(username=sender, avatar_key=avatar_key,
                              size=38)

        # 气泡 + 时间列
        col = QVBoxLayout()
        col.setSpacing(4)

        # 水平对齐：自己右对齐，对方左对齐
        h_align = Qt.AlignRight if is_mine else Qt.AlignLeft

        # 发送者名（仅对方消息）
        if not is_mine and sender:
            sender_lbl = QLabel(sender)
            sender_lbl.setStyleSheet(f"""
                QLabel {{
                    font-size: 12px;
                    color: {TEXT_SECONDARY};
                    background: transparent;
                    border: none;
                    padding: 0 4px;
                }}
            """)
            col.addWidget(sender_lbl, 0, h_align)

        # 气泡 — 对齐到正确的一侧，不拉伸填充列宽
        bubble = BubbleWidget(text=content, is_mine=is_mine)
        col.addWidget(bubble, 0, h_align)

        # 时间
        time_lbl = QLabel(timestamp)
        time_lbl.setAlignment(Qt.AlignRight if is_mine else Qt.AlignLeft)
        time_lbl.setStyleSheet(f"""
            QLabel {{
                font-size: 11px;
                color: {TEXT_HINT};
                background: transparent;
                border: none;
                padding: 0 4px;
            }}
        """)
        col.addWidget(time_lbl, 0, h_align)

        # 装配 — 左右镜像对称：stretch 在气泡反面
        # 头像顶部对齐（参考 QQ 设计）
        if is_mine:
            root.addStretch()
            root.addLayout(col)
            root.addWidget(avatar, 0, Qt.AlignTop)
        else:
            root.addWidget(avatar, 0, Qt.AlignTop)
            root.addLayout(col)
            root.addStretch()


# =============================================================================
# 文件卡片
# =============================================================================

# 文件类型 → emoji 映射
_FILE_ICONS = {
    ".pdf": "📄",
    ".doc": "📝", ".docx": "📝",
    ".xls": "📊", ".xlsx": "📊",
    ".ppt": "📽️", ".pptx": "📽️",
    ".zip": "📦", ".rar": "📦", ".7z": "📦", ".tar": "📦", ".gz": "📦",
    ".mp3": "🎵", ".wav": "🎵", ".ogg": "🎵", ".m4a": "🎵", ".flac": "🎵",
    ".mp4": "🎬", ".avi": "🎬", ".mkv": "🎬", ".mov": "🎬",
    ".jpg": "🖼️", ".jpeg": "🖼️", ".png": "🖼️", ".gif": "🖼️", ".bmp": "🖼️",
    ".py": "💻", ".js": "💻", ".ts": "💻", ".java": "💻",
    ".html": "💻", ".css": "💻", ".cpp": "💻", ".c": "💻",
    ".txt": "📃",
}


def _format_size(size_bytes):
    """将字节数格式化为可读字符串。"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _file_icon(file_name):
    _, ext = os.path.splitext(file_name or "")
    return _FILE_ICONS.get(ext.lower(), "📎")


class _FileCard(QWidget):
    """文件卡片气泡容器 — 图标 + 文件名 + 大小。"""

    MAX_W = 300
    PAD = 12

    def __init__(self, file_name="", file_size=0, is_mine=True, parent=None):
        super().__init__(parent)
        self._is_mine = is_mine

        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        self.setMaximumWidth(self.MAX_W)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(self.PAD, self.PAD, self.PAD, self.PAD)
        layout.setSpacing(10)

        # 文件图标
        icon_lbl = QLabel(_file_icon(file_name))
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("""
            QLabel {
                font-size: 28px;
                background: rgba(0,0,0,0.06);
                border-radius: 8px;
                border: none;
            }
        """)
        layout.addWidget(icon_lbl)

        # 文件信息
        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        # 文件名（最多两行）
        name_lbl = QLabel(file_name)
        name_lbl.setWordWrap(True)
        name_lbl.setMaximumWidth(self.MAX_W - 80)
        fg = "#ffffff" if is_mine else TEXT_PRIMARY
        name_lbl.setStyleSheet(f"""
            QLabel {{
                font-size: 14px;
                font-weight: 500;
                color: {fg};
                background: transparent;
                border: none;
            }}
        """)
        info_col.addWidget(name_lbl)

        # 文件大小
        hint_fg = "rgba(255,255,255,0.7)" if is_mine else TEXT_HINT
        size_text = _format_size(file_size) if file_size > 0 else ""
        size_lbl = QLabel(size_text)
        size_lbl.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                color: {hint_fg};
                background: transparent;
                border: none;
            }}
        """)
        info_col.addWidget(size_lbl)

        layout.addLayout(info_col, 1)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        if w < 8 or h < 8:
            return

        r = RADIUS_BUBBLE
        s = BUBBLE_CORNER_SMALL

        p.setPen(Qt.NoPen)
        bg = QColor(PRIMARY) if self._is_mine else QColor(BG_MSG_OTHER)
        p.setBrush(bg)

        p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        if self._is_mine:
            p.drawRect(QRectF(w - r, h - s, r, s))
            p.drawRect(QRectF(w - s, h - r, s, r))
        else:
            p.drawRect(QRectF(0, h - s, r, s))
            p.drawRect(QRectF(0, h - r, s, r))

        p.end()


class FileBubbleWidget(QWidget):
    """文件消息行：头像 + 发送者名 + 文件卡片 + 时间戳。"""

    def __init__(self, file_name="", file_size=0, is_mine=False,
                 sender="", timestamp="", avatar_key="", parent=None):
        super().__init__(parent)
        self.initUI(file_name, file_size, is_mine, sender, timestamp, avatar_key)

    def initUI(self, file_name, file_size, is_mine, sender, timestamp, avatar_key):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        avatar = AvatarWidget(username=sender, avatar_key=avatar_key,
                              size=38)

        col = QVBoxLayout()
        col.setSpacing(4)

        h_align = Qt.AlignRight if is_mine else Qt.AlignLeft

        if not is_mine and sender:
            sender_lbl = QLabel(sender)
            sender_lbl.setStyleSheet(f"""
                QLabel {{
                    font-size: 12px;
                    color: {TEXT_SECONDARY};
                    background: transparent;
                    border: none;
                    padding: 0 4px;
                }}
            """)
            col.addWidget(sender_lbl, 0, h_align)

        card = _FileCard(file_name=file_name, file_size=file_size,
                         is_mine=is_mine)
        col.addWidget(card, 0, h_align)

        if timestamp:
            time_lbl = QLabel(timestamp)
            time_lbl.setAlignment(Qt.AlignRight if is_mine else Qt.AlignLeft)
            time_lbl.setStyleSheet(f"""
                QLabel {{
                    font-size: 11px;
                    color: {TEXT_HINT};
                    background: transparent;
                    border: none;
                    padding: 0 4px;
                }}
            """)
            col.addWidget(time_lbl, 0, h_align)

        if is_mine:
            root.addStretch()
            root.addLayout(col)
            root.addWidget(avatar)
        else:
            root.addWidget(avatar)
            root.addLayout(col)
            root.addStretch()


class SystemMessageWidget(QWidget):
    """居中系统消息。"""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                color: {TEXT_HINT};
                background: transparent;
                border: none;
                padding: 4px 0;
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)
        self.setLayout(layout)


class _ImageBubble(QWidget):
    """图片内容的气泡容器 — 与 BubbleWidget 使用相同的不对称圆角绘制逻辑。"""

    MAX_W = 320
    MAX_H = 240
    PAD = 8  # 气泡内边距

    def __init__(self, image_path="", is_mine=True, parent=None):
        super().__init__(parent)
        self._is_mine = is_mine

        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)

        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(self.MAX_W, self.MAX_H,
                                   Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)

        self._img_label = QLabel()
        self._img_label.setAlignment(Qt.AlignCenter)
        self._img_label.setScaledContents(False)
        self._img_label.setStyleSheet("""
            QLabel {
                background: transparent;
                border: none;
            }
        """)
        if not pixmap.isNull():
            self._img_label.setPixmap(pixmap)
            self._img_label.setFixedSize(pixmap.size())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(self.PAD, self.PAD, self.PAD, self.PAD)
        layout.addWidget(self._img_label)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        if w < 8 or h < 8:
            return

        r = RADIUS_BUBBLE
        s = BUBBLE_CORNER_SMALL

        p.setPen(Qt.NoPen)
        bg = QColor(PRIMARY) if self._is_mine else QColor(BG_MSG_OTHER)
        p.setBrush(bg)

        # 全圆角
        p.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # 不对称角遮罩
        if self._is_mine:
            p.drawRect(QRectF(w - r, h - s, r, s))
            p.drawRect(QRectF(w - s, h - r, s, r))
        else:
            p.drawRect(QRectF(0, h - s, r, s))
            p.drawRect(QRectF(0, h - r, s, r))

        p.end()


class ImageBubbleWidget(QWidget):
    """图片消息行：头像 + 发送者名 + 图片气泡 + 时间戳。
    与 MessageBubbleWidget 保持一致的布局结构。"""

    def __init__(self, image_path="", is_mine=False, sender="", timestamp="",
                 avatar_key="", parent=None):
        super().__init__(parent)
        self.initUI(image_path, is_mine, sender, timestamp, avatar_key)

    def initUI(self, image_path, is_mine, sender, timestamp, avatar_key):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        # 头像
        avatar = AvatarWidget(username=sender, avatar_key=avatar_key,
                              size=38)

        # 气泡 + 时间列
        col = QVBoxLayout()
        col.setSpacing(4)

        h_align = Qt.AlignRight if is_mine else Qt.AlignLeft

        # 发送者名（仅对方消息）
        if not is_mine and sender:
            sender_lbl = QLabel(sender)
            sender_lbl.setStyleSheet(f"""
                QLabel {{
                    font-size: 12px;
                    color: {TEXT_SECONDARY};
                    background: transparent;
                    border: none;
                    padding: 0 4px;
                }}
            """)
            col.addWidget(sender_lbl, 0, h_align)

        # 图片气泡
        bubble = _ImageBubble(image_path=image_path, is_mine=is_mine)
        col.addWidget(bubble, 0, h_align)

        # 时间
        if timestamp:
            time_lbl = QLabel(timestamp)
            time_lbl.setAlignment(Qt.AlignRight if is_mine else Qt.AlignLeft)
            time_lbl.setStyleSheet(f"""
                QLabel {{
                    font-size: 11px;
                    color: {TEXT_HINT};
                    background: transparent;
                    border: none;
                    padding: 0 4px;
                }}
            """)
            col.addWidget(time_lbl, 0, h_align)

        # 装配 — 左右镜像对称
        if is_mine:
            root.addStretch()
            root.addLayout(col)
            root.addWidget(avatar)
        else:
            root.addWidget(avatar)
            root.addLayout(col)
            root.addStretch()
