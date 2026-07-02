"""文档中心 — 管理 received 目录中的所有文件：查看、打开、删除、分享。"""

import os
import subprocess
import platform
from datetime import datetime

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QListWidget, QListWidgetItem,
                               QMenu, QMessageBox, QWidget, QFrame)
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QCursor

from .theme import (BG_APP, BG_SIDEBAR, BORDER, BORDER_LIGHT, PRIMARY,
                    PRIMARY_DARK, TEXT_PRIMARY, TEXT_SECONDARY,
                    TEXT_HINT, RADIUS_WINDOW, RADIUS_XS)
from capychat._paths import asset_dir


def _format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _file_type_label(name):
    _, ext = os.path.splitext(name or "")
    ext = ext.lstrip(".").upper()
    return ext if ext else "?"


def _icon_dir():
    return asset_dir('icons')


class _FileRow(QWidget):
    """单行文件条目：图标 | 名称 + 类型·大小·时间 | 操作按钮。"""

    delete_clicked = Signal(str)
    share_clicked = Signal(str, str)  # file_path, channel_id

    def __init__(self, file_path="", parent=None):
        super().__init__(parent)
        self._file_path = file_path
        self.setStyleSheet("background: transparent;")

        name = os.path.basename(file_path)
        stat = os.stat(file_path)
        size_str = _format_size(stat.st_size)
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        ext_label = _file_type_label(name)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(10)

        # 文件图标 — 使用 sticky-note.svg
        icon_path = os.path.join(_icon_dir(), "sticky-note.svg")
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(40, 40)
        icon_lbl.setAlignment(Qt.AlignCenter)
        if os.path.exists(icon_path):
            pix = QPixmap(icon_path).scaled(24, 24,
                                            Qt.KeepAspectRatio,
                                            Qt.SmoothTransformation)
            icon_lbl.setPixmap(pix)
        icon_lbl.setStyleSheet("""
            QLabel {
                background: rgba(0,0,0,0.04);
                border-radius: 8px;
                border: none;
            }
        """)
        row.addWidget(icon_lbl)

        # 文件信息
        info = QVBoxLayout()
        info.setSpacing(2)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"""
            QLabel {{
                font-size: 14px;
                font-weight: 500;
                color: {TEXT_PRIMARY};
                background: transparent;
                border: none;
            }}
        """)
        name_lbl.setWordWrap(False)
        info.addWidget(name_lbl)

        meta_lbl = QLabel(f"{ext_label}  ·  {size_str}  ·  {mtime}")
        meta_lbl.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                color: {TEXT_HINT};
                background: transparent;
                border: none;
            }}
        """)
        info.addWidget(meta_lbl)

        row.addLayout(info, 1)

        # 操作按钮
        btn_style = f"""
            QPushButton {{
                font-size: 12px;
                padding: 4px 12px;
                border: 0.5px solid {BORDER};
                border-radius: {RADIUS_XS}px;
                background: transparent;
                color: {TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                background: {BG_SIDEBAR};
                color: {TEXT_PRIMARY};
            }}
        """

        open_btn = QPushButton("打开")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.setStyleSheet(btn_style)
        open_btn.clicked.connect(lambda: self._open_file())
        row.addWidget(open_btn)

        del_btn = QPushButton("删除")
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(btn_style)
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(self._file_path))
        row.addWidget(del_btn)

        share_btn = QPushButton("分享")
        share_btn.setCursor(Qt.PointingHandCursor)
        share_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 12px;
                padding: 4px 12px;
                border: 0.5px solid {PRIMARY};
                border-radius: {RADIUS_XS}px;
                background: transparent;
                color: {PRIMARY};
            }}
            QPushButton:hover {{
                background: {PRIMARY};
                color: #fff;
            }}
        """)
        share_btn.clicked.connect(lambda: self.share_clicked.emit(self._file_path, ""))
        row.addWidget(share_btn)

    def _open_file(self):
        """用系统默认程序打开文件。"""
        try:
            path = os.path.abspath(self._file_path)
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass


