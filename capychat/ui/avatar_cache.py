"""头像缓存系统：SVG 渲染缓存 + MD5 稳定色板 + AvatarWidget 组件。

设计目标：
  - 避免重复创建 QSvgRenderer
  - 渲染后 QPixmap 按 (key, size) 缓存
  - MD5 哈希确保同一用户名在所有客户端显示一致颜色
  - AvatarWidget 统一替换现有的 _CircleAvatar / _AvatarLabel
"""

import hashlib
import os
from typing import Optional

from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt, QSize, QRectF, Signal
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QPainterPath
from PySide6.QtSvg import QSvgRenderer

from .theme import AVATAR_PALETTE
from capychat._paths import asset_dir


# =============================================================================
# 头像色板工具
# =============================================================================

def get_avatar_color(username: str) -> str:
    """使用 MD5 哈希从色板中稳定选取颜色。

    同一用户名 → 同一索引 → 同一颜色。
    零网络开销，所有客户端独立计算但结果一致。
    """
    if not username:
        return AVATAR_PALETTE[0]
    hash_bytes = hashlib.md5(username.encode()).digest()
    index = hash_bytes[0] % len(AVATAR_PALETTE)
    return AVATAR_PALETTE[index]


# =============================================================================
# 头像目录路径（相对于 client/ 目录）
# =============================================================================

def _avatars_dir() -> str:
    """返回 assets/avatars/ 目录的绝对路径。"""
    return asset_dir('avatars')


# =============================================================================
# AvatarCache — 单例模式，全局共享
# =============================================================================

class AvatarCache:
    """头像渲染缓存（单例）。

    用法：
        pixmap = avatar_cache.get_pixmap("fox", "Alice", 38)
        # 若 "fox" → 渲染 fox.svg 为圆形 QPixmap
        # 若 ""    → 渲染 Alice 首字母 + 稳定色圆形 QPixmap
    """

    _instance: Optional["AvatarCache"] = None

    def __new__(cls) -> "AvatarCache":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_cache()
        return cls._instance

    def _init_cache(self) -> None:
        """初始化内部缓存结构。"""
        self._svg_renderers: dict[str, QSvgRenderer] = {}
        self._pixmap_cache: dict[tuple, QPixmap] = {}
        self._avatars_dir = _avatars_dir()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_pixmap(self, avatar_key: str, username: str,
                   size: int) -> QPixmap:
        """获取渲染后的圆形头像 QPixmap。

        Args:
            avatar_key: 头像标识（"" 表示首字母头像，"fox" 等表示 SVG）
            username:   用户名（用于首字母头像的颜色和文字）
            size:       输出尺寸（正方形边长，像素）

        Returns:
            已渲染为圆形的 QPixmap
        """
        # 构建缓存键
        if avatar_key:
            cache_key = ("svg", avatar_key, size)
        else:
            cache_key = ("letter", username, size)

        # 命中缓存
        cached = self._pixmap_cache.get(cache_key)
        if cached is not None:
            return cached

        # 渲染
        if avatar_key:
            pixmap = self._render_svg(avatar_key, size)
        else:
            pixmap = self._render_letter(username, size)

        # 存入缓存
        self._pixmap_cache[cache_key] = pixmap
        return pixmap

    def has_svg(self, avatar_key: str) -> bool:
        """检查指定 key 对应的头像文件是否存在（SVG 或 PNG）。"""
        if not avatar_key:
            return False
        # SVG
        if os.path.exists(os.path.join(self._avatars_dir, f"{avatar_key}.svg")):
            return True
        # PNG（capybara_avatar.png 模式）
        for png_name in (f"{avatar_key}_avatar.png", f"{avatar_key}.png"):
            if os.path.exists(os.path.join(self._avatars_dir, png_name)):
                return True
        return False

    def clear_cache(self) -> None:
        """清空所有缓存（通常在头像选择变更后调用）。"""
        self._pixmap_cache.clear()

    # ------------------------------------------------------------------
    # 内部渲染 — SVG
    # ------------------------------------------------------------------

    def _render_svg(self, avatar_key: str, size: int) -> QPixmap:
        """将头像文件渲染为圆形 QPixmap（支持 SVG 和 PNG）。"""
        # 1. 优先尝试 SVG（普通用户头像）
        svg_path = os.path.join(self._avatars_dir, f"{avatar_key}.svg")
        if os.path.exists(svg_path):
            return self._render_svg_file(avatar_key, svg_path, size)

        # 2. 尝试 PNG（capybara_avatar → capybara_avatar.png）
        for png_name in (f"{avatar_key}_avatar.png", f"{avatar_key}.png"):
            png_path = os.path.join(self._avatars_dir, png_name)
            if os.path.exists(png_path):
                return self._render_png_file(png_path, size)

        # 3. 回退到首字母头像
        return self._render_letter("?", size)

    # ------------------------------------------------------------------
    # SVG 渲染
    # ------------------------------------------------------------------

    def _render_svg_file(self, avatar_key: str, svg_path: str,
                         size: int) -> QPixmap:
        """渲染 SVG 文件为圆形 QPixmap。"""
        renderer = self._svg_renderers.get(avatar_key)
        if renderer is None:
            renderer = QSvgRenderer(svg_path)
            self._svg_renderers[avatar_key] = renderer

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        clip_path = QPainterPath()
        clip_path.addEllipse(0, 0, size, size)
        painter.setClipPath(clip_path)

        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        return pixmap

    # ------------------------------------------------------------------
    # PNG 渲染
    # ------------------------------------------------------------------

    def _render_png_file(self, png_path: str, size: int) -> QPixmap:
        """渲染 PNG 文件为圆形 QPixmap。"""
        source = QPixmap(png_path)
        scaled = source.scaled(
            size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        clip_path = QPainterPath()
        clip_path.addEllipse(0, 0, size, size)
        painter.setClipPath(clip_path)

        # 居中绘制缩放后的图片
        ox = (size - scaled.width()) // 2
        oy = (size - scaled.height()) // 2
        painter.drawPixmap(ox, oy, scaled)
        painter.end()
        return pixmap

    # ------------------------------------------------------------------
    # 内部渲染 — 首字母头像
    # ------------------------------------------------------------------

    def _render_letter(self, username: str, size: int) -> QPixmap:
        """渲染首字母圆形头像。"""
        color = get_avatar_color(username)
        letter = username[0].upper() if username else "?"

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # 圆形背景
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(0, 0, size, size)

        # 白色首字母
        painter.setPen(QColor("#ffffff"))
        font_size = max(10, int(size / 2.6))
        font = QFont()
        font.setPixelSize(font_size)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(0, 0, size, size),
                         Qt.AlignCenter, letter)

        painter.end()
        return pixmap


