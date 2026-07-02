"""登录/设置界面：配置本地网络参数，启动P2P+UDP通信。"""

import os
import socket
from PySide6.QtWidgets import (QWidget, QLineEdit, QPushButton,
                               QVBoxLayout, QHBoxLayout, QLabel,
                               QMessageBox, QComboBox, QFrame)
from PySide6.QtCore import Qt, QRect, QRectF, QSize
from PySide6.QtGui import QIcon, QPainter, QColor, QPixmap

from network.udp_broadcast import UdpBroadcast
from network.tcp_p2p import TcpP2P
from network.protocol import DEFAULT_UDP_PORT, DEFAULT_TCP_PORT
from network.crypto import derive_key
from views.chat_ui import ChatWindow
from config_manager import load_config, save_config, DEFAULT_CONFIG
from capychat._paths import asset_dir


def _get_local_ips():
    """获取本机所有局域网IP地址"""
    ips = ["127.0.0.1"]
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            ip = info[4][0]
            if ip not in ips and not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    return ips


# ---------------------------------------------------------------------------
# 样式常量 — 温暖浅色主题 (Claude Desktop light)
# ---------------------------------------------------------------------------

# 强调色：暖橙
ACCENT = "#D97757"
ACCENT_HOVER = "#C96A4A"
ACCENT_PRESSED = "#B85038"

# 背景
BG_WINDOW = "#F7F4EF"       # 窗口底色 — 温暖米白
BG_INPUT = "#FAF8F5"        # 输入框底色 — 极淡暖色
BG_INPUT_FOCUS = "#FFFDFA"  # 输入框聚焦 — 近乎纯白

# 边框
BORDER = "#E6E0D8"          # 默认边框 — 暖调浅米
BORDER_FOCUS = ACCENT       # 聚焦边框 — 暖橙
BORDER_HOVER = "#D9D1C7"    # 悬停边框

# 文字
TEXT_PRIMARY = "#2F2A25"    # 主文字 — 深褐黑
TEXT_SECONDARY = "#6F6A65"  # 辅助文字 — 中暖灰
TEXT_MUTED = "#9E9890"      # 淡文字 — 浅暖灰
TEXT_PLACEHOLDER = "#B8B0A8"  # 占位符 — 更淡

# 圆角
RADIUS = 20                 # 窗口/卡片
RADIUS_SM = 10              # 输入框/按钮

# 窗口尺寸
WIN_W = 420
WIN_H = 670
SHADOW_MARGIN = 20  # 窗口阴影边距（需 ≥ blur 扩展范围）


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def _label(text, *, size=12, color=TEXT_SECONDARY):
    """快捷创建装饰性标签（不可交互，鼠标事件穿透）。"""
    lbl = QLabel(text)
    lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    lbl.setStyleSheet(f"""
        QLabel {{
            color: {color};
            font-size: {size}px;
            font-weight: normal;
            background: transparent;
            border: none;
            padding: 0;
            margin: 0;
        }}
    """)
    return lbl


def _input(placeholder="", *, password=False, default_text=""):
    """快捷创建输入框。"""
    inp = QLineEdit()
    inp.setPlaceholderText(placeholder)
    inp.setText(default_text)
    inp.setMinimumHeight(44)
    inp.setStyleSheet(f"""
        QLineEdit {{
            background-color: {BG_INPUT};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_SM}px;
            padding: 0 14px;
            color: {TEXT_PRIMARY};
            font-size: 14px;
        }}
        QLineEdit:focus {{
            border: 1px solid {BORDER_FOCUS};
            background-color: {BG_INPUT_FOCUS};
        }}
        QLineEdit:disabled {{
            color: {TEXT_MUTED};
            background-color: #F3F0EB;
        }}
    """)
    if password:
        inp.setEchoMode(QLineEdit.Password)
    return inp


# ---------------------------------------------------------------------------
# 自定义 QComboBox：用 QIcon 画下拉箭头
# ---------------------------------------------------------------------------

_ICON_DIR = asset_dir('icons')
_CHEVRON_DOWN = QIcon(os.path.join(_ICON_DIR, "chevron-down.svg"))
_CHEVRON_UP = QIcon(os.path.join(_ICON_DIR, "chevron-up.svg"))
_EYE_OPEN = QIcon(os.path.join(_ICON_DIR, "eye.svg"))
_EYE_CLOSED = QIcon(os.path.join(_ICON_DIR, "eye-closed.svg"))


class _Combo(QComboBox):
    """QComboBox 子类 — 用 QIcon 在右侧画 chevron 箭头。"""

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)

        r = QRect(0, 0, 16, 16)
        r.moveCenter(self.rect().center())
        r.moveRight(self.rect().right() - 12)

        icon = _CHEVRON_UP if self.view().isVisible() else _CHEVRON_DOWN
        icon.paint(painter, r)

        painter.end()

