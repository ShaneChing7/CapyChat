"""聊天区组件：头部 + 消息列表 + 工具栏 + 输入框。"""

import os
from datetime import datetime, timedelta

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QTextEdit, QFrame, QSizePolicy)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QKeyEvent

from .theme import (BG_APP, BG_SIDEBAR, BG_INPUT, BORDER, BORDER_LIGHT,
                    PRIMARY, PRIMARY_DARK, TEXT_PRIMARY, TEXT_SECONDARY,
                    TEXT_HINT, GREEN_ONLINE, RADIUS_BUBBLE, RADIUS_XS)
from .message_list import MessageListWidget
from .message_bubble import (MessageBubbleWidget, SystemMessageWidget,
                               BubbleWidget, ImageBubbleWidget, FileBubbleWidget)
from capychat._paths import asset_dir


class ChatAreaWidget(QWidget):
    """完整的聊天区域。

    信号：
        send_message(str)         — 用户点击发送
        send_image()              — 用户点击图片按钮
        send_video()              — 用户点击视频按钮
        send_audio()              — 用户点击音频按钮
        send_file()               — 用户点击文件按钮
        emoji_picker_requested()  — 用户点击表情按钮
    """

    send_message_signal = Signal(str)
    send_image_signal = Signal()
    send_video_signal = Signal()
    send_audio_signal = Signal()
    send_file_signal = Signal()
    emoji_picker_signal = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._icon_dir = asset_dir('icons')
        self._channel_id = "group"
        self._online_count = 0
        self._channel_title = "广场"
        self._last_msg_dt: datetime | None = None
        self.initUI()

    def initUI(self):
        self.setStyleSheet(f"""
            ChatAreaWidget {{
                background-color: {BG_APP};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ================================================================
        # 聊天头部
        # ================================================================
        self._header = QWidget()
        self._header.setFixedHeight(54)
        self._header.setStyleSheet(f"""
            QWidget {{
                background: transparent;
                border-bottom: 0.5px solid {BORDER_LIGHT};
            }}
        """)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(20, 0, 20, 0)

        self._header_title = QLabel(self._channel_title)
        self._header_title.setStyleSheet(f"""
            QLabel {{
                font-size: 18px;
                font-weight: 700;
                color: {TEXT_PRIMARY};
                background: transparent;
                border: none;
            }}
        """)
        header_layout.addWidget(self._header_title, 0, Qt.AlignVCenter)
        header_layout.addStretch()

        # 在线状态
        self._online_dot = QLabel()
        self._online_dot.setFixedSize(8, 8)
        self._online_dot.setStyleSheet(f"""
            QLabel {{
                background-color: {GREEN_ONLINE};
                border-radius: 4px;
                border: none;
            }}
        """)
        header_layout.addWidget(self._online_dot)
        header_layout.addSpacing(4)

        self._online_label = QLabel("0 人在线")
        self._online_label.setStyleSheet(f"""
            QLabel {{
                font-size: 13px;
                color: {TEXT_HINT};
                background: transparent;
                border: none;
            }}
        """)
        header_layout.addWidget(self._online_label)

        layout.addWidget(self._header)

        # ================================================================
        # 消息列表
        # ================================================================
        self.message_list = MessageListWidget()
        layout.addWidget(self.message_list, 1)

        # ================================================================
        # 工具栏
        # ================================================================
        toolbar = QWidget()
        toolbar.setStyleSheet(f"""
            QWidget {{
                background: transparent;
                border-top: 0.5px solid {BORDER_LIGHT};
            }}
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 6, 16, 4)
        toolbar_layout.setSpacing(4)

        btn_style = f"""
            QPushButton {{
                width: 36px;
                height: 36px;
                border: 0.5px solid {BORDER_LIGHT};
                border-radius: {RADIUS_XS}px;
                background: transparent;
                font-size: 20px;
            }}
            QPushButton:hover {{
                background: {BG_INPUT};
            }}
        """

        def _mk_btn(icon_file, tooltip, signal):
            btn = QPushButton()
            icon_path = os.path.join(self._icon_dir, icon_file)
            if os.path.exists(icon_path):
                btn.setIcon(QIcon(icon_path))
                btn.setIconSize(QSize(22, 22))
            else:
                btn.setText(tooltip[0])
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(signal.emit)
            return btn

        self._img_btn = _mk_btn("image.svg", "发送图片",
                                self.send_image_signal)
        self._vid_btn = _mk_btn("video.svg", "发送视频",
                                self.send_video_signal)
        self._aud_btn = _mk_btn("audio.svg", "发送音频",
                                self.send_audio_signal)
        self._file_btn = _mk_btn("file.svg", "发送文件",
                                 self.send_file_signal)
        self._emoji_btn = _mk_btn("smile.svg", "选择表情",
                                  self.emoji_picker_signal)

        toolbar_layout.addWidget(self._img_btn)
        toolbar_layout.addWidget(self._vid_btn)
        toolbar_layout.addWidget(self._aud_btn)
        toolbar_layout.addWidget(self._file_btn)
        toolbar_layout.addWidget(self._emoji_btn)
        toolbar_layout.addStretch()

        layout.addWidget(toolbar)

        # ================================================================
        # 输入 + 发送
        # ================================================================
        input_row = QWidget()
        input_row.setStyleSheet("background: transparent;")
        input_row_layout = QHBoxLayout(input_row)
        input_row_layout.setContentsMargins(16, 0, 16, 14)
        input_row_layout.setSpacing(10)

        self._input = QTextEdit()
        self._input.setPlaceholderText("请输入消息...")
        self._input.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._input.setSizePolicy(QSizePolicy.Expanding,
                                  QSizePolicy.Preferred)
        self._input.document().setDocumentMargin(6)
        self._input.setStyleSheet(f"""
            QTextEdit {{
                background-color: {BG_INPUT};
                border: 0.5px solid {BORDER};
                border-radius: {RADIUS_BUBBLE // 2 + 4}px;
                padding: 6px 14px;
                font-size: 15px;
                color: {TEXT_PRIMARY};
            }}
            QTextEdit:focus {{
                border: 0.5px solid {PRIMARY};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER};
                border-radius: 2px;
            }}
        """)
        # Enter 发送，Shift+Enter 换行
        self._input.installEventFilter(self)
        # 自适应高度
        self._input.document().documentLayout().documentSizeChanged.connect(
            self._adjust_input_height)
        input_row_layout.addWidget(self._input, 1)

        self._send_btn = QPushButton("发送")
        self._send_btn.setCursor(Qt.PointingHandCursor)
        self._send_btn.setFixedSize(78, self._MIN_HEIGHT)
        self._send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {PRIMARY};
                color: #ffffff;
                border: none;
                border-radius: {RADIUS_XS + 2}px;
                font-size: 15px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {PRIMARY_DARK};
            }}
            QPushButton:pressed {{
                background-color: #A85A40;
            }}
        """)
        self._send_btn.clicked.connect(self._on_send)
        input_row_layout.addWidget(self._send_btn, 0, Qt.AlignBottom)

        layout.addWidget(input_row)

        self.setLayout(layout)

    # ==================================================================
    # Event filter — Enter 发送，Shift+Enter 换行
    # ==================================================================

    def eventFilter(self, obj, event):
        if obj == self._input and event.type() == QKeyEvent.KeyPress:
            if (event.key() == Qt.Key_Return or
                    event.key() == Qt.Key_Enter):
                if not (event.modifiers() & Qt.ShiftModifier):
                    self._on_send()
                    return True
        return super().eventFilter(obj, event)

    # ==================================================================
    # 自适应输入框高度
    # ==================================================================

    _MIN_HEIGHT = 54
    _MAX_LINES = 6

    def _adjust_input_height(self):
        """根据文档实际内容高度自适应调整输入框高度，最多 _MAX_LINES 行。"""
        doc = self._input.document()
        doc_h = doc.size().height()

        margins = (self._input.contentsMargins().top()
                   + self._input.contentsMargins().bottom())
        new_h = int(doc_h + margins + 8)

        fm = self._input.fontMetrics()
        max_h = fm.height() * self._MAX_LINES + margins + 16

        clamped = max(self._MIN_HEIGHT, min(new_h, max_h))
        self._input.setFixedHeight(clamped)

    # ==================================================================
    # Public API
    # ==================================================================

    def set_channel(self, channel_id, title="广场"):
        """切换频道。"""
        self._channel_id = channel_id
        self._channel_title = title
        self._header_title.setText(title)
        # 私聊 / Capybara 时隐藏在线状态
        is_group = (channel_id == "group")
        self._online_dot.setVisible(is_group)
        self._online_label.setVisible(is_group)
        # 切换背景
        if channel_id == "capybara":
            self.message_list.set_bg_type("single")
        else:
            self.message_list.set_bg_type("group" if is_group else "single")
        # Capybara 频道时隐藏媒体按钮，替换提示文字
        is_ai = (channel_id == "capybara")
        self._img_btn.setVisible(not is_ai)
        self._vid_btn.setVisible(not is_ai)
        self._aud_btn.setVisible(not is_ai)
        self._file_btn.setVisible(not is_ai)
        if is_ai:
            self._input.setPlaceholderText("和 Capybara 聊天...")
        else:
            self._input.setPlaceholderText("请输入消息...")

    def set_online_count(self, count):
        """更新在线人数。"""
        self._online_count = count
        self._online_label.setText(f"{count} 人在线")
        self._online_dot.setVisible(count > 0)

    def add_system_msg(self, text):
        """添加系统消息。"""
        self.message_list.add_system_msg(text)

    def add_message(self, sender, content, timestamp, is_mine=False,
                    avatar=""):
        """添加用户消息气泡。"""
        self._maybe_add_time_divider()
        bubble = MessageBubbleWidget(
            sender=sender, content=content,
            timestamp=timestamp, is_mine=is_mine,
            avatar_key=avatar)
        self.message_list.add_message(bubble)

    def add_image(self, image_path, is_mine=False, sender="", timestamp="",
                  avatar=""):
        """添加图片消息。"""
        self._maybe_add_time_divider()
        bubble = ImageBubbleWidget(
            image_path=image_path, is_mine=is_mine,
            sender=sender, timestamp=timestamp,
            avatar_key=avatar)
        self.message_list.add_message(bubble)

    def add_file_card(self, file_name, file_size=0, is_mine=False,
                      sender="", timestamp="", avatar=""):
        """添加文件卡片消息。"""
        self._maybe_add_time_divider()
        bubble = FileBubbleWidget(
            file_name=file_name, file_size=file_size, is_mine=is_mine,
            sender=sender, timestamp=timestamp,
            avatar_key=avatar)
        self.message_list.add_message(bubble)

    def clear_messages(self):
        """清空消息列表。"""
        self.message_list.clear()
        self._last_msg_dt = None

    def insert_emoji(self, emoji):
        """在输入框光标处插入表情。"""
        cursor = self._input.textCursor()
        cursor.insertText(emoji)
        self._input.setFocus()

    def focus_input(self):
        """聚焦输入框。"""
        self._input.setFocus()

    # ==================================================================
    # Private
    # ==================================================================

    _DIVIDER_GAP = timedelta(minutes=5)

    def _maybe_add_time_divider(self):
        """相邻消息间隔超过阈值时插入时间分割线。"""
        now = datetime.now()
        if self._last_msg_dt is not None and now - self._last_msg_dt >= self._DIVIDER_GAP:
            label = self._format_divider(now)
            self.message_list.add_system_msg(label)
        self._last_msg_dt = now

    @staticmethod
    def _format_divider(dt: datetime) -> str:
        now = datetime.now()
        if dt.date() == now.date():
            return f"今天 {dt.strftime('%H:%M')}"
        yesterday = now - timedelta(days=1)
        if dt.date() == yesterday.date():
            return f"昨天 {dt.strftime('%H:%M')}"
        if dt.year == now.year:
            return dt.strftime('%m-%d %H:%M')
        return dt.strftime('%Y-%m-%d %H:%M')

    def _on_send(self):
        text = self._input.toPlainText().strip()
        if text:
            self.send_message_signal.emit(text)
            self._input.clear()
            self._input.setFocus()
