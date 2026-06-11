"""消息列表 — 可滚动的消息容器，自动滚动到底部，支持视口固定背景水印。

私聊使用 bg_single.png，群聊使用 bg_group.png。
"""

import os

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QScrollArea,
                               QSizePolicy)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QPixmap

from .message_bubble import (SystemMessageWidget, MessageBubbleWidget,
                               BubbleWidget)


# 背景图片目录
_BG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "images", "backgrounds")

_BG_FILES = {
    "single": os.path.join(_BG_DIR, "bg_single.png"),
    "group":  os.path.join(_BG_DIR, "bg_group.png"),
}


class _BgScrollArea(QScrollArea):
    """带固定背景水印的滚动区域 — 在视口上绘制，不随消息滚动。"""

    def __init__(self, bg_type: str = "group", parent=None):
        super().__init__(parent)
        self._bg_pixmap: QPixmap | None = None
        bg_path = _BG_FILES.get(bg_type, "")
        if bg_path and os.path.exists(bg_path):
            self._bg_pixmap = QPixmap(bg_path)
        self.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.viewport() and event.type() == event.Type.Paint:
            self._draw_bg()
        return super().eventFilter(obj, event)

    def _draw_bg(self):
        """在视口上直接绘制背景水印。"""
        if not self._bg_pixmap or self._bg_pixmap.isNull():
            return
        vp = self.viewport()
        w, h = vp.width(), vp.height()
        if w < 1 or h < 1:
            return

        p = QPainter(vp)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        scaled = self._bg_pixmap.scaled(
            w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        ox = (w - scaled.width()) // 2
        oy = (h - scaled.height() - 100) // 2 - 10

        p.setOpacity(0.1)
        p.drawPixmap(ox, oy, scaled)
        p.end()


class MessageListWidget(QWidget):
    """可滚动的消息列表。

    bg_type: "group" 用群聊背景，"single" 用私聊背景。

    用法：
        msg_list = MessageListWidget(bg_type="group")
        msg_list.add_system_msg("欢迎来到广场")
        msg_list.add_message(bubble_widget)
        msg_list.clear()
    """

    def __init__(self, bg_type: str = "group", parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._scroll_area = _BgScrollArea(bg_type=bg_type)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded)
        self._scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 5px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #d0c8c0;
                border-radius: 2px;
                min-height: 30px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._msg_layout = QVBoxLayout(self._container)
        self._msg_layout.setSpacing(14)
        self._msg_layout.setContentsMargins(22, 18, 22, 18)
        self._msg_layout.setAlignment(Qt.AlignTop)
        self._msg_layout.addStretch()

        self._scroll_area.setWidget(self._container)
        layout.addWidget(self._scroll_area)

        self._scroll_area.verticalScrollBar().rangeChanged.connect(
            self._auto_scroll)

        self.setLayout(layout)

    # ==================================================================
    # Public API
    # ==================================================================

    def add_system_msg(self, text):
        w = SystemMessageWidget(text)
        self._insert_before_stretch(w)

    def add_message(self, bubble_widget):
        self._insert_before_stretch(bubble_widget)

    def set_bg_type(self, bg_type: str) -> None:
        """切换背景图：\"group\" -> bg_group.png，\"single\" -> bg_single.png。"""
        bg_path = _BG_FILES.get(bg_type, "")
        if bg_path and os.path.exists(bg_path):
            self._scroll_area._bg_pixmap = QPixmap(bg_path)
        self._scroll_area.viewport().update()

    # ==================================================================
    # 流式输出（Capybara AI）
    # ==================================================================

    def start_stream(self, sender: str, avatar_key: str, timestamp: str):
        """开始流式输出 — 立即创建带头像的气泡占位，避免后续抖动。"""
        self.finish_stream()  # 清理上一个流（如果有）
        self._stream_bubble = MessageBubbleWidget(
            sender=sender, content="", timestamp=timestamp,
            is_mine=False, avatar_key=avatar_key)
        self._insert_before_stretch(self._stream_bubble)
        self._stream_text = ""

    def append_stream(self, text: str):
        """流式追加 token — 更新气泡内文字。"""
        if not hasattr(self, '_stream_bubble') or self._stream_bubble is None:
            return
        self._stream_text += text
        # 找到内层 BubbleWidget 并更新文字
        bubble = self._find_bubble_widget(self._stream_bubble)
        if bubble:
            bubble.set_text(self._stream_text)
        self._auto_scroll()

    def finish_stream(self):
        """结束流式输出（气泡已占位，清理流状态即可）。"""
        self._stream_bubble = None
        self._stream_text = ""

    @staticmethod
    def _find_bubble_widget(root: QWidget):
        """从 MessageBubbleWidget 中找到内层 BubbleWidget。"""
        for child in root.findChildren(BubbleWidget):
            return child
        return None

    def clear(self):
        self.finish_stream()
        while self._msg_layout.count() > 1:
            item = self._msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    # ==================================================================
    # Private
    # ==================================================================

    def _insert_before_stretch(self, widget):
        count = self._msg_layout.count()
        self._msg_layout.insertWidget(count - 1, widget)

    def _auto_scroll(self):
        sb = self._scroll_area.verticalScrollBar()
        sb.setValue(sb.maximum())
