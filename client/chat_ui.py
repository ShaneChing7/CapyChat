"""聊天主界面 — ChatWindow 纯 View 层。

业务逻辑已抽离至 controller.py 的 ChatController。
ChatWindow 仅负责：窗口渲染、布局、阴影、拖动、关闭确认。
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                               QStackedWidget, QMessageBox,
                               QFrame, QScrollArea, QProgressBar,
                               QPushButton, QLabel)
from PySide6.QtCore import Qt, QTimer, QRectF, Signal
from PySide6.QtGui import QPainter, QColor

from network.protocol import format_size, format_speed, format_time

from ui.theme import (BG_APP, BG_HOVER, BORDER, TEXT_PRIMARY, TEXT_SECONDARY,
                      TEXT_HINT, PRIMARY, PRIMARY_DARK, GREEN_ONLINE,
                      RADIUS_WINDOW, RADIUS_XS, SHADOW_MARGIN)
from ui.sidebar import SidebarWidget
from ui.chat_area import ChatAreaWidget


# =============================================================================
# 文件传输进度栏（内嵌在侧边栏底部）
# =============================================================================

class _ProgressBar(QWidget):
    cancelled = Signal()

    def __init__(self, file_name="", file_size=0):
        super().__init__()
        self.file_name = file_name
        self.file_size = file_size
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(6, 5, 6, 5)

        info = QHBoxLayout()
        name = QLabel(self.file_name)
        name.setStyleSheet(f"font-size: 12px; color: {TEXT_PRIMARY}; background: transparent;")
        info.addWidget(name)
        info.addStretch()
        cancel = QPushButton("✕")
        cancel.setFixedSize(18, 18)
        cancel.setStyleSheet(f"""
            QPushButton {{ border: none; color: {TEXT_HINT}; font-size: 11px; background: transparent; }}
            QPushButton:hover {{ color: {PRIMARY}; }}
        """)
        cancel.clicked.connect(self.cancelled.emit)
        info.addWidget(cancel)
        layout.addLayout(info)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(True)
        self._bar.setFixedHeight(14)
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                border: 0.5px solid {BORDER};
                border-radius: 3px;
                background: transparent;
                font-size: 10px;
                color: {TEXT_SECONDARY};
            }}
            QProgressBar::chunk {{ background: {PRIMARY}; border-radius: 2px; }}
        """)
        layout.addWidget(self._bar)

        stats = QHBoxLayout()
        self._speed = QLabel("--")
        self._eta = QLabel("--")
        for lbl in (self._speed, self._eta):
            lbl.setStyleSheet(f"font-size: 10px; color: {TEXT_HINT}; background: transparent;")
        stats.addWidget(self._speed)
        stats.addStretch()
        stats.addWidget(self._eta)
        layout.addLayout(stats)
        self.setLayout(layout)

    def update_progress(self, p):
        pct = int(p.received_bytes / max(p.file_size, 1) * 100)
        self._bar.setValue(pct)
        self._bar.setFormat(f"{format_size(p.received_bytes)}/{format_size(p.file_size)}")
        self._speed.setText(format_speed(p.speed))
        self._eta.setText(f"剩余:{format_time(p.eta_seconds)}")

    def set_done(self):
        self._bar.setValue(100)
        self._speed.setText("完成")
        self._eta.setText("")

    def set_error(self, msg=""):
        self._speed.setText(msg or "失败")
        self._eta.setText("")


# =============================================================================
# ChatWindow — 纯 View 层
# =============================================================================