class DocumentCenterDialog(QDialog):
    """文档中心弹窗 — 无边框，圆角与主窗口统一。"""

    share_file_requested = Signal(str, str)  # file_path, channel_id
    delete_file_requested = Signal(str)      # file_path

    def __init__(self, received_dir="", get_users=None, parent=None):
        super().__init__(parent)
        self._received_dir = received_dir
        self._get_users = get_users or (lambda: [])
        self.setWindowTitle("文档中心")
        self.resize(630, 460)
        self.setMinimumSize(510, 340)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._drag_pos = None
        self.initUI()
        self._refresh()

    # ==================================================================
    # UI
    # ==================================================================

    def initUI(self):
        margin = 6
        # 外层
        outer = QVBoxLayout(self)
        outer.setContentsMargins(margin, margin, margin, margin)

        # 窗口容器（圆角背景 + 统一边框）
        container = QFrame()
        container.setObjectName("doc_container")
        container.setStyleSheet(f"""
            #doc_container {{
                background-color: {BG_APP};
                border: 0.5px solid {BORDER};
                border-radius: {RADIUS_WINDOW}px;
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        # ---- 标题栏 ----
        title_row = QHBoxLayout()

        # 标题图标
        icon_path = os.path.join(_icon_dir(), "sticky-note.svg")
        if os.path.exists(icon_path):
            title_icon = QLabel()
            title_icon.setFixedSize(24, 24)
            pix = QPixmap(icon_path).scaled(24, 24,
                                            Qt.KeepAspectRatio,
                                            Qt.SmoothTransformation)
            title_icon.setPixmap(pix)
            title_icon.setStyleSheet("background: transparent; border: none;")
            title_row.addWidget(title_icon)

        title = QLabel("文档中心")
        title.setStyleSheet(f"""
            QLabel {{
                font-size: 18px;
                font-weight: 700;
                color: {TEXT_PRIMARY};
                background: transparent;
                border: none;
            }}
        """)
        title_row.addWidget(title)
        title_row.addStretch()

        refresh_btn = QPushButton("刷新")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 12px;
                padding: 4px 12px;
                border: 0.5px solid {BORDER};
                border-radius: {RADIUS_XS}px;
                background: transparent;
                color: {TEXT_SECONDARY};
            }}
            QPushButton:hover {{
                background: {BG_SIDEBAR};
            }}
        """)
        refresh_btn.clicked.connect(self._refresh)
        title_row.addWidget(refresh_btn)

        del_all_btn = QPushButton("全部删除")
        del_all_btn.setCursor(Qt.PointingHandCursor)
        del_all_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 12px;
                padding: 4px 12px;
                border: 0.5px solid #C97A7A;
                border-radius: {RADIUS_XS}px;
                background: transparent;
                color: #C97A7A;
            }}
            QPushButton:hover {{
                background: #C97A7A;
                color: #fff;
            }}
        """)
        del_all_btn.clicked.connect(self._on_delete_all)
        title_row.addWidget(del_all_btn)

        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                border-radius: 6px;
                background: transparent;
                color: {TEXT_SECONDARY};
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {PRIMARY};
                color: #fff;
            }}
        """)
        close_btn.clicked.connect(self.close)
        title_row.addWidget(close_btn)

        root.addLayout(title_row)

        # ---- 分隔线 ----
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {BORDER_LIGHT}; border: none;")
        root.addWidget(sep)

        # ---- 接收目录路径 ----
        path_row = QHBoxLayout()
        path_label = QLabel("接收目录：")
        path_label.setStyleSheet(f"""
            QLabel {{
                font-size: 11px;
                color: {TEXT_HINT};
                background: transparent;
                border: none;
            }}
        """)
        path_row.addWidget(path_label)

        self._path_value = QLabel(self._received_dir)
        self._path_value.setStyleSheet(f"""
            QLabel {{
                font-size: 11px;
                color: {TEXT_SECONDARY};
                background: transparent;
                border: none;
            }}
        """)
        self._path_value.setWordWrap(True)
        path_row.addWidget(self._path_value, 1)

        open_dir_btn = QPushButton("打开目录")
        open_dir_btn.setCursor(Qt.PointingHandCursor)
        open_dir_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 11px;
                padding: 2px 10px;
                border: 0.5px solid {BORDER};
                border-radius: {RADIUS_XS}px;
                background: transparent;
                color: {PRIMARY};
            }}
            QPushButton:hover {{
                background: {BG_SIDEBAR};
            }}
        """)
        open_dir_btn.clicked.connect(self._open_received_dir)
        path_row.addWidget(open_dir_btn)

        root.addLayout(path_row)

        # ---- 文件列表 ----
        self._list = QListWidget()
        self._list.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background: transparent;
                outline: none;
            }}
            QListWidget::item {{
                background: transparent;
                border: none;
                margin: 2px 0;
            }}
            QListWidget::item:hover {{
                background: {BG_SIDEBAR};
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
        root.addWidget(self._list, 1)

        # ---- 空状态提示 ----
        self._empty_lbl = QLabel("暂无文件，接收到的文件会出现在这里")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet(f"""
            QLabel {{
                font-size: 13px;
                color: {TEXT_HINT};
                background: transparent;
                border: none;
                padding: 40px;
            }}
        """)
        root.addWidget(self._empty_lbl)

    # ==================================================================
    # 拖拽
    # ==================================================================

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    # ==================================================================
    # Private
    # ==================================================================

    def _refresh(self):
        """重新扫描 received 目录并刷新列表。"""
        self._list.clear()
        files = []

        if self._received_dir and os.path.isdir(self._received_dir):
            for name in os.listdir(self._received_dir):
                path = os.path.join(self._received_dir, name)
                if os.path.isfile(path) and not name.startswith("."):
                    files.append(path)

        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)

        self._empty_lbl.setVisible(len(files) == 0)

        for fp in files:
            item = QListWidgetItem()
            row = _FileRow(fp)
            row.delete_clicked.connect(self._on_delete)
            row.share_clicked.connect(self._on_share)
            item.setSizeHint(row.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, row)

    def _on_delete(self, file_path):
        ret = QMessageBox.question(
            self, "确认删除", f"确定要删除 \"{os.path.basename(file_path)}\" 吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret == QMessageBox.Yes:
            try:
                os.remove(file_path)
            except OSError as e:
                QMessageBox.warning(self, "删除失败", str(e))
                return
            self.delete_file_requested.emit(file_path)
            self._refresh()

    def _on_delete_all(self):
        """删除全部已接收文件。"""
        if not self._received_dir or not os.path.isdir(self._received_dir):
            return
        files = [f for f in os.listdir(self._received_dir)
                 if os.path.isfile(os.path.join(self._received_dir, f))
                 and not f.startswith(".")]
        if not files:
            return
        ret = QMessageBox.question(
            self, "确认全部删除",
            f"确定要删除文档中心全部 {len(files)} 个文件吗？\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        errors = 0
        for name in files:
            try:
                os.remove(os.path.join(self._received_dir, name))
            except OSError:
                errors += 1
        if errors:
            QMessageBox.warning(self, "删除完成",
                                f"已删除 {len(files) - errors} 个文件，{errors} 个文件删除失败。")
        self._refresh()

    def _open_received_dir(self):
        """在资源管理器中打开接收目录。"""
        if not self._received_dir:
            return
        try:
            os.startfile(self._received_dir)
        except Exception:
            # 目录不存在则尝试用 subprocess
            if platform.system() == "Windows":
                subprocess.run(["explorer", self._received_dir])
            elif platform.system() == "Darwin":
                subprocess.run(["open", self._received_dir])
            else:
                subprocess.run(["xdg-open", self._received_dir])

    def _on_share(self, file_path, _):
        """弹出分享菜单：广场 + 在线用户列表。"""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {BG_APP};
                border: 0.5px solid {BORDER};
                border-radius: {RADIUS_XS}px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                font-size: 13px;
                color: {TEXT_PRIMARY};
                border-radius: 4px;
            }}
            QMenu::item:hover {{
                background: {BG_SIDEBAR};
            }}
            QMenu::separator {{
                height: 1px;
                background: {BORDER_LIGHT};
                margin: 4px 8px;
            }}
        """)

        # 广场
        menu.addAction("广场", lambda: self._do_share(file_path, "group"))
        menu.addSeparator()

        # 在线用户（私聊）
        online = self._get_users()
        has_users = False
        for item in online:
            username, ip, port = item[0], item[1], item[2]
            channel_id = f"{ip}:{port}"
            menu.addAction(username, lambda cid=channel_id: self._do_share(file_path, cid))
            has_users = True

        if not has_users:
            menu.addAction("(暂无在线用户)").setEnabled(False)

        menu.exec(QCursor.pos())

    def _do_share(self, file_path, channel_id):
        self.share_file_requested.emit(file_path, channel_id)
