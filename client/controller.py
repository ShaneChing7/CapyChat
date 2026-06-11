"""ChatController — 聊天业务逻辑层。

从 ChatWindow 抽离所有信号处理、消息发送、文件传输管理，
ChatWindow 仅保留纯 UI（布局、渲染、窗口控制）。

职责：
  - 网络信号接线（UDP/TCP → UI 更新）
  - 消息发送（文本 / 图片 / 视频 / 音频 / 文件）
  - 频道切换管理
  - 头像同步
  - 文件传输进度管理
"""

import os
import base64
import subprocess
import platform
from datetime import datetime

from PySide6.QtWidgets import (QWidget, QMessageBox, QFileDialog, QDialog,
                               QVBoxLayout, QHBoxLayout, QLabel, QPushButton)
from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QPainter, QColor

from network.protocol import format_size
from ui.theme import (BG_APP, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_HINT,
                      PRIMARY, PRIMARY_DARK, RADIUS_XS)
from ui.chat_area import ChatAreaWidget
from ui.document_center import DocumentCenterDialog
from ui.emoji_picker import EmojiPicker
from config_manager import (set_avatar as config_set_avatar,
                            get_capybara_config, set_capybara_config)
from ai.capybara_agent import CapybaraAgent


class ChatController(QObject):
    """聊天业务逻辑控制器。

    持有 ChatWindow 引用，通过 window 访问 UI 组件。
    ChatWindow 在 __init__ 中创建本控制器并传入 self。
    """

    def __init__(self, window: "ChatWindow", username: str, local_ip: str,
                 tcp_port: int, udp, tcp, avatar: str = ""):
        super().__init__(parent=window)
        self.window = window
        self.username = username
        self.local_ip = local_ip
        self.tcp_port = tcp_port
        self.udp = udp
        self.tcp = tcp
        self.avatar = avatar

        # 数据字典（供 UI 层读取）
        self.contact_avatars: dict[str, str] = {}   # username → avatar_key
        self.online_users: list = []                 # 缓存供文档中心
        self.file_meta: dict[str, tuple] = {}        # file_id → (name, size, sender, addr)
        self.progress_bars: dict[str, QWidget] = {}
        self.pending_progress: dict[str, object] = {}

        # Capybara AI Agent（从配置文件加载）
        capy_cfg = get_capybara_config()
        self._capybara_agent = CapybaraAgent(
            api_key=capy_cfg["api_key"],
            system_prompt=capy_cfg["system_prompt"])
        self._capybara_agent.thinking_started.connect(self._on_capy_thinking)
        self._capybara_agent.chunk_received.connect(self._on_capy_chunk)
        self._capybara_agent.response_complete.connect(self._on_capy_done)
        self._capybara_agent.error_occurred.connect(self._on_capy_error)

        self._connect_network_signals()

    # ==================================================================
    # 网络信号绑定
    # ==================================================================

    def _connect_network_signals(self) -> None:
        if self.udp:
            self.udp.user_online.connect(self._on_user_online)
            self.udp.user_offline.connect(self._on_user_offline)
            self.udp.user_list_updated.connect(self._on_user_list)
            self.udp.group_message_received.connect(self._on_group_message)
            self.udp.error.connect(lambda e: print(f"[UDP] {e}"))

        if self.tcp:
            self.tcp.private_message_received.connect(self._on_private_message)
            self.tcp.private_image_received.connect(self._on_private_image)
            self.tcp.file_request.connect(self._on_file_request)
            self.tcp.file_progress.connect(self._on_file_progress)
            self.tcp.file_received.connect(self._on_file_received)
            self.tcp.file_sent.connect(self._on_file_sent)
            self.tcp.file_cancelled.connect(self._on_file_cancelled)
            self.tcp.peer_connected.connect(
                lambda u, a: print(f"[P2P] connected: {u or a}"))
            self.tcp.peer_disconnected.connect(
                lambda a: print(f"[P2P] disconnected: {a}"))
            self.tcp.error.connect(lambda e: print(f"[TCP] {e}"))

    # ==================================================================
    # ChatArea factory
    # ==================================================================

    def make_chat_area(self, channel_id: str, title: str) -> ChatAreaWidget:
        area = ChatAreaWidget()
        area.set_channel(channel_id, title)
        area.send_message_signal.connect(
            lambda text, cid=channel_id: self._send_text(cid, text))
        area.send_image_signal.connect(
            lambda cid=channel_id: self._send_media(cid, "assets"))
        area.send_video_signal.connect(
            lambda cid=channel_id: self._send_media(cid, "video"))
        area.send_audio_signal.connect(
            lambda cid=channel_id: self._send_media(cid, "audio"))
        area.send_file_signal.connect(
            lambda cid=channel_id: self._send_media(cid, "file"))
        area.emoji_picker_signal.connect(self._show_emoji_picker)
        self.window.chat_areas[channel_id] = area
        return area

    def ensure_private_area(self, addr: str, username: str = "") -> None:
        if addr not in self.window.chat_areas:
            title = username or "私聊"
            area = self.make_chat_area(addr, title)
            self.window.chat_stack.addWidget(area)
        elif username:
            area = self.window.chat_areas[addr]
            area.set_channel(addr, username)

    # ==================================================================
    # 频道切换
    # ==================================================================

    def on_channel_selected(self, channel_id: str) -> None:
        win = self.window
        if channel_id == win.current_channel:
            return
        win.current_channel = channel_id

        if channel_id not in win.chat_areas:
            title = win.sidebar.get_channel_name(channel_id)
            self.make_chat_area(channel_id, title)
            win.chat_stack.addWidget(win.chat_areas[channel_id])

        win.chat_stack.setCurrentWidget(win.chat_areas[channel_id])
        win.sidebar.set_active_channel(channel_id)
        win.sidebar.clear_unread(channel_id)

        # 切换到 Capybara 频道时重置对话
        if channel_id == "capybara":
            self._capybara_agent.reset_conversation()

    # ==================================================================
    # 头像变更
    # ==================================================================

    def on_avatar_changed(self, avatar_key: str) -> None:
        self.avatar = avatar_key
        config_set_avatar(avatar_key)
        if self.udp:
            self.udp.avatar = avatar_key
            self.udp.announce_now()

    # ==================================================================
    # UDP 事件
    # ==================================================================

    def _on_user_online(self, username, ip, tcp_port, avatar="") -> None:
        self.window.sidebar.add_user(username, ip, tcp_port, avatar)
        self.contact_avatars[username] = avatar
        area = self.window.chat_areas.get("group")
        if area:
            area.add_system_msg(f"{username} 加入了聊天室")

    def _on_user_offline(self, username, ip) -> None:
        win = self.window
        win.sidebar.remove_user(username)
        for key in list(win.chat_areas.keys()):
            if key != "group" and ip in key:
                area = win.chat_areas.pop(key)
                win.chat_stack.removeWidget(area)
                area.deleteLater()
                if win.current_channel == key:
                    win.current_channel = "group"
                    win.chat_stack.setCurrentWidget(win.chat_areas["group"])
                    win.sidebar.set_active_channel("group")
        area = win.chat_areas.get("group")
        if area:
            area.add_system_msg(f"{username} 离开了聊天室")

    def _on_user_list(self, users) -> None:
        filtered = [(u, ip, p, a) for u, ip, p, a in users
                    if not (ip == self.local_ip and p == self.tcp_port)]
        self.online_users = filtered
        for u, _, _, a in filtered:
            self.contact_avatars[u] = a
        self.window.sidebar.update_user_list(filtered)
        self.window.sidebar.set_group_online(len(filtered) > 0)
        area = self.window.chat_areas.get("group")
        if area:
            area.set_online_count(len(filtered))

    def _on_group_message(self, username, ip, content, timestamp) -> None:
        area = self.window.chat_areas.get("group")
        if area:
            is_mine = (ip == self.local_ip)
            avatar = self.contact_avatars.get(username, "")
            area.add_message(username, content, timestamp,
                           is_mine=is_mine, avatar=avatar)

    # ==================================================================
    # TCP P2P 事件
    # ==================================================================

    def _on_private_message(self, username, ip, port, content, timestamp) -> None:
        addr = f"{ip}:{port}"
        self.ensure_private_area(addr, username)
        area = self.window.chat_areas.get(addr)
        if area:
            is_mine = (ip == self.local_ip)
            avatar = self.contact_avatars.get(username, "")
            area.add_message(username, content, timestamp,
                           is_mine=is_mine, avatar=avatar)
        if addr != self.window.current_channel:
            self.window.sidebar.add_unread(addr)

    def _on_private_image(self, username, ip, port, image_data,
                          image_ext, file_name) -> None:
        addr = f"{ip}:{port}"
        self.ensure_private_area(addr, username)
        area = self.window.chat_areas.get(addr)
        if area:
            recv_dir = os.path.join(os.path.dirname(__file__), "received")
            os.makedirs(recv_dir, exist_ok=True)
            save_path = os.path.join(recv_dir,
                                     f"{datetime.now().strftime('%H%M%S')}_{file_name}")
            avatar = self.contact_avatars.get(username, "")
            try:
                raw = base64.b64decode(image_data)
                with open(save_path, "wb") as f:
                    f.write(raw)
                is_mine = (ip == self.local_ip)
                ts = datetime.now().strftime("%H:%M")
                area.add_image(save_path, is_mine=is_mine,
                               sender=username, timestamp=ts,
                               avatar=avatar if not is_mine else self.avatar)
            except Exception:
                area.add_system_msg(f"[图片] {file_name} (解码失败)")
        if addr != self.window.current_channel:
            self.window.sidebar.add_unread(addr)

    # ==================================================================
    # 文件传输事件
    # ==================================================================

    def _on_file_request(self, file_id, sender, sender_ip, sender_port,
                         file_name, file_size, file_ext) -> None:
        addr = f"{sender_ip}:{sender_port}"
        self.file_meta[file_id] = (file_name, file_size, sender, addr)
        dlg = _FileRequestDialog(sender, file_name, file_size, self.window)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.tcp.respond_file_request(file_id, addr, True)
            self._add_progress_bar(file_id, file_name, file_size)
        else:
            self.tcp.respond_file_request(file_id, addr, False)

    def _on_file_progress(self, progress) -> None:
        bar = self.progress_bars.get(progress.file_id)
        if bar:
            bar.update_progress(progress)
            if progress.done:
                bar.set_done()
        else:
            self.pending_progress[progress.file_id] = progress

    def _on_file_received(self, file_id, file_path, file_name) -> None:
        bar = self.progress_bars.get(file_id)
        if bar:
            bar.set_done()
            QTimer.singleShot(3000, lambda: self._remove_progress_bar(file_id))
        meta = self.file_meta.pop(file_id, (file_name, 0, "", ""))
        addr = meta[3]
        if addr:
            self.ensure_private_area(addr, meta[2])
        area = self.window.chat_areas.get(addr) if addr else self.window.chat_areas.get("group")
        sender_name = meta[2]
        if area:
            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else meta[1]
            ts = datetime.now().strftime("%H:%M")
            avatar = self.contact_avatars.get(sender_name, "")
            area.add_file_card(file_name=file_name, file_size=file_size,
                               is_mine=False, sender=sender_name,
                               timestamp=ts, avatar=avatar)
        if addr and addr != self.window.current_channel:
            self.window.sidebar.add_unread(addr)

    def _on_file_sent(self, file_id, file_name) -> None:
        bar = self.progress_bars.get(file_id)
        if bar:
            bar.set_done()
            QTimer.singleShot(3000, lambda: self._remove_progress_bar(file_id))
        self.file_meta.pop(file_id, None)

    def _on_file_cancelled(self, file_id) -> None:
        bar = self.progress_bars.get(file_id)
        if bar:
            bar.set_error("已取消")
            QTimer.singleShot(3000, lambda: self._remove_progress_bar(file_id))
        self.file_meta.pop(file_id, None)

    # ==================================================================
    # Capybara AI
    # ==================================================================

    def _send_to_capybara(self, text: str) -> None:
        """用户消息 → CapybaraAgent。"""
        area = self.window.chat_areas.get("capybara")
        if area:
            ts = datetime.now().strftime("%H:%M")
            area.add_message(self.username, text, ts,
                           is_mine=True, avatar=self.avatar)
        self._capybara_agent.ask(text)

    def _on_capy_thinking(self) -> None:
        """Capybara 开始思考 → 创建带头像的气泡占位 + 侧边栏动画。"""
        self.window.sidebar.capybara_widget.set_thinking(True)
        # 确保 capybara 聊天区域存在
        if "capybara" not in self.window.chat_areas:
            self.make_chat_area("capybara", "🦫 Capybara")
            self.window.chat_stack.addWidget(
                self.window.chat_areas["capybara"])
        # 立即创建带 Capybara 头像的空气泡，避免后续抖动
        area = self.window.chat_areas.get("capybara")
        if area:
            ts = datetime.now().strftime("%H:%M")
            area.message_list.start_stream(
                "🦫 Capybara", "capybara_avatar", ts)

    def _on_capy_chunk(self, text: str) -> None:
        """流式输出 token → 更新气泡文字。"""
        area = self.window.chat_areas.get("capybara")
        if area:
            area.message_list.append_stream(text)

    def _on_capy_done(self, full_text: str) -> None:
        """Capybara 回答完成 → 清理流状态 + 更新动画。"""
        self.window.sidebar.capybara_widget.set_thinking(False)
        area = self.window.chat_areas.get("capybara")
        if area:
            area.message_list.finish_stream()

    def _on_capy_error(self, error_msg: str) -> None:
        """API 错误处理。"""
        self.window.sidebar.capybara_widget.set_thinking(False)
        area = self.window.chat_areas.get("capybara")
        if area:
            area.message_list.finish_stream()
            area.add_system_msg(f"🦫 Capybara 暂时无法回答：{error_msg}")

    def _on_capy_settings(self) -> None:
        """打开 Capybara 设置面板，保存后更新 Agent 配置。"""
        capy_cfg = get_capybara_config()
        from ui.capybara_settings import CapybaraSettingsDialog
        dlg = CapybaraSettingsDialog(
            api_key=capy_cfg["api_key"],
            system_prompt=capy_cfg["system_prompt"],
            parent=self.window)
        if dlg.exec() == QDialog.Accepted:
            new_key = dlg.api_key
            new_prompt = dlg.system_prompt
            set_capybara_config(new_key, new_prompt)
            self._capybara_agent.set_api_key(new_key)
            self._capybara_agent.set_system_prompt(new_prompt)

    # ==================================================================
    # 发送
    # ==================================================================

    def _send_text(self, channel_id: str, text: str) -> None:
        if channel_id == "capybara":
            self._send_to_capybara(text)
            return
        if channel_id == "group":
            if self.udp:
                self.udp.send_group_message(text)
            area = self.window.chat_areas.get("group")
            if area:
                ts = datetime.now().strftime("%H:%M")
                area.add_message(self.username, text, ts,
                               is_mine=True, avatar=self.avatar)
        else:
            ip, port = channel_id.split(":")
            if self.tcp:
                ok = self.tcp.send_private_message(ip, int(port), text)
                if not ok:
                    QMessageBox.warning(self.window, "发送失败", "无法连接到对方")
                    return
            area = self.window.chat_areas.get(channel_id)
            if area:
                ts = datetime.now().strftime("%H:%M")
                area.add_message(self.username, text, ts,
                               is_mine=True, avatar=self.avatar)

    def _send_media(self, channel_id: str, media_type: str) -> None:
        if media_type == "assets":
            self._do_send_image(channel_id)
        elif media_type == "video":
            self._do_send_video(channel_id)
        elif media_type == "audio":
            self._do_send_audio(channel_id)
        elif media_type == "file":
            self._do_send_file(channel_id)

    def _do_send_image(self, channel_id: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.window, "选择图片", "",
            "图片 (*.png *.jpg *.jpeg *.gif *.bmp);;所有文件 (*.*)")
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            encoded = base64.b64encode(data).decode()
            _, ext = os.path.splitext(path)
            name = os.path.basename(path)
            area = self.window.chat_areas.get(channel_id)

            if channel_id == "group":
                if len(encoded) > 30000:
                    QMessageBox.warning(self.window, "图片过大", "群聊图片建议小于20KB")
                    return
                if area:
                    ts = datetime.now().strftime("%H:%M")
                    area.add_image(path, is_mine=True,
                                   sender=self.username, timestamp=ts,
                                   avatar=self.avatar)
                for addr in list(self.window.chat_areas.keys()):
                    if addr != "group" and self.tcp:
                        ip, port = addr.split(":")
                        self.tcp.send_private_image(ip, int(port), encoded, ext, name)
            else:
                ip, port = channel_id.split(":")
                ok = self.tcp.send_private_image(ip, int(port), encoded, ext, name)
                if not ok:
                    QMessageBox.warning(self.window, "发送失败", "无法连接到对方")
                    return
                if area:
                    ts = datetime.now().strftime("%H:%M")
                    area.add_image(path, is_mine=True,
                                   sender=self.username, timestamp=ts,
                                   avatar=self.avatar)
        except Exception as e:
            QMessageBox.warning(self.window, "发送失败", str(e))

    def _do_send_video(self, channel_id: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.window, "选择视频", "",
            "视频 (*.mp4 *.avi *.mkv *.mov);;所有文件 (*.*)")
        if not path:
            return
        if os.path.getsize(path) > 50 * 1024 * 1024:
            QMessageBox.warning(self.window, "文件过大", "视频不超过50MB")
            return
        self._send_file(channel_id, path)

    def _do_send_audio(self, channel_id: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self.window, "选择音频", "",
            "音频 (*.mp3 *.wav *.ogg *.m4a);;所有文件 (*.*)")
        if not path:
            return
        if os.path.getsize(path) > 50 * 1024 * 1024:
            QMessageBox.warning(self.window, "文件过大", "音频不超过50MB")
            return
        self._send_file(channel_id, path)

    def _do_send_file(self, channel_id: str) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self.window, "选择文件", "", "所有文件 (*.*)")
        for p in paths:
            self._send_file(channel_id, p)

    def _send_file(self, channel_id: str, file_path: str) -> None:
        name = os.path.basename(file_path)
        size = os.path.getsize(file_path)
        area = self.window.chat_areas.get(channel_id)
        if area:
            ts = datetime.now().strftime("%H:%M")
            area.add_file_card(file_name=name, file_size=size,
                               is_mine=True, sender=self.username,
                               timestamp=ts, avatar=self.avatar)

        if channel_id == "group":
            for addr in list(self.window.chat_areas.keys()):
                if addr != "group" and self.tcp:
                    ip, port = addr.split(":")
                    self.tcp.send_file(ip, int(port), file_path)
        else:
            ip, port = channel_id.split(":")
            if self.tcp:
                self.tcp.send_file(ip, int(port), file_path)

    # ==================================================================
    # Emoji / 文档中心
    # ==================================================================

    def _show_emoji_picker(self) -> None:
        picker = EmojiPicker(self.window)
        picker.emoji_selected.connect(self._insert_emoji)
        picker.exec()

    def _insert_emoji(self, emoji: str) -> None:
        area = self.window.chat_areas.get(self.window.current_channel)
        if area:
            area.insert_emoji(emoji)

    def _show_doc_center(self) -> None:
        recv_dir = os.path.join(os.path.dirname(__file__), "received")
        dlg = DocumentCenterDialog(
            received_dir=recv_dir,
            get_users=lambda: self.online_users,
            parent=self.window)
        dlg.share_file_requested.connect(self._on_doc_share)
        dlg.exec()

    def _on_doc_share(self, file_path: str, channel_id: str) -> None:
        if channel_id == "group":
            self._send_file("group", file_path)
        else:
            self._send_file(channel_id, file_path)

    def on_doc_open(self, file_path: str) -> None:
        try:
            path = os.path.abspath(file_path)
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception:
            pass

    # ==================================================================
    # 文件传输进度管理
    # ==================================================================

    def _add_progress_bar(self, file_id: str, name: str, size: int) -> None:
        from chat_ui import _ProgressBar
        bar = _ProgressBar(name, size)
        bar.cancelled.connect(lambda: self._cancel_transfer(file_id))
        self.progress_bars[file_id] = bar
        self.window.sidebar.add_progress_bar(bar)
        pending = self.pending_progress.pop(file_id, None)
        if pending:
            bar.update_progress(pending)
            if pending.done:
                bar.set_done()

    def _cancel_transfer(self, file_id: str) -> None:
        if self.window.current_channel != "group":
            ip, port = self.window.current_channel.split(":")
            self.tcp.cancel_transfer(self.window.current_channel, file_id)
        bar = self.progress_bars.get(file_id)
        if bar:
            bar.set_error("已取消")
            QTimer.singleShot(3000, lambda: self._remove_progress_bar(file_id))

    def _remove_progress_bar(self, file_id: str) -> None:
        bar = self.progress_bars.pop(file_id, None)
        if bar:
            self.window.sidebar.remove_progress_bar(bar)
            bar.deleteLater()

    # ==================================================================
    # 退出
    # ==================================================================

    def logout(self) -> None:
        dlg = QMessageBox(self.window)
        dlg.setWindowTitle("确认退出")
        dlg.setText("确定要退出聊天室吗？")
        dlg.setIcon(QMessageBox.Question)
        yes = dlg.addButton("确定", QMessageBox.YesRole)
        dlg.addButton("取消", QMessageBox.NoRole)
        dlg.exec()
        if dlg.clickedButton() == yes:
            if self.udp:
                self.udp.stop()
            if self.tcp:
                self.tcp.stop()
            import sys
            self.window.close()
            sys.exit(0)