def _combo(items=(), *, editable=True):
    """快捷创建下拉框。"""
    combo = _Combo()
    combo.setEditable(editable)
    combo.setMinimumHeight(44)
    for item in items:
        combo.addItem(item)

    combo.setStyleSheet(f"""
        QComboBox {{
            background-color: {BG_INPUT};
            border: 1px solid {BORDER};
            border-radius: {RADIUS_SM}px;
            padding: 0 36px 0 14px;
            color: {TEXT_PRIMARY};
            font-size: 14px;
        }}
        QComboBox:focus {{
            border: 1px solid {BORDER_FOCUS};
        }}
        QComboBox::down-arrow {{
            assets: none;
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
        
            width: 30px;      /* 根据图标位置调整 */
            border: none;
        }}
        QComboBox QAbstractItemView {{
            background-color: #FFFFFF;
            border: 1px solid {BORDER};
            border-radius: 8px;
            color: {TEXT_PRIMARY};
            selection-background-color: {ACCENT};
            selection-color: #ffffff;
            outline: none;
            padding: 4px;
        }}
    """)
    return combo


# ---------------------------------------------------------------------------
# 自定义 QLineEdit：密码可见性切换（眼睛图标）
# ---------------------------------------------------------------------------

class _PasswordLineEdit(QLineEdit):
    """QLineEdit 子类 — 右侧显示眼睛图标，点击切换密码可见性。"""

    def __init__(self, placeholder="", default_text=""):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setText(default_text)
        self.setMinimumHeight(44)
        self.setEchoMode(QLineEdit.Password)
        self._password_visible = False
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_INPUT};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_SM}px;
                padding: 0 36px 0 14px;
                color: {TEXT_PRIMARY};
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border: 1px solid {BORDER_FOCUS};
                background-color: {BG_INPUT_FOCUS};
            }}
            QLineEdit:disabled {{
                color: {TEXT_MUTED};
                background-color: #F3F0EB;
            }}
        """)

    def _icon_rect(self):
        """返回图标绘制区域。"""
        r = QRect(0, 0, 20, 20)
        r.moveCenter(self.rect().center())
        r.moveRight(self.rect().right() - 10)
        return r

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        icon = _EYE_OPEN if self._password_visible else _EYE_CLOSED
        icon.paint(painter, self._icon_rect())
        painter.end()

    def mousePressEvent(self, event):
        if self._icon_rect().contains(event.pos()):
            self._password_visible = not self._password_visible
            if self._password_visible:
                self.setEchoMode(QLineEdit.Normal)
            else:
                self.setEchoMode(QLineEdit.Password)
            self.update()
            return
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# LoginWindow
# ---------------------------------------------------------------------------


class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.chat_window = None
        self._drag_pos = None
        self.initUI()
        self._load_config_to_ui()

    # ====================================================================
    # 窗口拖动
    # ====================================================================

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.LeftButton) and self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ====================================================================
    # 窗口阴影（手动绘制，避免 QGraphicsDropShadowEffect 被圆角裁剪）
    # ====================================================================

    def paintEvent(self, event):
        """在透明边距区域手动绘制柔和阴影。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 内容区域（不含阴影边距）
        content_rect = QRectF(
            SHADOW_MARGIN, SHADOW_MARGIN,
            self.width() - SHADOW_MARGIN * 2,
            self.height() - SHADOW_MARGIN * 2,
        )

        # 多层叠加模拟高斯模糊阴影
        offset_x, offset_y = 0, 3
        layers = 10
        for i in range(layers):
            alpha = int(22 * (1 - i / layers))  # 22 → 0
            if alpha <= 0:
                continue
            expand = i * 2.5  # 每层外扩 2.5px
            rect = QRectF(
                content_rect.x() + offset_x - expand,
                content_rect.y() + offset_y - expand,
                content_rect.width() + expand * 2,
                content_rect.height() + expand * 2,
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(rect, RADIUS + expand, RADIUS + expand)

        painter.end()

    # ====================================================================
    # UI 构建
    # ====================================================================

    def initUI(self):
        self.setWindowTitle("CapyChat · 登录")
        self.setFixedSize(WIN_W + SHADOW_MARGIN * 2, WIN_H + SHADOW_MARGIN * 2)

        # 无边框窗口 + 透明背景（让阴影可见）
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # 全局字体样式（不再设 LoginWindow 背景色）
        self.setStyleSheet(f"""
            QWidget {{
                color: {TEXT_PRIMARY};
                font-family: "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif;
                font-size: 14px;
            }}
        """)

        # ---- 外层布局（留出阴影空间）------------------------------------
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)

        # ---- Logo 图片（背景层，不影响布局）-------------------------------
        self._logo_pixmap: QPixmap | None = None
        logo_path = os.path.join(asset_dir('images', 'logo'), "logo.png")
        if os.path.exists(logo_path):
            self._logo_pixmap = QPixmap(logo_path)

        # ---- 内容容器（带 Logo 背景绘制）-----------------------------------
        class _ContentFrame(QFrame):
            _logo = self._logo_pixmap
            def paintEvent(self, ev):
                super().paintEvent(ev)
                if self._logo and not self._logo.isNull():
                    p = QPainter(self)
                    p.setRenderHint(QPainter.Antialiasing)
                    p.setRenderHint(QPainter.SmoothPixmapTransform)
                    logo_w = min(self.width() * 0.45, 180)
                    scaled = self._logo.scaled(
                        int(logo_w), int(logo_w),
                        Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    ox = (self.width() - scaled.width()) // 2
                    oy = 0
                    p.setOpacity(0.4)
                    p.drawPixmap(ox, oy, scaled)
                    p.end()

        container = _ContentFrame()
        container.setObjectName("content")
        container.setStyleSheet(f"""
            #content {{
                background-color: {BG_WINDOW};
                border-radius: {RADIUS}px;
            }}
        """)
        outer.addWidget(container)

        # ---- 根布局（内容区）---------------------------------------------
        root = QVBoxLayout(container)
        root.setContentsMargins(36, 28, 36, 32)
        root.setSpacing(0)

        # ---- 关闭按钮（右上角）------------------------------------------
        close_row = QHBoxLayout()
        close_row.setContentsMargins(0, 0, 0, 0)
        close_row.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setToolTip("关闭")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 8px;
                font-size: 15px;
                font-weight: normal;
            }}
            QPushButton:hover {{
                background-color: {ACCENT};
                color: #ffffff;
            }}
            QPushButton:pressed {{
                background-color: {ACCENT_PRESSED};
            }}
        """)
        close_btn.clicked.connect(self.close)
        close_row.addWidget(close_btn)
        root.addLayout(close_row)
        root.addSpacing(4)

        # ---- 标题 -------------------------------------------------------
        title = QLabel("CapyChat")
        title.setAlignment(Qt.AlignCenter)
        title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        title.setStyleSheet(f"""
            QLabel {{
                font-size: 22px;
                font-weight: 700;
                color: {TEXT_PRIMARY};
                background: transparent;
                border: none;
                padding: 0;
                margin-bottom: 4px;
            }}
        """)
        root.addWidget(title)

        subtitle = QLabel("水豚的局域网聊天室")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        subtitle.setStyleSheet(f"""
            QLabel {{
                font-size: 13px;
                color: {TEXT_MUTED};
                background: transparent;
                border: none;
                padding: 0;
                margin-bottom: 25px;
            }}
        """)
        root.addWidget(subtitle)

        # ---- 字段 ------------------------------------------------------

        # 本机 IP
        root.addWidget(_label("本机 IP"))
        root.addSpacing(6)
        self.local_ip = _combo(_get_local_ips())
        root.addWidget(self.local_ip)
        root.addSpacing(18)

        # 端口行（UDP / TCP 并排）
        ports_row = QHBoxLayout()
        ports_row.setSpacing(14)

        for port_type, default_val in [("UDP 端口", DEFAULT_UDP_PORT),
                                        ("TCP 端口", DEFAULT_TCP_PORT)]:
            col = QVBoxLayout()
            col.setSpacing(6)
            col.addWidget(_label(port_type))
            inp = _input(default_text=str(default_val))
            col.addWidget(inp)
            ports_row.addLayout(col)
            if port_type == "UDP 端口":
                self.udp_port = inp
            else:
                self.tcp_port = inp

        root.addLayout(ports_row)
        root.addSpacing(30)

        # 用户名
        root.addWidget(_label("用户名"))
        root.addSpacing(6)
        self.username = _input("请输入聊天昵称")
        root.addWidget(self.username)
        root.addSpacing(18)

        # 房间密码
        root.addWidget(_label("房间密码"))
        root.addSpacing(6)
        self.room_password = _PasswordLineEdit("留空 = 不加密，同房间需一致")
        root.addWidget(self.room_password)

        root.addSpacing(32)

        # ---- 按钮 ------------------------------------------------------
        self.confirm_btn = QPushButton("进入聊天室")
        self.confirm_btn.setCursor(Qt.PointingHandCursor)
        self.confirm_btn.setMinimumHeight(46)
        self.confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT};
                color: #ffffff;
                border: none;
                border-radius: {RADIUS_SM}px;
                font-size: 15px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {ACCENT_PRESSED};
            }}
        """)
        root.addWidget(self.confirm_btn)

        root.addSpacing(10)

        self.reset_btn = QPushButton("恢复默认")
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn.setMinimumHeight(40)
        self.reset_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_SECONDARY};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_SM}px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {BG_INPUT};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_HOVER};
            }}
            QPushButton:pressed {{
                background-color: #EEE9E0;
            }}
        """)
        root.addWidget(self.reset_btn)

        root.addSpacing(38)

        # ---- 底部版权 --------------------------------------------------
        copyright_label = QLabel("端到端加密  ·  P2P + UDP 广播")
        copyright_label.setAlignment(Qt.AlignCenter)
        copyright_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        copyright_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 11px;
                background: transparent;
                border: none;
                padding: 0;
            }}
        """)
        root.addWidget(copyright_label)

        root.addSpacing(2)

        author_label = QLabel("@Shane · 2026")
        author_label.setAlignment(Qt.AlignCenter)
        author_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        author_label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 11px;
                background: transparent;
                border: none;
                padding: 0;
            }}
        """)
        root.addWidget(author_label)

        root.addStretch()

        # ---- 信号绑定 --------------------------------------------------
        self.confirm_btn.clicked.connect(self.try_connect)
        self.reset_btn.clicked.connect(self._reset_to_defaults)

    # ====================================================================
    # 业务逻辑（与原版完全一致）
    # ====================================================================

    def try_connect(self):
        local_ip = self.local_ip.currentText().strip()
        udp_port = self.udp_port.text().strip()
        tcp_port = self.tcp_port.text().strip()
        username = self.username.text().strip()
        password = self.room_password.text().strip()

        if not all([local_ip, udp_port, tcp_port, username]):
            QMessageBox.warning(self, "输入错误", "请填写所有字段")
            return

        try:
            udp_port = int(udp_port)
            tcp_port = int(tcp_port)
        except ValueError:
            QMessageBox.warning(self, "输入错误", "端口号必须是数字")
            return

        if len(username) > 20:
            QMessageBox.warning(self, "输入错误", "用户名不能超过20个字符")
            return

        avatar = ""
        try:
            avatar = load_config().get("avatar", "")
        except Exception:
            pass

        encryption_key = derive_key(password) if password else None

        self._persist_config()

        try:
            self.tcp = TcpP2P(username, local_ip, tcp_port,
                              encryption_key=encryption_key)
            self.tcp.start()
        except Exception as e:
            QMessageBox.critical(self, "启动失败", f"TCP P2P启动失败: {e}")
            return

        try:
            self.udp = UdpBroadcast(username, local_ip, udp_port, tcp_port,
                                    encryption_key=encryption_key,
                                    avatar=avatar)
            self.udp.start()
        except Exception as e:
            self.tcp.stop()
            QMessageBox.critical(self, "启动失败", f"UDP广播启动失败: {e}")
            return

        self.chat_window = ChatWindow(
            username=username, local_ip=local_ip,
            tcp_port=tcp_port, udp=self.udp, tcp=self.tcp,
            avatar=avatar
        )
        self.chat_window.show()
        self.hide()

    def _reset_to_defaults(self):
        """恢复所有字段为程序默认值（不读 conf.json）。"""
        self.local_ip.setCurrentText(DEFAULT_CONFIG["local_ip"])
        self.udp_port.setText(str(DEFAULT_CONFIG["udp_port"]))
        self.tcp_port.setText(str(DEFAULT_CONFIG["tcp_port"]))
        self.username.setText(DEFAULT_CONFIG["username"])
        self.room_password.setText(DEFAULT_CONFIG.get("room_password", ""))

    def _load_config_to_ui(self):
        """从 config_manager 加载配置到 UI 字段。"""
        try:
            config = load_config()
        except Exception as e:
            print(f"加载配置失败: {e}")
            config = DEFAULT_CONFIG
        self.local_ip.setCurrentText(config.get("local_ip", DEFAULT_CONFIG["local_ip"]))
        self.udp_port.setText(str(config.get("udp_port", DEFAULT_CONFIG["udp_port"])))
        self.tcp_port.setText(str(config.get("tcp_port", DEFAULT_CONFIG["tcp_port"])))
        self.username.setText(config.get("username", DEFAULT_CONFIG["username"]))
        self.room_password.setText(config.get("room_password", DEFAULT_CONFIG.get("room_password", "")))

    def _persist_config(self):
        """从 UI 字段收集数据并写入 conf.json。"""
        current = load_config()
        current.update({
            "local_ip": self.local_ip.currentText(),
            "udp_port": int(self.udp_port.text().strip()),
            "tcp_port": int(self.tcp_port.text().strip()),
            "username": self.username.text().strip(),
            "room_password": self.room_password.text().strip(),
        })
        save_config(current)

    def closeEvent(self, event):
        if hasattr(self, "udp"):
            self.udp.stop()
        if hasattr(self, "tcp"):
            self.tcp.stop()
        super().closeEvent(event)
