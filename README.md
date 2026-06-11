# 🐹 CapyChat

基于 PySide6 的局域网 P2P 加密聊天工具，TCP + UDP 混合通信，无需中心服务器。

## 功能特性

- **P2P 局域网通信** — UDP 广播发现在线用户，TCP 点对点加密传输
- **加密通信** — 基于密钥派生函数（KDF）的端到端加密
- **多频道支持** — 支持频道切换、群聊与私聊
- **文件传输** — 图片、视频、音频、文档的发送与接收
- **头像系统** — 内置 30+ 动物头像，支持同步显示
- **表情选择器** — 丰富的表情面板
- **文档中心** — 汇总查看已接收的文件
- **AI 助手** — 集成 AI 聊天代理（CapybaraAgent）
- **现代 UI** — 深色主题，圆角气泡消息，侧边栏导航

## 技术栈

| 组件 | 技术 |
|------|------|
| GUI | PySide6 (Qt for Python) |
| 网络 | TCP P2P + UDP 广播 |
| 加密 | cryptography (Fernet) |
| AI | requests (HTTP API 调用) |
| 构建 | uv (Python 包管理器) |

## 安装与运行

### 环境要求

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) (推荐) 或 pip

### 安装

```bash
# 克隆仓库
git clone https://github.com/ShaneChing7/CapyChat.git
cd CapyChat

# 使用 uv 安装依赖
uv sync

# 或使用 pip
pip install -e .
```

### 启动

```bash
# 方式一：直接运行
uv run python -m capychat.main

# 方式二：使用安装的命令
capychat
```

### 配置

编辑 `capychat/conf.json` 可自定义：
- 默认用户名与头像
- TCP / UDP 端口
- 加密密钥
- AI 助手设置

## 项目结构

```
CapyChat/
├── capychat/
│   ├── main.py              # 应用入口
│   ├── controller.py        # 聊天业务逻辑层
│   ├── config_manager.py    # 配置读写管理
│   ├── conf.json            # 本地配置文件
│   ├── views/
│   │   ├── login_ui.py      # 登录 / 设置界面
│   │   └── chat_ui.py       # 聊天主界面
│   ├── network/
│   │   ├── tcp_p2p.py       # TCP 点对点通信
│   │   ├── udp_broadcast.py # UDP 广播发现
│   │   ├── protocol.py      # 通信协议定义
│   │   ├── crypto.py        # 加密工具
│   │   └── file_transfer.py # 文件传输管理
│   ├── ui/
│   │   ├── chat_area.py     # 聊天区域组件
│   │   ├── message_bubble.py# 消息气泡组件
│   │   ├── message_list.py  # 消息列表组件
│   │   ├── sidebar.py       # 侧边栏组件
│   │   ├── avatar_cache.py  # 头像缓存
│   │   ├── avatar_picker.py # 头像选择器
│   │   ├── capybara_widget.py   # 水豚动画组件
│   │   ├── capybara_settings.py # AI 设置面板
│   │   ├── emoji_picker.py  # 表情选择器
│   │   ├── document_center.py   # 文档中心
│   │   └── theme.py         # 主题样式定义
│   ├── ai/
│   │   └── capybara_agent.py# AI 聊天代理
│   └── assets/              # 图标、头像、图片资源
├── pyproject.toml
└── uv.lock
```

## License

MIT