class ChatWindow(QWidget):
    """聊天主窗口。

    业务逻辑由 ChatController 处理，通过 controller 属性访问。
    chat_areas / chat_stack / sidebar / current_channel 为公开属性，
    供 Controller 层读写。
    """

    def __init__(self, username="", local_ip="", tcp_port=0,
                 udp=None, tcp=None, avatar=""):
        super().__init__()
        self.username = username
        self.local_ip = local_ip
        self.tcp_port = tcp_port

        # 公开属性 — Controller 层访问
        self.chat_areas: dict[str, ChatAreaWidget] = {}
        self.current_channel = "group"

        # 私有
        self._drag_pos = None
        self._udp = udp
        self._tcp = tcp

        # 主聊天区栈
        self.chat_stack = QStackedWidget()

        # 控制器（在 initUI 构建完 sidebar 后创建）
        self.controller = None
        from controller import ChatController
        self.controller = ChatController(
            window=self, username=username, local_ip=local_ip,
            tcp_port=tcp_port, udp=udp, tcp=tcp, avatar=avatar)

        # 初始广场
        group_area = self.controller.make_chat_area("group", "广场")
        self.chat_stack.addWidget(group_area)

        self.initUI()

        # 侧边栏信号 → Controller
        sidebar = self.sidebar  # initUI 中创建
        sidebar.channel_selected.connect(self.controller.on_channel_selected)
        sidebar.exit_requested.connect(self._logout)
        sidebar.doc_center_requested.connect(self.controller._show_doc_center)
        sidebar.doc_open_requested.connect(self.controller.on_doc_open)
        sidebar.avatar_changed.connect(self.controller.on_avatar_changed)
        sidebar.capybara_widget.settings_requested.connect(
            self.controller._on_capy_settings)

    # ==================================================================
    # 窗口阴影 & 拖动
    # ==================================================================

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(SHADOW_MARGIN, SHADOW_MARGIN,
                      self.width() - SHADOW_MARGIN * 2,
                      self.height() - SHADOW_MARGIN * 2)
        ox, oy = 0, 3
        for i in range(8):
            alpha = int(12 * (1 - i / 8))
            if alpha <= 0:
                continue
            expand = i * 2.5
            r = QRectF(rect.x() + ox - expand, rect.y() + oy - expand,
                       rect.width() + expand * 2,
                       rect.height() + expand * 2)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(r, RADIUS_WINDOW + expand,
                                    RADIUS_WINDOW + expand)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.LeftButton) and self._drag_pos is not None:
            d = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + d)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ==================================================================
    # UI 构建
    # ==================================================================

    def initUI(self):
        self.setWindowTitle("CapyChat")
        self.resize(1020 + SHADOW_MARGIN * 2, 720 + SHADOW_MARGIN * 2)
        self.setMinimumSize(900 + SHADOW_MARGIN * 2,
                            600 + SHADOW_MARGIN * 2)

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.setStyleSheet(f"""
            QWidget {{
                color: {TEXT_PRIMARY};
                font-family: "Segoe UI", "Microsoft YaHei",
                             "PingFang SC", sans-serif;
                font-size: 14px;
            }}
            QToolTip {{
                background-color: #2d2d2d;
                color: #f0f0f0;
                border: 0.5px solid {BORDER};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 13px;
            }}
        """)

        # 外层（阴影空间）
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN,
                                 SHADOW_MARGIN, SHADOW_MARGIN)

        # 窗口容器
        container = QFrame()
        container.setObjectName("window")
        container.setStyleSheet(f"""
            #window {{
                background-color: {BG_APP};
                border-radius: {RADIUS_WINDOW}px;
            }}
        """)
        outer.addWidget(container)

        # 水平分区
        hbox = QHBoxLayout(container)
        hbox.setContentsMargins(0, 0, 0, 0)
        hbox.setSpacing(0)

        # ---- 侧边栏 ----
        self.sidebar = SidebarWidget(
            username=self.username,
            address=f"{self.local_ip}:{self.tcp_port}",
            avatar_key=self.controller.avatar if self.controller else "")
        hbox.addWidget(self.sidebar)

        # ---- 竖向分割线 ----
        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setStyleSheet(f"QFrame {{ background-color: {BORDER}; border: none; }}")
        hbox.addWidget(sep)

        # ---- 聊天区 + 窗口控制 ----
        right = QWidget()
        right.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # 窗口按钮栏
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(0, 8, 8, 0)
        title_bar.addStretch()

        min_btn = QPushButton("─")
        min_btn.setFixedSize(30, 30)
        min_btn.setCursor(Qt.PointingHandCursor)
        min_btn.setToolTip("最小化")
        min_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_SECONDARY};
                           border: none; border-radius: 8px; font-size: 14px; }}
            QPushButton:hover {{ background: {BG_HOVER}; }}
        """)
        min_btn.clicked.connect(self.showMinimized)
        title_bar.addWidget(min_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip("关闭")
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT_SECONDARY};
                           border: none; border-radius: 8px; font-size: 15px; }}
            QPushButton:hover {{ background: {PRIMARY}; color: #fff; }}
        """)
        close_btn.clicked.connect(self.close)
        title_bar.addWidget(close_btn)

        right_layout.addLayout(title_bar)
        right_layout.addWidget(self.chat_stack, 1)
        hbox.addWidget(right, 1)

        self.setLayout(hbox)

    # ==================================================================
    # 退出
    # ==================================================================

    def _logout(self):
        if self.controller:
            self.controller.logout()

    def closeEvent(self, event):
        if self._udp:
            self._udp.stop()
        if self._tcp:
            self._tcp.stop()
        super().closeEvent(event)