# =============================================================================
# 文件传输请求对话框
# =============================================================================

class _FileRequestDialog(QDialog):
    def __init__(self, sender, file_name, file_size, parent=None):
        super().__init__(parent)
        self.setWindowTitle("文件传输请求")
        self.setFixedSize(340, 180)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {BG_APP}; }}
            QLabel {{ font-size: 13px; color: {TEXT_PRIMARY}; background: transparent; }}
            QPushButton {{ padding: 8px 18px; border: none; border-radius: {RADIUS_XS}px;
                          font-size: 13px; font-weight: 500; color: #fff; }}
        """)
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.addWidget(QLabel(f"<b>{sender}</b> 向你发送文件:"))
        layout.addWidget(QLabel(f"📁 {file_name}"))
        layout.addWidget(QLabel(f"大小: {format_size(file_size)}"))

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        accept = QPushButton("接收")
        accept.setStyleSheet(f"""
            QPushButton {{ background-color: {PRIMARY}; }}
            QPushButton:hover {{ background-color: {PRIMARY_DARK}; }}
        """)
        reject = QPushButton("拒绝")
        reject.setStyleSheet(f"""
            QPushButton {{ background-color: {TEXT_HINT}; }}
            QPushButton:hover {{ background-color: {TEXT_SECONDARY}; }}
        """)
        accept.clicked.connect(self.accept)
        reject.clicked.connect(self.reject)
        btn_row.addWidget(accept)
        btn_row.addWidget(reject)
        layout.addLayout(btn_row)
        self.setLayout(layout)
