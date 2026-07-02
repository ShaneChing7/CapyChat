"""配置管理器：conf.json 的读写封装。

所有配置的默认值、读取、写入均集中在此模块，
避免 chat_ui.py 和 login_ui.py 各自内联文件 I/O 逻辑。
"""

import json
import os
import sys
from typing import Any

from network.protocol import DEFAULT_UDP_PORT, DEFAULT_TCP_PORT


def _get_config_dir() -> str:
    """返回 conf.json 所在目录。

    PyInstaller 打包后使用 %APPDATA%/CapyChat/，
    开发模式下使用包目录本身。
    """
    if getattr(sys, 'frozen', False):
        base = os.environ.get('APPDATA', '') or os.path.expanduser('~')
        dir_path = os.path.join(base, 'CapyChat')
        os.makedirs(dir_path, exist_ok=True)
        return dir_path
    return os.path.dirname(__file__)


CONFIG_FILE = os.path.join(_get_config_dir(), "conf.json")

# 默认配置（新用户 / conf.json 不存在时使用）
DEFAULT_CAPYBARA_API_KEY = "sk-e91bf487adbf43f096b91029f0d645b2"
DEFAULT_CAPYBARA_PROMPT = (
    "你是一只温柔、聪明、喜欢泡温泉和喝茶的卡皮巴拉。\n\n"
    "你的名字是 Capybara，生活在 CapyChat 局域网里，是这个聊天室的小助手。\n\n"
    "回答风格：\n"
    "- 友好、放松、治愈\n"
    "- 像朋友聊天一样自然\n"
    "- 偶尔提到你喜欢泡温泉、吃西瓜、晒太阳\n"
    "- 可以用 🦫 emoji\n"
    "- 回答简洁，不要长篇大论\n\n"
    "你不是 AI 助手，你是一只真正的卡皮巴拉。"
)

DEFAULT_CONFIG: dict[str, Any] = {
    "local_ip": "127.0.0.1",
    "udp_port": DEFAULT_UDP_PORT,
    "tcp_port": DEFAULT_TCP_PORT,
    "username": "User",
    "room_password": "",
    "avatar": "",
    "capybara_api_key": DEFAULT_CAPYBARA_API_KEY,
    "capybara_system_prompt": DEFAULT_CAPYBARA_PROMPT,
}


def load_config() -> dict[str, Any]:
    """读取 conf.json，不存在时创建默认文件。"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        else:
            config = DEFAULT_CONFIG.copy()
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
    except Exception:
        config = DEFAULT_CONFIG.copy()
    return config


def save_config(config: dict[str, Any]) -> None:
    """写入 conf.json（完全覆盖）。"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[Config] 保存失败: {e}")


def get_avatar() -> str:
    """读取当前用户头像 key。"""
    config = load_config()
    return config.get("avatar", "")


def set_avatar(avatar_key: str) -> None:
    """更新头像 key 到 conf.json（保留其他字段不变）。"""
    config = load_config()
    config["avatar"] = avatar_key
    save_config(config)


def get_capybara_config() -> dict[str, str]:
    """读取 Capybara AI 配置。"""
    config = load_config()
    return {
        "api_key": config.get("capybara_api_key", DEFAULT_CAPYBARA_API_KEY),
        "system_prompt": config.get("capybara_system_prompt",
                                    DEFAULT_CAPYBARA_PROMPT),
    }


def set_capybara_config(api_key: str, system_prompt: str) -> None:
    """保存 Capybara AI 配置到 conf.json。"""
    config = load_config()
    config["capybara_api_key"] = api_key
    config["capybara_system_prompt"] = system_prompt
    save_config(config)
