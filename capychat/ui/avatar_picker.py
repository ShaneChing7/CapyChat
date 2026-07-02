"""头像选择器对话框 — 三列网格，双击确定，返回 avatar key。

用法：
    # 方式1：实例化使用
    dlg = AvatarPickerDialog(username="Alice", current_avatar="fox", parent=self)
    if dlg.exec() == QDialog.Accepted:
        new_avatar = dlg.selected_avatar

    # 方式2：静态方法（便捷）
    new_avatar = AvatarPickerDialog.get_selected_avatar(
        self, "Alice", "fox"
    )  # 返回 "fox" / "cat" / "" 等，取消返回 None
"""

import os
from typing import Optional

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QGridLayout, QWidget, QFrame,
                               QScrollArea)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QIcon

from .avatar_cache import AvatarCache, AvatarWidget, avatar_cache, get_avatar_color
from .theme import (PRIMARY, PRIMARY_DARK, BG_APP, TEXT_PRIMARY,
                    TEXT_SECONDARY, TEXT_HINT, BORDER, RADIUS_WINDOW)
from capychat._paths import asset_dir


# =============================================================================
# AvatarPickerDialog
# =============================================================================

class _AvatarCell(QFrame):
    """头像选择器中的单个头像格子 — 圆形预览 + 点击高亮。"""

    clicked = Signal(str)          # 单击 → 高亮
    double_clicked = Signal(str)   # 双击 → 直接确定

    def __init__(self, avatar_key: str, username: str = "",
                 size: int = 64, parent=None):
        """初始化头像格子。

        Args:
            avatar_key: 头像标识（""=首字母，其他=SVG key）
            username:   用户名（用于首字母头像渲染）
            size:       格子内头像尺寸
            parent:     父级控件
        """
        super().__init__(parent)
        self._avatar_key = avatar_key
        self._username = username
        self._size = size
        self._selected = False

        # 固定尺寸 = 头像 + 边距
        margin = 12
        total = size + margin * 2
        self.setFixedSize(total, total)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(self._tooltip_text())

        # 预渲染头像 pixmap
        self._pixmap = avatar_cache.get_pixmap(avatar_key, username, size)

        self.setStyleSheet(f"""
            _AvatarCell {{
                background: transparent;
                border: 2px solid transparent;
                border-radius: 12px;
            }}
            _AvatarCell:hover {{
                background: rgba(0,0,0,0.04);
            }}
        """)

    def _tooltip_text(self) -> str:
        """返回 tooltip 文字。"""
        if not self._avatar_key:
            return "默认头像（首字母）"
        # 将 key 转为显示名（首字母大写）
        return self._avatar_key.capitalize()

    def set_selected(self, selected: bool) -> None:
        """设置高亮状态。"""
        self._selected = selected
        if selected:
            self.setStyleSheet(f"""
                _AvatarCell {{
                    background: rgba(200,120,90,0.12);
                    border: 2px solid {PRIMARY};
                    border-radius: 12px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                _AvatarCell {{
                    background: transparent;
                    border: 2px solid transparent;
                    border-radius: 12px;
                }}
                _AvatarCell:hover {{
                    background: rgba(0,0,0,0.04);
                }}
            """)

    def paintEvent(self, event) -> None:
        """绘制圆形头像在格子中央。"""
        super().paintEvent(event)

        if self._pixmap and not self._pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            x = (self.width() - self._size) // 2
            y = (self.height() - self._size) // 2
            painter.drawPixmap(x, y, self._size, self._size, self._pixmap)
            painter.end()

    def mousePressEvent(self, event) -> None:
        """单击 → 高亮。"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._avatar_key)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """双击 → 直接确定。"""
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self._avatar_key)
        super().mouseDoubleClickEvent(event)


class AvatarPickerDialog(QDialog):
    """头像选择器对话框。

    界面：
        [默认] [🐱]  [🦊]
        [🐶]   [🦉]  [🐻]
        ...共 30 个预设 + 1 个默认...

    操作：
        - 单击高亮
        - 双击直接确定
        - 确定按钮返回选中项
    """

    COLUMNS = 3  # 网格列数

    def __init__(self, username: str = "", current_avatar: str = "",
                 parent=None):
        """初始化对话框。

        Args:
            username:       当前用户名
            current_avatar: 当前选中的头像 key
            parent:         父级控件
        """
        super().__init__(parent)
        self._username = username
        self.selected_avatar: str = current_avatar  # 初始值为当前头像
        self._drag_pos = None

        self._cells: dict[str, _AvatarCell] = {}
        self._init_ui()
        self._highlight(current_avatar)

    # ------------------------------------------------------------------
    # 窗口拖动
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        """构建对话框界面 — 无边框，圆角与主窗口一致。"""
        self.setWindowTitle("选择头像")
        self.setFixedSize(340, 440)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # ---- 外层（留出 6px 给可能的阴影边缘）----
        margin = 6
        outer = QVBoxLayout(self)
        outer.setContentsMargins(margin, margin, margin, margin)
        outer.setSpacing(0)

        # ---- 内容容器（背景色 + 圆角 = RADIUS_WINDOW）----
        container = QFrame()
        container.setObjectName("picker_container")
        container.setStyleSheet(f"""
            #picker_container {{
                background-color: {BG_APP};
                border: 0.5px solid {BORDER};
                border-radius: {RADIUS_WINDOW}px;
            }}
        """)
        outer.addWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(20, 8, 12, 16)
        root.setSpacing(12)

        # ---- 标题行（标题 + 关闭按钮）----
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(0)

        title = QLabel("选择头像")
        title.setStyleSheet(f"""
            QLabel {{
                font-size: 16px;
                font-weight: 600;
                color: {TEXT_PRIMARY};
                background: transparent;
                border: none;
            }}
        """)
        title_row.addWidget(title)
        title_row.addStretch()

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
            }}
            QPushButton:hover {{
                background-color: rgba(0,0,0,0.06);
                color: {TEXT_PRIMARY};
            }}
        """)
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn)
        root.addLayout(title_row)

        # ---- 说明文字 ----
        hint = QLabel("单击选择，双击确认")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                color: {TEXT_HINT};
                background: transparent;
                border: none;
            }}
        """)
        root.addWidget(hint)

        # ---- 头像网格（可滚动） ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER};
                border-radius: 2px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        grid_container = QWidget()
        grid_container.setStyleSheet("background: transparent;")
        grid = QGridLayout(grid_container)
        grid.setSpacing(6)
        grid.setContentsMargins(8, 4, 8, 4)
        grid.setAlignment(Qt.AlignCenter)

        # ---- 构建所有头像格子 ----
        # 第一项：默认首字母头像
        avatars = [""] + self._list_svg_avatars()

        for i, avatar_key in enumerate(avatars):
            cell = _AvatarCell(
                avatar_key=avatar_key,
                username=self._username,
                size=64,
            )
            cell.clicked.connect(self._on_cell_clicked)
            cell.double_clicked.connect(self._on_cell_double_clicked)
            self._cells[avatar_key] = cell

            row = i // self.COLUMNS
            col = i % self.COLUMNS
            grid.addWidget(cell, row, col, Qt.AlignCenter)

        scroll.setWidget(grid_container)
        root.addWidget(scroll, 1)

        # ---- 底部按钮 ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        cancel_btn = QPushButton("取消")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setMinimumHeight(38)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: 0.5px solid {BORDER};
                border-radius: 8px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: rgba(0,0,0,0.04);
            }}
        """)
        cancel_btn.clicked.connect(self.reject)

        ok_btn = QPushButton("确定")
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.setMinimumHeight(38)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {PRIMARY};
                color: #ffffff;
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {PRIMARY_DARK};
            }}
        """)
        ok_btn.clicked.connect(self.accept)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def _on_cell_clicked(self, avatar_key: str) -> None:
        """单击高亮格子。"""
        self.selected_avatar = avatar_key
        self._highlight(avatar_key)

    def _on_cell_double_clicked(self, avatar_key: str) -> None:
        """双击 → 确定并关闭。"""
        self.selected_avatar = avatar_key
        self.accept()

    def _highlight(self, avatar_key: str) -> None:
        """高亮指定格子，取消其他。"""
        for key, cell in self._cells.items():
            cell.set_selected(key == avatar_key)

    # ------------------------------------------------------------------
    # 静态工具
    # ------------------------------------------------------------------

    @staticmethod
    def _list_svg_avatars() -> list[str]:
        """列出 assets/avatars/ 下所有可用 SVG 文件名（不含扩展名）。"""
        avatars_dir = asset_dir('avatars')
        if not os.path.isdir(avatars_dir):
            return []
        names = []
        for fname in sorted(os.listdir(avatars_dir)):
            if fname.lower().endswith(".svg"):
                names.append(os.path.splitext(fname)[0])
        return names

    # ------------------------------------------------------------------
    # 便捷静态方法
    # ------------------------------------------------------------------

    @staticmethod
    def get_selected_avatar(parent, username: str,
                            current_avatar: str = "") -> Optional[str]:
        """弹出对话框并返回用户选择的 avatar key。

        Args:
            parent:         父级控件
            username:       当前用户名
            current_avatar: 当前头像 key

        Returns:
            新的 avatar key，用户取消时返回 None
        """
        dlg = AvatarPickerDialog(
            username=username,
            current_avatar=current_avatar,
            parent=parent,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.selected_avatar
        return None
