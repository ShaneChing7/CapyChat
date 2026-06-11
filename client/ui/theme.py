"""UI 色板 — 暖橙色调，类 Discord/Telegram 现代 IM 风格。

所有 UI 模块统一从此处导入颜色常量，禁止在组件中硬编码颜色值。
"""

# ---- 主色系 ----
PRIMARY = "#C8785A"
PRIMARY_DARK = "#B06448"
PRIMARY_LIGHT = "#F0DDD6"

# ---- 背景色 ----
BG_APP = "#FAF8F5"
BG_SIDEBAR = "#F2EDE7"
BG_INPUT = "#EDE8E2"
BG_MSG_OTHER = "#EDE8E2"
BG_HOVER = "#E8E2DB"

# ---- 边框 / 分隔线 ----
BORDER = "#E0D9D0"
BORDER_LIGHT = "#E8E2DB"

# ---- 文字色 ----
TEXT_PRIMARY = "#3A3028"
TEXT_SECONDARY = "#8A7D72"
TEXT_HINT = "#B0A49A"

# ---- 功能色 ----
GREEN_ONLINE = "#6AB87A"

# ---- 圆角 ----
RADIUS_WINDOW = 20
RADIUS_SM = 10
RADIUS_XS = 8
RADIUS_BUBBLE = 16
BUBBLE_CORNER_SMALL = 8

# ---- 头像色板（MD5 稳定哈希选色） ----
AVATAR_PALETTE = [
    "#F2994A",  # 暖橙
    "#A0BCDA",  # 浅蓝
    "#6FCF97",  # 翠绿
    "#BB6BD9",  # 紫色
    "#EB5757",  # 红色
    "#2D9CDB",  # 天蓝
    "#219653",  # 深绿
    "#F2C94C",  # 金黄
]

# ---- 窗口 ----
SHADOW_MARGIN = 16
SIDEBAR_WIDTH = 220