# =============================================================================
# 全局单例
# =============================================================================

avatar_cache = AvatarCache()


# =============================================================================
# AvatarWidget — 统一的头像显示组件
# =============================================================================

class AvatarWidget(QLabel):
    """统一的圆形头像组件，替换原有的 _CircleAvatar / _AvatarLabel。

    支持：
      - 首字母头像（avatar_key=""）：MD5 稳定色 + 白色首字母
      - SVG 预设头像（avatar_key="fox"）：圆形裁切渲染

    用法：
        avatar = AvatarWidget(username="Alice", avatar_key="fox", size=38)
        avatar.set_avatar("Bob", "")  # 运行时切换

    信号：
        clicked — 点击头像时发射（用于弹出选择器）
    """

    clicked = Signal()  # 点击头像时发射

    def __init__(self, username: str = "", avatar_key: str = "",
                 size: int = 38, parent=None):
        """初始化头像组件。

        Args:
            username:   用户名（首字母头像时必需）
            avatar_key: 头像标识（""=首字母，"fox"=SVG）
            size:       头像尺寸（正方形边长，像素）
            parent:     父级 QWidget
        """
        super().__init__(parent)
        self._username = username
        self._avatar_key = avatar_key
        self._size = size

        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                background: transparent;
                border: none;
                padding: 0;
            }
        """)

        self._render_and_show()

    def mousePressEvent(self, event) -> None:
        """鼠标点击时发射 clicked 信号。"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_avatar(self, username: str, avatar_key: str) -> None:
        """运行时更新头像。

        Args:
            username:   新用户名
            avatar_key: 新头像标识
        """
        if self._username == username and self._avatar_key == avatar_key:
            return
        self._username = username
        self._avatar_key = avatar_key
        self._render_and_show()

    def avatar_key(self) -> str:
        """返回当前头像标识。"""
        return self._avatar_key

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _render_and_show(self) -> None:
        """从缓存获取或渲染 pixmap 并显示。"""
        pixmap = avatar_cache.get_pixmap(
            self._avatar_key, self._username, self._size)
        if pixmap and not pixmap.isNull():
            self.setPixmap(pixmap)
