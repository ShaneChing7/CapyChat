"""Capybara AI 设置面板 — API Key + 系统提示词配置。"""

import os

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QFrame, QTextEdit, QLineEdit,
                               QSizePolicy)
from PySide6.QtCore import Qt, QPoint, QSize
from PySide6.QtGui import QFont, QColor, QIcon

from .theme import (PRIMARY, PRIMARY_DARK, BG_APP, TEXT_PRIMARY,
                    TEXT_SECONDARY, TEXT_HINT, BORDER, RADIUS_WINDOW)

_ICONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                          "assets", "icons")

WIN_W = 480
WIN_H = 440


class CapybaraSettingsDialog(QDialog):
    """Capybara AI 设置面板 — 无边框、可拖拽。

    用法：
        dlg = CapybaraSettingsDialog(api_key="...", system_prompt="...", parent=self)
        if dlg.exec() == QDialog.Accepted:
            new_key = dlg.api_key
            new_prompt = dlg.system_prompt
    """

    def __init__(self, api_key: str = "", system_prompt: str = "",
                 parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedSize(WIN_W, WIN_H)

        self._api_key = api_key
        self._system_prompt = system_prompt
        self._drag_pos: QPoint | None = None

        self._init_ui()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def api_key(self) -> str:
        return self._api_key_input.text().strip()

    @property
    def system_prompt(self) -> str:
        return self._prompt_edit.toPlainText().strip()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        # ---- 最外层透明背景 --------------------------------------------
        self.setStyleSheet("background: transparent;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # ---- 容器卡片 --------------------------------------------------
        card = QFrame(self)
        card.setObjectName("card")
        card.setStyleSheet(f"""
            #card {{
                background: {BG_APP};
                border: 0.5px solid {BORDER};
                border-radius: {RADIUS_WINDOW}px;
            }}
        """)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # ---- 标题行 ----------------------------------------------------
        title_row = QHBoxLayout()
        title_row.setSpacing(0)

        title = QLabel("Capybara 设置")
        title.setStyleSheet(f"""
            QLabel {{
                font-size: 17px; font-weight: 700;
                color: {TEXT_PRIMARY};
                background: transparent; border: none;
                padding: 4px 0;
            }}
        """)
        title_row.addWidget(title)
        title_row.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(32, 32)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 16px; color: {TEXT_HINT};
                background: transparent; border: none;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                color: {TEXT_PRIMARY};
                background: rgba(0,0,0,0.06);
            }}
        """)
        close_btn.clicked.connect(self.reject)
        title_row.addWidget(close_btn)

        layout.addLayout(title_row)

        # ---- API Key ---------------------------------------------------
        key_label = QLabel("API Key")
        key_label.setStyleSheet(f"""
            font-size: 13px; font-weight: 600;
            color: {TEXT_PRIMARY}; background: transparent; border: none;
        """)
        layout.addWidget(key_label)

        self._api_key_input = QLineEdit(self._api_key)
        self._api_key_input.setPlaceholderText("输入 DeepSeek API Key...")
        self._api_key_input.setEchoMode(QLineEdit.Password)
        self._api_key_input.setStyleSheet(f"""
            QLineEdit {{
                font-size: 14px; color: {TEXT_PRIMARY};
                background: #F8F5F0; border: 0.5px solid {BORDER};
                border-radius: 10px; padding: 10px 14px;
            }}
            QLineEdit:focus {{ border-color: {PRIMARY}; }}
        """)
        layout.addWidget(self._api_key_input)

        # ---- 切换可见性按钮 --------------------------------------------
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(0)
        toggle_row.addStretch()
        self._toggle_btn = QPushButton(" 显示")
        self._eye_open_icon = QIcon(os.path.join(_ICONS_DIR, "eye.svg"))
        self._eye_closed_icon = QIcon(os.path.join(_ICONS_DIR, "eye-closed.svg"))
        self._toggle_btn.setIcon(self._eye_open_icon)
        self._toggle_btn.setIconSize(QSize(16, 16))
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 12px; color: {TEXT_HINT};
                background: transparent; border: none;
                padding: 2px 6px;
            }}
            QPushButton:hover {{ color: {PRIMARY}; }}
        """)
        self._toggle_btn.clicked.connect(self._toggle_key_visible)
        toggle_row.addWidget(self._toggle_btn)
        layout.addLayout(toggle_row)

        # ---- 系统提示词 ------------------------------------------------
        prompt_label = QLabel("系统提示词")
        prompt_label.setStyleSheet(f"""
            font-size: 13px; font-weight: 600;
            color: {TEXT_PRIMARY}; background: transparent; border: none;
        """)
        layout.addWidget(prompt_label)

        self._prompt_edit = QTextEdit()
        self._prompt_edit.setPlainText(self._system_prompt)
        self._prompt_edit.setAcceptRichText(False)
        self._prompt_edit.setStyleSheet(f"""
            QTextEdit {{
                font-size: 13px; color: {TEXT_PRIMARY};
                background: #F8F5F0; border: 0.5px solid {BORDER};
                border-radius: 10px; padding: 10px 14px;
            }}
            QTextEdit:focus {{ border-color: {PRIMARY}; }}
            QScrollBar:vertical {{
                background: transparent; width: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER}; border-radius: 2px;
            }}
        """)
        layout.addWidget(self._prompt_edit, 1)

        # ---- 按钮行 ----------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        reset_btn = QPushButton("恢复默认")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 14px; color: {TEXT_SECONDARY};
                background: transparent; border: 0.5px solid {BORDER};
                border-radius: 10px; padding: 8px 18px;
            }}
            QPushButton:hover {{
                color: {TEXT_PRIMARY};
                border-color: {TEXT_SECONDARY};
            }}
        """)
        reset_btn.clicked.connect(self._on_reset)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()

        save_btn = QPushButton("保存")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 14px; font-weight: 600;
                color: #ffffff; background: {PRIMARY};
                border: none; border-radius: 10px;
                padding: 8px 28px;
            }}
            QPushButton:hover {{ background: {PRIMARY_DARK}; }}
        """)
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # 交互
    # ------------------------------------------------------------------

    def _toggle_key_visible(self):
        if self._api_key_input.echoMode() == QLineEdit.Password:
            # 隐藏 → 可见，切换后按钮显示"隐藏"
            self._api_key_input.setEchoMode(QLineEdit.Normal)
            self._toggle_btn.setIcon(self._eye_closed_icon)
            self._toggle_btn.setText(" 隐藏")
        else:
            # 可见 → 隐藏，切换后按钮显示"显示"
            self._api_key_input.setEchoMode(QLineEdit.Password)
            self._toggle_btn.setIcon(self._eye_open_icon)
            self._toggle_btn.setText(" 显示")

    def _on_reset(self):
        from config_manager import DEFAULT_CAPYBARA_API_KEY, DEFAULT_CAPYBARA_PROMPT
        self._api_key_input.setText(DEFAULT_CAPYBARA_API_KEY)
        self._prompt_edit.setPlainText(DEFAULT_CAPYBARA_PROMPT)

    # ------------------------------------------------------------------
    # 拖拽
    # ------------------------------------------------------------------

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
