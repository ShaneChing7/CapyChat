"""统一的资源路径解析工具。

开发模式下基于 __file__ 解析，
PyInstaller 打包后基于 sys._MEIPASS 解析。
"""

import os
import sys


def base_dir() -> str:
    """返回 capychat 包目录的绝对路径。

    开发模式:  E:\\CapyChat\\capychat\\
    打包模式:  <_MEIPASS>\\capychat\\
    """
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, 'capychat')
    # _paths.py 就在 capychat/ 里，不需要再往上一级
    return os.path.dirname(os.path.abspath(__file__))


def asset_dir(*parts: str) -> str:
    """返回 assets 子目录路径。"""
    return os.path.join(base_dir(), 'assets', *parts)
