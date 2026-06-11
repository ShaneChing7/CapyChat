"""CapybaraAgent — DeepSeek-V4 API 封装，卡皮巴拉人格系统提示词。

使用 QThread 异步请求，通过信号驱动 UI 更新（不阻塞界面）。

用法：
    agent = CapybaraAgent(api_key="sk-...")
    agent.thinking_started.connect(capy_widget.set_thinking(True))
    agent.chunk_received.connect(lambda text: chat_area.append(text))
    agent.response_complete.connect(capy_widget.set_thinking(False))
    agent.ask("你好")
"""

import json
import requests
from PySide6.QtCore import QObject, Signal, QThread


DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"

SYSTEM_PROMPT = """你是一只温柔、聪明、喜欢泡温泉和喝茶的卡皮巴拉。

你的名字是 Capybara，生活在 LANChat 局域网里，是这个聊天室的小助手。

回答风格：
- 友好、放松、治愈
- 像朋友聊天一样自然
- 偶尔提到你喜欢泡温泉、吃西瓜、晒太阳
- 可以用 🦫 emoji
- 回答简洁，不要长篇大论

你不是 AI 助手，你是一只真正的卡皮巴拉。"""


class _AskWorker(QObject):
    """后台线程执行 HTTP 流式请求。"""

    finished = Signal(str)           # 完整响应文本
    chunk = Signal(str)              # 每个 token
    error = Signal(str)              # 错误消息

    def __init__(self, api_key: str, messages: list[dict], parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._messages = messages

    def run(self):
        """在 QThread 中执行。"""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        body = {
            "model": MODEL,
            "messages": self._messages,
            "stream": True,
        }
        full_text = ""
        try:
            resp = requests.post(
                DEEPSEEK_URL, headers=headers, json=body,
                stream=True, timeout=60)
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_text += content
                        self.chunk.emit(content)
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
        except requests.RequestException as e:
            self.error.emit(str(e))
            return
        except Exception as e:
            self.error.emit(f"未知错误: {e}")
            return
        self.finished.emit(full_text)


class CapybaraAgent(QObject):
    """卡皮巴拉 AI 助手 — 管理对话历史 + 异步 API 调用。

    信号：
        thinking_started  — 开始请求
        chunk_received    — 收到一个 token 文本
        response_complete — 完整响应结束（参数：完整文本）
        error_occurred    — 请求失败
    """

    thinking_started = Signal()
    chunk_received = Signal(str)
    response_complete = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, api_key: str = "", system_prompt: str = "", parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._system_prompt = system_prompt or SYSTEM_PROMPT
        self._messages: list[dict] = [
            {"role": "system", "content": self._system_prompt}
        ]
        self._thread: QThread | None = None
        self._worker: _AskWorker | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_api_key(self, key: str) -> None:
        self._api_key = key

    def set_system_prompt(self, prompt: str) -> None:
        """更新系统提示词并重建对话。"""
        self._system_prompt = prompt
        self.reset_conversation()

    def reset_conversation(self) -> None:
        """清空对话历史，保留当前系统提示词。"""
        prompt = getattr(self, '_system_prompt', SYSTEM_PROMPT) or SYSTEM_PROMPT
        self._messages = [{"role": "system", "content": prompt}]

    def ask(self, user_message: str) -> None:
        """发送用户消息，异步获取回复。"""
        if not self._api_key:
            self.error_occurred.emit("未设置 API Key")
            return

        self._messages.append({"role": "user", "content": user_message})
        self.thinking_started.emit()

        # 创建后台线程
        self._thread = QThread(self)
        self._worker = _AskWorker(self._api_key, list(self._messages))
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.chunk.connect(self._on_chunk)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _on_chunk(self, text: str) -> None:
        self.chunk_received.emit(text)

    def _on_finished(self, full_text: str) -> None:
        if full_text:
            self._messages.append(
                {"role": "assistant", "content": full_text})
        self.response_complete.emit(full_text)

    def _on_error(self, error_msg: str) -> None:
        self.error_occurred.emit(error_msg)
        # 移除未得到回复的用户消息
        if self._messages and self._messages[-1]["role"] == "user":
            self._messages.pop()
