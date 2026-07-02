"""CapybaraWidget — 带动画的卡皮巴拉 AI 助手卡片。

支持三种状态：
  IDLE       — 睁眼 + 每 5 秒随机眨眼
  THINKING   — 3 帧思考动画循环
  RESPONDING — 与 THINKING 视觉一致（流式输出阶段）

动画：
  - 眨眼：闭眼 120ms → 睁眼
  - 思考：3 帧 PNG 循环（300ms/帧）
"""

import os
from enum import Enum

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QPixmap

from .theme import BORDER, TEXT_PRIMARY, BG_APP
from capychat._paths import asset_dir


_IMG_DIR = asset_dir('images', 'capybara')


class CapybaraState(Enum):
    IDLE = 0
    THINKING = 1
    RESPONDING = 2


class CapybaraWidget(QWidget):
    """卡皮巴拉 AI 助手卡片 — 带动画的状态机。"""

    clicked = Signal()
    settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = CapybaraState.IDLE
        self._frame_index = 0

        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(56)
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

        # 图片资源
        self.open_pixmap = self._load("capybara_open.png", 36)
        self.close_pixmap = self._load("capybara_close.png", 36)
        self.thinking_frames = [
            self._load(f"capybara_thinking_{i}.png", 40)
            for i in (1, 2, 3)
        ]

        self._init_ui()

        # 眨眼定时器（IDLE 时每 5 秒）
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink)
        self._blink_timer.start(5000)

        # 思考帧定时器（300ms）
        self._thinking_timer = QTimer(self)
        self._thinking_timer.timeout.connect(self._next_think_frame)
        self._thinking_timer.setInterval(300)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        self.setStyleSheet("""
            CapybaraWidget {
                background: transparent;
                border: none;
                border-radius: 8px;
            }
            CapybaraWidget:hover {
                background: rgba(200,120,90,0.08);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        # 文字在左
        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        self._name = QLabel("Capybara")
        self._name.setStyleSheet("""
            QLabel {
                font-size: 14px;
                font-weight: bold;
                color: #3A3028;
                background: transparent;
                border: none;
            }
        """)
        text_col.addWidget(self._name)

        self._hint = QLabel("卡皮巴拉 AI 助手")
        self._hint.setStyleSheet("""
            QLabel {
                font-size: 11px; color: #B0A49A;
                background: transparent; border: none;
            }
        """)
        text_col.addWidget(self._hint)

        layout.addLayout(text_col, 1)

        # 头像在右
        self._avatar = QLabel()
        self._avatar.setFixedSize(40, 40)
        self._avatar.setAlignment(Qt.AlignCenter)
        self._avatar.setStyleSheet("background: transparent; border: none;")
        if self.open_pixmap:
            self._avatar.setPixmap(self.open_pixmap)
        layout.addWidget(self._avatar)

    # ------------------------------------------------------------------
    # 状态切换
    # ------------------------------------------------------------------

    def set_thinking(self, thinking: bool) -> None:
        """True → THINKING（启动思考帧动画）。
           False → IDLE（停止动画，恢复眨眼）。"""
        if thinking:
            self.state = CapybaraState.THINKING
            self._hint.setText("思考中...")
            self._blink_timer.stop()
            self._thinking_timer.start()
        else:
            self.state = CapybaraState.IDLE
            self._hint.setText("卡皮巴拉 AI 助手")
            self._thinking_timer.stop()
            self._frame_index = 0
            if self.open_pixmap:
                self._avatar.setPixmap(self.open_pixmap)
            self._blink_timer.start()

    # ------------------------------------------------------------------
    # 眨眼
    # ------------------------------------------------------------------

    def _blink(self):
        if self.state != CapybaraState.IDLE:
            return
        if self.close_pixmap:
            self._avatar.setPixmap(self.close_pixmap)
        QTimer.singleShot(120, self._open_eyes)

    def _open_eyes(self):
        if self.state == CapybaraState.IDLE and self.open_pixmap:
            self._avatar.setPixmap(self.open_pixmap)

    # ------------------------------------------------------------------
    # 思考帧
    # ------------------------------------------------------------------

    def _next_think_frame(self):
        if not self.thinking_frames:
            return
        self._frame_index = (self._frame_index + 1) % len(self.thinking_frames)
        self._avatar.setPixmap(self.thinking_frames[self._frame_index])

    # ------------------------------------------------------------------
    # 点击
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout, QApplication
        from PySide6.QtGui import QIcon
        from PySide6.QtCore import QTimer

        _icons_dir = asset_dir('icons')

        popup = QFrame()
        popup.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint
                           | Qt.NoDropShadowWindowHint)
        popup.setAttribute(Qt.WA_TranslucentBackground)
        popup.setFixedSize(150, 42)
        popup.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(popup)
        layout.setContentsMargins(0, 0, 0, 0)

        btn = QPushButton("  设置")
        bolt_path = os.path.join(_icons_dir, "bolt.svg")
        if os.path.exists(bolt_path):
            btn.setIcon(QIcon(bolt_path))
            btn.setIconSize(QSize(16, 16))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                padding: 10px 16px;
                border: 0.5px solid {BORDER};
                border-radius: 10px;
                font-size: 13px;
                color: {TEXT_PRIMARY};
                background: {BG_APP};
                text-align: left;
            }}
            QPushButton:hover {{
                background: rgba(200,120,90,0.10);
                border-color: #D4B8A8;
            }}
        """)
        btn.clicked.connect(lambda: (self.settings_requested.emit(),
                                      popup.close()))
        layout.addWidget(btn)

        popup.move(event.globalPos())
        popup.show()

        # 失焦自动关闭
        def _close_if_needed():
            if not popup.isVisible():
                return
            if QApplication.activePopupWidget() != popup:
                popup.close()
        QTimer.singleShot(50, _close_if_needed)

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    def _load(self, filename: str, size: int) -> QPixmap | None:
        path = os.path.join(_IMG_DIR, filename)
        if os.path.exists(path):
            return QPixmap(path).scaled(
                size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return None
