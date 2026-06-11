"""表情选择器：分类标签页 + emoji 按钮网格 + 底部预览栏，暖橙主题。"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QPushButton, QScrollArea, QFrame, QGridLayout, QSizePolicy,
    QTabBar,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QKeyEvent, QCursor

from .theme import (BG_APP, BG_SIDEBAR, BG_INPUT, BG_HOVER,
                    PRIMARY, PRIMARY_DARK, PRIMARY_LIGHT,
                    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_HINT,
                    BORDER, RADIUS_WINDOW)

# ---------------------------------------------------------------------------
# Emoji 数据
# ---------------------------------------------------------------------------
EMOJI_DATA: dict[str, list[str]] = {
    "😀 笑脸": [
        "😀","😃","😄","😁","😅","🤣","😂","🙂","😊","😇",
        "😍","🤩","😘","😗","😚","😋","😜","🤪","😝","🤑",
        "🤗","🤭","🤫","🤔","😐","😑","😶","🙄","😏","😒",
        "😬","😌","😔","😪","🤤","😴","😷","🤒","🤕","🤢",
        "🤮","🥵","🥶","😵","🤯","🥴","😎","🤓",
    ],
    "👋 手势": [
        "👋","🤚","✋","🖐","👌","🤏","✌️","🤞","🤟","🤘",
        "🤙","👈","👉","👆","👇","☝️","👍","👎","✊","👊",
        "🤛","🤜","👏","🙌","🤲","🤝","🙏","💪","🦾","✍️","🤳",
    ],
    "❤️ 爱心": [
        "❤️","🧡","💛","💚","💙","💜","🖤","🤍","🤎","💔",
        "💕","💞","💓","💗","💖","💘","💝","💟","💌","💋",
        "💯","💢","💥","💫","💦","💨","🕳","💤","💬","💭","🗯",
    ],
    "🎉 庆祝": [
        "🎉","🎊","🎈","🎂","🎀","🎁","🎃","🎄","🎅","🤶",
        "🧧","🧨","🎆","🎇","✨","🌟","⭐","🔥","💥","🌈",
        "☀️","🌙","🎵","🎶","🎤","🎧","📢","🔔","🎼","🎹",
        "🥁","🎷","🎺","🎸",
    ],
    "🍕 食物": [
        "🍕","🍔","🍟","🌭","🍿","🧂","🥓","🥚","🧇","🥞",
        "🍞","🥐","🍰","🎂","🧁","🍪","🍩","🍫","🍬","🍭",
        "🍦","🍨","☕","🍵","🧃","🥤","🧊","🍺","🍻","🥂",
        "🍷","🍸","🍹","🧉","🍾","🥡","🍜","🍝","🍣","🍤",
    ],
    "🐱 动物": [
        "🐱","🐶","🐼","🐨","🐸","🦊","🐰","🐤","🐻","🐯",
        "🦁","🐮","🐷","🐙","🦋","🐝","🦄","🐬","🐳","🦜",
        "🌻","🌹","🌸","🍀","🌲","🌵","🍄","🌍",
    ],
    "🚀 其他": [
        "🚀","✈️","🚗","🚲","⛵","🏠","🏖","🏔","🏆","⚽",
        "🏀","🎮","🎲","🧩","🎯","🎳","💻","📱","⌚","💡",
        "💰","🔑","🔒","🔓","✅","❌","❓","❗","💯","🔞","♻️",
        "🐱","🐶","🐼","🐨","🐸","🦊","🐰","🐤",
        "🌻","🌹","🌸","🍀","🌲","🌵","🍄","🌍",
    ],
}

# 分类显示名（去掉 emoji 前缀后的纯文字）
CATEGORY_NAMES = {k: k.split(" ", 1)[1] for k in EMOJI_DATA}


# ---------------------------------------------------------------------------
# 单个 Emoji 按钮
# ---------------------------------------------------------------------------
class _EmojiButton(QPushButton):
    hovered = Signal(str, str)   # (emoji, category_name)

    def __init__(self, emoji: str, category_name: str, parent=None):
        super().__init__(emoji, parent)
        self._emoji = emoji
        self._category_name = category_name
        self.setFixedSize(QSize(34, 34))
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setStyleSheet(f"""
            QPushButton {{
                font-size: 19px;
                border: none;
                border-radius: 6px;
                background-color: transparent;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: {BG_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {PRIMARY_LIGHT};
            }}
        """)

    def enterEvent(self, event):
        self.hovered.emit(self._emoji, self._category_name)
        super().enterEvent(event)


# ---------------------------------------------------------------------------
# 主弹窗
# ---------------------------------------------------------------------------
class EmojiPicker(QDialog):
    """表情选择弹窗。用户点击 emoji 后发射 emoji_selected 信号并关闭。"""
    emoji_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择表情")
        self.setFixedSize(QSize(424, 360))
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self._active_category: str = list(EMOJI_DATA.keys())[0]

        self._build_ui()
        # 默认选中第一个分类
        self._tab_bar.setCurrentIndex(0)
        self._load_grid(self._active_category)

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self):
        # 外层
        margin = 6
        outer = QVBoxLayout(self)
        outer.setContentsMargins(margin, margin, margin, margin)
        outer.setSpacing(0)

        # 卡片容器（统一圆角 + 边框，与文档中心/头像选择器一致）
        card = QFrame()
        card.setObjectName("emoji_card")
        card.setStyleSheet(f"""
            #emoji_card {{
                background-color: {BG_APP};
                border: 0.5px solid {BORDER};
                border-radius: {RADIUS_WINDOW}px;
            }}
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # 标题栏
        card_layout.addWidget(self._build_header())

        # 分隔线
        card_layout.addWidget(self._make_divider())

        # 分类 Tab 行
        card_layout.addWidget(self._build_tab_bar())

        # 分隔线
        card_layout.addWidget(self._make_divider())

        # Emoji 网格（ScrollArea）
        self._scroll = QScrollArea()
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{
                background: transparent;
                width: 4px;
                margin: 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER};
                border-radius: 2px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{ background: none; }}
        """)
        self._scroll.setFixedHeight(220)
        card_layout.addWidget(self._scroll)

        # 分隔线
        card_layout.addWidget(self._make_divider())

        # 底部预览栏
        card_layout.addWidget(self._build_footer())

        outer.addWidget(card)

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"""
            background-color: {BG_APP};
            border: none;
            border-top-left-radius: {RADIUS_WINDOW}px;
            border-top-right-radius: {RADIUS_WINDOW}px;
        """)
        row = QHBoxLayout(w)
        row.setContentsMargins(16, 11, 10, 11)
        row.setSpacing(8)

        title = QLabel("选择表情")
        title.setStyleSheet(f"""
            font-size: 14px;
            font-weight: 500;
            color: {TEXT_PRIMARY};
            background: transparent;
            border: none;
        """)
        row.addWidget(title)
        row.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(QSize(26, 26))
        close_btn.setCursor(QCursor(Qt.PointingHandCursor))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                border-radius: 6px;
                background: transparent;
                color: {TEXT_HINT};
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {BG_HOVER};
                color: {PRIMARY};
            }}
        """)
        close_btn.clicked.connect(self.reject)
        row.addWidget(close_btn)
        return w

    def _build_tab_bar(self) -> QWidget:
        """分类标签行：QTabBar，分类多时自动出现左右滚动箭头。"""
        self._tab_bar = QTabBar()
        self._tab_bar.setUsesScrollButtons(True)
        self._tab_bar.setExpanding(False)
        self._tab_bar.setCursor(QCursor(Qt.PointingHandCursor))
        self._tab_bar.setStyleSheet(f"""
            QTabBar {{
                background: transparent;
                border: none;
            }}
            QTabBar::tab {{
                font-size: 13px;
                color: {TEXT_SECONDARY};
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
                padding: 8px 12px;
            }}
            QTabBar::tab:selected {{
                color: {PRIMARY};
                font-weight: 500;
                border-bottom: 2px solid {PRIMARY};
            }}
            QTabBar::tab:hover:!selected {{
                color: {TEXT_PRIMARY};
            }}
            QTabBar::scroller {{
                width: 20px;
            }}
            QTabBar QToolButton {{
                border: none;
                background: transparent;
                color: {TEXT_HINT};
            }}
            QTabBar QToolButton:hover {{
                color: {PRIMARY};
            }}
        """)

        for cat in EMOJI_DATA.keys():
            self._tab_bar.addTab(cat)

        self._tab_bar.currentChanged.connect(self._on_tab_changed)
        return self._tab_bar

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(38)
        w.setStyleSheet(f"""
            background-color: {BG_APP};
            border: none;
            border-bottom-left-radius: {RADIUS_WINDOW}px;
            border-bottom-right-radius: {RADIUS_WINDOW}px;
        """)
        row = QHBoxLayout(w)
        row.setContentsMargins(14, 0, 14, 0)
        row.setSpacing(6)

        self._preview_emoji = QLabel("👋")
        self._preview_emoji.setStyleSheet(f"""
            font-size: 20px;
            background: transparent;
            border: none;
        """)
        row.addWidget(self._preview_emoji)

        self._preview_hint = QLabel("悬停预览  ·")
        self._preview_hint.setStyleSheet(f"""
            font-size: 12px;
            color: {TEXT_HINT};
            background: transparent;
            border: none;
        """)
        row.addWidget(self._preview_hint)

        self._preview_name = QLabel("手势")
        self._preview_name.setStyleSheet(f"""
            font-size: 12px;
            font-weight: 500;
            color: {TEXT_SECONDARY};
            background: transparent;
            border: none;
        """)
        row.addWidget(self._preview_name)
        row.addStretch()
        return w

    def _make_divider(self) -> QWidget:
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {BORDER}; border: none;")
        return line

    # ------------------------------------------------------------------
    # 逻辑
    # ------------------------------------------------------------------
    def _on_tab_changed(self, index: int):
        self._active_category = list(EMOJI_DATA.keys())[index]
        self._load_grid(self._active_category)

    def _load_grid(self, category: str):
        """重建 emoji 网格并设置到 scroll area。"""
        container = QWidget()
        container.setStyleSheet("background: transparent;")

        grid = QGridLayout(container)
        grid.setSpacing(2)
        grid.setContentsMargins(10, 8, 10, 8)

        cols = 10
        cat_name = CATEGORY_NAMES[category]
        for i, emoji in enumerate(EMOJI_DATA[category]):
            btn = _EmojiButton(emoji, cat_name)
            btn.hovered.connect(self._on_emoji_hover)
            btn.clicked.connect(lambda *_, e=emoji: self._on_emoji_click(e))
            grid.addWidget(btn, i // cols, i % cols)

        self._scroll.setWidget(container)

    def _on_emoji_hover(self, emoji: str, category_name: str):
        self._preview_emoji.setText(emoji)
        self._preview_name.setText(category_name)
        self._preview_hint.setText("悬停预览  ·")

    def _on_emoji_click(self, emoji: str):
        self._preview_emoji.setText(emoji)
        self._preview_hint.setText("已选择  ·")
        self.emoji_selected.emit(emoji)
        self.accept()

    # ------------------------------------------------------------------
    # 键盘
    # ------------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)


# ---------------------------------------------------------------------------
# 简单测试入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    picker = EmojiPicker()
    picker.emoji_selected.connect(lambda e: print(f"选择了：{e}"))
    picker.exec()