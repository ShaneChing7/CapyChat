"""侧边栏组件：用户信息、频道列表、退出按钮。"""

import os
import sys

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSizePolicy, QAbstractScrollArea,
                               QStyledItemDelegate, QLineEdit)
from PySide6.QtCore import Qt, Signal, QSize, QEvent, QPoint
from PySide6.QtGui import (QPainter, QColor, QFont, QPainterPath, QIcon)

from .theme import (BG_SIDEBAR, BORDER, PRIMARY, TEXT_PRIMARY,
                    TEXT_SECONDARY, TEXT_HINT, GREEN_ONLINE,
                    RADIUS_XS, SIDEBAR_WIDTH, BG_HOVER,
                    RADIUS_WINDOW)
from .avatar_cache import AvatarWidget, avatar_cache
from .capybara_widget import CapybaraWidget
from capychat._paths import asset_dir


_ONLINE_ROLE = Qt.UserRole + 1   # 存储在线状态: True/False
_UNREAD_ROLE = Qt.UserRole + 2   # 存储未读数量: int
_AVATAR_ROLE = Qt.UserRole + 3   # 存储头像 key: str


class _ChannelDelegate(QStyledItemDelegate):
    """绘制广场右侧在线小点，私聊右侧未读数字徽章。"""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        # ---- 在线小点（仅广场） ----
        online = index.data(_ONLINE_ROLE)
        if online is not None:
            dot_size = 7
            margin = 10
            x = option.rect.right() - dot_size - margin
            y = option.rect.center().y() - dot_size // 2
            color = GREEN_ONLINE if online else "#B0B0B0"
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(color))
            painter.drawEllipse(x, y, dot_size, dot_size)

        # ---- 未读徽章（仅私聊） ----
        unread = index.data(_UNREAD_ROLE)
        if unread and unread > 0:
            badge_w = 18 if unread < 10 else 24
            badge_h = 18
            margin = 8
            bx = option.rect.right() - badge_w - margin
            by = option.rect.center().y() - badge_h // 2

            # 椭圆背景
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(PRIMARY))
            painter.drawRoundedRect(bx, by, badge_w, badge_h,
                                    badge_h // 2, badge_h // 2)
            # 白色数字
            painter.setPen(QColor("#ffffff"))
            font = painter.font()
            font.setPixelSize(11)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(bx, by, badge_w, badge_h,
                             Qt.AlignCenter, str(unread))

        painter.restore()


class _ChannelItem(QListWidgetItem):
    """自定义列表项，携带频道标识数据。"""

    def __init__(self, text="", channel_id=""):
        super().__init__(text)
        self.setData(Qt.UserRole, channel_id)
        self.setFlags(self.flags() | Qt.ItemIsEnabled)


class SidebarWidget(QWidget):
    """左侧边栏。"""

    channel_selected = Signal(str)   # channel_id
    exit_requested = Signal()
    doc_center_requested = Signal()
    doc_open_requested = Signal(str)  # file_path
    avatar_changed = Signal(str)      # 用户更改头像时发射，参数为新 avatar_key

    def __init__(self, username="", address="", avatar_key="",
                 parent=None):
        super().__init__(parent)
        self.username = username
        self.address = address
        self._avatar_key = avatar_key
        self.setFixedWidth(SIDEBAR_WIDTH)
        self._active_channel = "group"
        self._channel_data: dict[str, dict] = {}  # channel_id → {text, online, unread, avatar}
        self._online_count = 0
        self._searching = False
        self._icon_dir = asset_dir('icons')
        self._received_dir = (
            os.path.join(os.path.expanduser('~'), 'Downloads', 'CapyChat')
            if getattr(sys, 'frozen', False)
            else os.path.join(os.path.dirname(os.path.dirname(__file__)), 'received')
        )
        self.initUI()

    def paintEvent(self, event):
        """绘制背景：仅左上/左下圆角，右侧直角。"""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        r = RADIUS_WINDOW

        path = QPainterPath()
        # 从左上圆角起点开始，顺时针
        path.moveTo(r, 0)
        path.lineTo(w, 0)
        path.lineTo(w, h)
        path.lineTo(r, h)
        path.arcTo(0, h - r * 2, r * 2, r * 2, 270, -90)   # 左下圆角
        path.lineTo(0, r)
        path.arcTo(0, 0, r * 2, r * 2, 180, -90)            # 左上圆角
        path.closeSubpath()

        p.setBrush(QColor(BG_SIDEBAR))
        p.setPen(Qt.NoPen)
        p.drawPath(path)
        p.end()

    def initUI(self):
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WA_StyledBackground, False)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ==================================================================
        # 用户信息头
        # ==================================================================
        header = QWidget()
        header.setStyleSheet(f"""
            QWidget {{
                background: transparent;
                border-bottom: 0.5px solid {BORDER};
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(10)

        self.avatar = AvatarWidget(
            username=self.username,
            avatar_key=self._avatar_key,
            size=42)
        self.avatar.setCursor(Qt.PointingHandCursor)
        self.avatar.setToolTip("点击更换头像")
        self.avatar.clicked.connect(self._on_avatar_clicked)
        header_layout.addWidget(self.avatar)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        self.name_label = QLabel(self.username or "用户")
        self.name_label.setStyleSheet(f"""
            QLabel {{
                font-size: 16px;
                font-weight: 500;
                color: {TEXT_PRIMARY};
                background: transparent;
                border: none;
            }}
        """)
        info_col.addWidget(self.name_label)

        self.addr_label = QLabel(self.address or "")
        self.addr_label.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                color: {TEXT_SECONDARY};
                background: transparent;
                border: none;
            }}
        """)
        info_col.addWidget(self.addr_label)

        header_layout.addLayout(info_col, 1)
        layout.addWidget(header)

        # ==================================================================
        # 搜索框
        # ==================================================================
        search_wrap = QWidget()
        search_wrap.setStyleSheet("background: transparent;")
        search_layout = QHBoxLayout(search_wrap)
        search_layout.setContentsMargins(10, 10, 10, 4)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("搜索联系人 / 文档...")
        self._search_input.setClearButtonEnabled(True)
        icon_path = os.path.join(self._icon_dir, "search.svg")
        if os.path.exists(icon_path):
            self._search_input.addAction(QIcon(icon_path),
                                         QLineEdit.LeadingPosition)
        self._search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: rgba(0,0,0,0.04);
                border: 0.5px solid {BORDER};
                border-radius: {RADIUS_XS + 2}px;
                padding: 8px 12px;
                font-size: 13px;
                color: {TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border: 0.5px solid {PRIMARY};
            }}
        """)
        self._search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self._search_input)
        layout.addWidget(search_wrap)

        # ==================================================================
        # 文档中心入口
        # ==================================================================
        doc_wrap = QWidget()
        doc_wrap.setStyleSheet("background: transparent;")
        doc_layout = QHBoxLayout(doc_wrap)
        doc_layout.setContentsMargins(10, 0, 10, 8)

        self.doc_btn = QPushButton("  文档中心")
        self.doc_btn.setCursor(Qt.PointingHandCursor)
        self.doc_btn.setMinimumHeight(36)
        icon_path = os.path.join(self._icon_dir, "file-stack.svg")
        if os.path.exists(icon_path):
            self.doc_btn.setIcon(QIcon(icon_path))
            self.doc_btn.setIconSize(QSize(20, 20))
        self.doc_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_PRIMARY};
                border: 0.5px solid {BORDER};
                border-radius: {RADIUS_XS}px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {BG_HOVER};
            }}
            QPushButton:pressed {{
                background: {BORDER};
            }}
        """)
        self.doc_btn.clicked.connect(self.doc_center_requested.emit)
        doc_layout.addWidget(self.doc_btn)
        layout.addWidget(doc_wrap)

        # ==================================================================
        # Capybara AI 助手卡片
        # ==================================================================
        self.capybara_widget = CapybaraWidget()
        self.capybara_widget.clicked.connect(lambda: self._on_capybara_clicked())
        layout.addWidget(self.capybara_widget)

        # 分隔线
        sep2 = QLabel()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background: {BORDER}; margin: 0 12px; border: none;")
        layout.addWidget(sep2)

        # ==================================================================
        # 频道标题
        # ==================================================================
        self._section_label = QLabel("频道")
        self._section_label.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                color: {TEXT_SECONDARY};
                letter-spacing: 0.05em;
                padding: 12px 14px 6px;
                background: transparent;
                border: none;
            }}
        """)
        layout.addWidget(self._section_label)

        # ==================================================================
        # 频道列表
        # ==================================================================
        self.channel_list = QListWidget()
        self.channel_list.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background: transparent;
                font-size: 15px;
                outline: none;
                padding: 2px 8px;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                border-radius: {RADIUS_XS}px;
                color: {TEXT_PRIMARY};
                margin-bottom: 2px;
                background: transparent;
            }}
            QListWidget::item:selected {{
                background-color: {PRIMARY};
                color: #ffffff;
                border-radius: {RADIUS_XS}px;
            }}
            QListWidget::item:selected:!active {{
                background-color: {PRIMARY};
                color: #ffffff;
                border-radius: {RADIUS_XS}px;
            }}
            QListWidget::item:hover:!selected {{
                background-color: {BG_HOVER};
                border-radius: {RADIUS_XS}px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER};
                border-radius: 2px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        self._channel_data["group"] = {"text": "广场",
                                        "icon": "house-heart.svg",
                                        "online": False,
                                        "unread": 0}
        self._build_channel_list()
        self.channel_list.setItemDelegate(_ChannelDelegate())
        self.channel_list.itemClicked.connect(self._on_channel_clicked)
        layout.addWidget(self.channel_list, 1)

        # ==================================================================
        # 文件传输进度列表（可滚动，隐藏时不可见）
        # ==================================================================
        self._progress_scroll = QScrollArea()
        self._progress_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff)
        self._progress_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded)
        self._progress_scroll.setMaximumHeight(200)
        self._progress_scroll.setWidgetResizable(True)
        self._progress_scroll.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self._progress_scroll.setSizePolicy(QSizePolicy.Expanding,
                                            QSizePolicy.Preferred)
        self._progress_scroll.setVisible(False)
        self._progress_scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                border-top: 0.5px solid {BORDER};
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER};
                border-radius: 2px;
                min-height: 16px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        self._progress_container = QWidget()
        self._progress_container.setStyleSheet(
            "background: transparent;")
        self._progress_layout = QVBoxLayout(self._progress_container)
        self._progress_layout.setContentsMargins(6, 6, 6, 6)
        self._progress_layout.setSpacing(4)
        self._progress_layout.addStretch()
        self._progress_scroll.setWidget(self._progress_container)

        # 修正滚轮方向：滚轮向下 → 内容上移（正常逻辑）
        self._progress_scroll.viewport().installEventFilter(self)

        layout.addWidget(self._progress_scroll)

        # ==================================================================
        # 底部按钮区
        # ==================================================================
        footer = QWidget()
        footer.setStyleSheet(f"QWidget {{ background: transparent; border-top: 0.5px solid {BORDER}; }}")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(8, 10, 8, 10)
        footer_layout.setSpacing(6)

        # 退出聊天室
        self.exit_btn = QPushButton("退出聊天室")
        self.exit_btn.setCursor(Qt.PointingHandCursor)
        self.exit_btn.setMinimumHeight(40)
        self.exit_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: #C97A7A;
                border: 0.5px solid {BORDER};
                border-radius: {RADIUS_XS}px;
                font-size: 15px;
            }}
            QPushButton:hover {{
                background: {BG_HOVER};
            }}
            QPushButton:pressed {{
                background: {BORDER};
            }}
        """)
        self.exit_btn.clicked.connect(self.exit_requested.emit)
        footer_layout.addWidget(self.exit_btn)

        layout.addWidget(footer)

    # ==================================================================
    # Public API
    # ==================================================================

    def add_user(self, username, ip, tcp_port, avatar=""):
        """添加在线用户到频道列表。"""
        addr = f"{ip}:{tcp_port}"
        self._channel_data[addr] = {"text": username,
                                     "icon": "contact-round.svg",
                                     "unread": 0,
                                     "avatar": avatar}
        if not self._searching:
            self._build_channel_list()

    def remove_user(self, username):
        """从频道列表移除用户。"""
        for addr, data in list(self._channel_data.items()):
            if addr != "group" and data["text"] == username:
                del self._channel_data[addr]
                if not self._searching:
                    self._build_channel_list()
                return

    def update_user_list(self, users):
        """批量更新在线用户列表。users: [(username, ip, tcp_port, avatar), ...]"""
        for addr in list(self._channel_data.keys()):
            if addr != "group":
                del self._channel_data[addr]
        for item in users:
            username, ip, tcp_port = item[0], item[1], item[2]
            avatar = item[3] if len(item) > 3 else ""
            addr = f"{ip}:{tcp_port}"
            self._channel_data[addr] = {"text": username,
                                         "icon": "contact-round.svg",
                                         "unread": 0,
                                         "avatar": avatar}
        if not self._searching:
            self._build_channel_list()

    def get_channel_name(self, channel_id):
        """返回频道的显示名称。"""
        if channel_id == "capybara":
            return "🦫 Capybara"
        data = self._channel_data.get(channel_id)
        if data:
            return data["text"]
        return "广场" if channel_id == "group" else "私聊"

    def set_group_online(self, has_online):
        """更新广场项的在线圆点：绿色 / 灰色。"""
        data = self._channel_data.get("group")
        if data:
            data["online"] = has_online
            if not self._searching:
                self._build_channel_list()

    def add_unread(self, channel_id):
        """对应私聊项未读计数 +1。"""
        data = self._channel_data.get(channel_id)
        if not data or channel_id == "group":
            return
        data["unread"] = data.get("unread", 0) + 1
        if not self._searching:
            self._build_channel_list()

    def clear_unread(self, channel_id):
        """清除私聊项未读计数。"""
        data = self._channel_data.get(channel_id)
        if not data or channel_id == "group":
            return
        data["unread"] = 0
        if not self._searching:
            self._build_channel_list()

    def set_active_channel(self, channel_id):
        """高亮活跃频道。"""
        self._active_channel = channel_id
        if not self._searching:
            item = self._find_item_by_channel_id(channel_id)
            if item:
                self.channel_list.setCurrentItem(item)

    def set_avatar(self, avatar_key: str) -> None:
        """更新当前用户头像（外部调用）。"""
        self._avatar_key = avatar_key
        self.avatar.set_avatar(self.username, avatar_key)

    # ==================================================================
    # 头像点击 → 弹出选择器
    # ==================================================================

    def _on_avatar_clicked(self) -> None:
        """点击当前用户头像 → 弹出 AvatarPickerDialog。"""
        from .avatar_picker import AvatarPickerDialog
        result = AvatarPickerDialog.get_selected_avatar(
            self, self.username, self._avatar_key)
        if result is not None and result != self._avatar_key:
            self._avatar_key = result
            self.avatar.set_avatar(self.username, result)
            self.avatar_changed.emit(result)

    def add_progress_bar(self, bar_widget):
        """添加文件传输进度条到可滚动列表。"""
        count = self._progress_layout.count()
        self._progress_layout.insertWidget(count - 1, bar_widget)
        self._progress_scroll.setVisible(True)

    def remove_progress_bar(self, bar_widget):
        """移除文件传输进度条。"""
        bar_widget.setParent(None)
        self._progress_layout.removeWidget(bar_widget)
        # 没有进度条时隐藏整个区域
        if self._progress_layout.count() <= 1:  # 只剩 stretch
            self._progress_scroll.setVisible(False)

    # ==================================================================
    # Event filter — 修正进度列表滚轮方向
    # ==================================================================

    def eventFilter(self, obj, event):
        if obj is self._progress_scroll.viewport() and \
                event.type() == QEvent.Wheel:
            delta = event.angleDelta().y()
            if delta != 0:
                sb = self._progress_scroll.verticalScrollBar()
                sb.setValue(sb.value() - delta)
            return True
        return super().eventFilter(obj, event)

    # ==================================================================
    # Search
    # ==================================================================

    _DOC_PREFIX = "__doc__"

    def _on_search(self, text):
        t = text.strip().lower()
        has_text = bool(t)
        self._section_label.setVisible(not has_text)

        if not has_text:
            self._searching = False
            self._build_channel_list()
            return

        # ---- 搜索模式：清空列表并重建 ----
        self._searching = True
        self.channel_list.clear()

        def _add_header(label_text):
            hdr = QListWidgetItem()
            hdr.setText(label_text)
            hdr.setFlags(Qt.NoItemFlags)
            hdr.setData(Qt.UserRole, "")
            font = hdr.font()
            font.setPointSize(10)
            font.setBold(True)
            hdr.setFont(font)
            hdr.setForeground(QColor(TEXT_HINT))
            hdr.setSizeHint(QSize(0, 28))
            self.channel_list.addItem(hdr)

        # 收集匹配的联系人
        contact_matches = []
        for channel_id, data in self._channel_data.items():
            if t in data["text"].lower():
                contact_matches.append((channel_id, data))

        # 收集匹配的文档
        doc_matches = []
        if os.path.isdir(self._received_dir):
            for fname in os.listdir(self._received_dir):
                fpath = os.path.join(self._received_dir, fname)
                if os.path.isfile(fpath) and not fname.startswith(".") \
                        and t in fname.lower():
                    doc_matches.append((fname, fpath, os.path.getmtime(fpath)))
            doc_matches.sort(key=lambda x: x[2], reverse=True)
            doc_matches = doc_matches[:8]

        # 联系人区段
        if contact_matches:
            _add_header("联系人")
            for channel_id, data in contact_matches:
                username = data["text"]
                avatar_key = data.get("avatar", "")
                item = QListWidgetItem(username)
                item.setData(Qt.UserRole, channel_id)
                # 渲染真实头像图标
                pixmap = avatar_cache.get_pixmap(avatar_key, username, 24)
                item.setIcon(QIcon(pixmap))
                item.setFlags(item.flags() | Qt.ItemIsEnabled)
                self.channel_list.addItem(item)

        # 文档区段
        if doc_matches:
            _add_header("文档")
            for fname, fpath, _ in doc_matches:
                item = QListWidgetItem(fname)
                item.setData(Qt.UserRole, self._DOC_PREFIX + fpath)
                icon_path = os.path.join(self._icon_dir, "sticky-note.svg")
                if os.path.exists(icon_path):
                    item.setIcon(QIcon(icon_path))
                item.setFlags(item.flags() | Qt.ItemIsEnabled)
                self.channel_list.addItem(item)

        # 无结果
        if not contact_matches and not doc_matches:
            _add_header("无搜索结果")

    # ==================================================================
    # Private
    # ==================================================================

    def _make_item(self, text, channel_id, icon_file=None):
        """创建带图标和 channel_id 的 QListWidgetItem。"""
        item = QListWidgetItem(text)
        item.setData(Qt.UserRole, channel_id)
        if icon_file:
            icon_path = os.path.join(self._icon_dir, icon_file)
            if os.path.exists(icon_path):
                item.setIcon(QIcon(icon_path))
        return item

    def _make_avatar_item(self, username, channel_id, avatar_key=""):
        """创建带真实头像图标的 QListWidgetItem（24px 圆形头像）。"""
        item = QListWidgetItem(username)
        item.setData(Qt.UserRole, channel_id)
        item.setData(_AVATAR_ROLE, avatar_key)
        # 渲染 24px 圆形头像为图标
        pixmap = avatar_cache.get_pixmap(avatar_key, username, 24)
        item.setIcon(QIcon(pixmap))
        return item

    def _find_item_by_channel_id(self, channel_id):
        """在列表中按 UserRole 查找 item。"""
        for i in range(self.channel_list.count()):
            item = self.channel_list.item(i)
            if item and item.data(Qt.UserRole) == channel_id:
                return item
        return None

    def _build_channel_list(self):
        """从 _channel_data 完整重建频道列表。"""
        self.channel_list.clear()

        # 广场
        group_data = self._channel_data.get("group")
        if group_data:
            item = self._make_item(group_data["text"], "group",
                                   group_data.get("icon"))
            item.setData(_ONLINE_ROLE, group_data.get("online", False))
            self.channel_list.addItem(item)

        # 分隔线
        sep = QListWidgetItem()
        sep.setFlags(Qt.NoItemFlags)
        sep.setSizeHint(QSize(0, 1))
        self.channel_list.addItem(sep)

        # 在线用户 — 使用真实头像
        for channel_id, data in self._channel_data.items():
            if channel_id == "group":
                continue
            avatar_key = data.get("avatar", "")
            username = data["text"]
            item = self._make_avatar_item(username, channel_id, avatar_key)
            unread = data.get("unread", 0)
            if unread:
                item.setData(_UNREAD_ROLE, unread)
            self.channel_list.addItem(item)

        # 重建后恢复当前活跃频道的选中状态
        active_item = self._find_item_by_channel_id(self._active_channel)
        if active_item:
            self.channel_list.setCurrentItem(active_item)

    def _on_channel_clicked(self, item):
        channel_id = item.data(Qt.UserRole)
        if not channel_id:
            return
        if channel_id.startswith(self._DOC_PREFIX):
            file_path = channel_id[len(self._DOC_PREFIX):]
            self.doc_open_requested.emit(file_path)
            return
        # 立即高亮选中项（避免重建列表后丢失选中状态）
        self.channel_list.setCurrentItem(item)
        if channel_id != self._active_channel:
            self._active_channel = channel_id
            self.channel_selected.emit(channel_id)

    def _on_capybara_clicked(self):
        """点击 Capybara 卡片 → 切换到 AI 助手频道。"""
        if "capybara" != self._active_channel:
            self._active_channel = "capybara"
            self.channel_list.clearSelection()
            self.channel_selected.emit("capybara")
