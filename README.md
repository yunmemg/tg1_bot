# 🎵 Telegram 音乐机器人

一个部署在 Telegram 上的音乐机器人，支持 **网易云音乐 / QQ音乐 / 汽水音乐** 三平台点歌、搜索和歌单收藏。

## 功能

| 命令 | 说明 |
|------|------|
| `/search 关键词` | 跨平台搜索歌曲，展示结果列表，点击即可播放 |
| `/dian 关键词` | 直接点歌，自动播放最匹配的一首 |
| `/fav` | 查看个人收藏歌单，可播放或删除 |
| `/help` | 显示帮助 |

- 点歌时并行搜索三个平台，封面、歌名、歌手一并展示
- 播放成功后点击「❤️ 收藏」加入个人歌单
- 搜索结果显示前 5 首，支持翻页浏览
- 可选用户白名单（仅允许指定用户使用）

## 快速开始

### 1. 创建 Telegram Bot

在 Telegram 中向 [@BotFather](https://t.me/BotFather) 发送 `/newbot`，按提示创建机器人，获取类似 `123456789:ABC...` 的 Token。

### 2. 配置

```bash
cp .env.example .env
```

编辑 `.env`：

```env
BOT_TOKEN=你的机器人Token
# ALLOWED_USER_IDS=111111111,222222222   # 可选，白名单
```

### 3. 运行

```bash
bash start.sh
```

脚本会自动创建虚拟环境、安装依赖并启动机器人。

## 手动运行

```bash
pip install -r requirements.txt
python -m bot.main
```

## Railway 部署

项目已内置 `Dockerfile` 与 `railway.json`，Railway 会自动检测并构建。

### 1. 推送代码

将本项目推送到 GitHub 仓库。建议把 `music-bot` 目录**内容**作为仓库根目录（`Dockerfile`、`railway.json`、`bot/` 等在根目录），这样 Railway 无需额外配置；若放在子目录，则在 Railway 服务 Settings 的 **Root Directory** 中填该子目录路径。

### 2. 新建 Railway 项目

1. 登录 [Railway](https://railway.app)，点击 **New Project → Deploy from GitHub repo**，选择本仓库
2. Railway 检测到根目录的 `Dockerfile` 会自动开始构建

### 3. 配置环境变量

在服务 **Variables** 中添加：

| 变量 | 必填 | 说明 |
|------|------|------|
| `BOT_TOKEN` | 是 | 从 @BotFather 获取的机器人 Token |
| `ALLOWED_USER_IDS` | 否 | 用户白名单，逗号分隔 |
| `DB_PATH` | 否 | 数据库路径，建议 `/app/data/musicbot.db` |

### 4. 挂载持久化 Volume（重要）

Railway 的容器文件系统是**临时**的，重启/重新部署会清空。收藏歌单存在 SQLite 中，必须挂载 Volume 才能持久化：

1. 服务 **Settings → Volumes → Add Volume**
2. Mount Path 填 `/app/data`
3. 环境变量 `DB_PATH` 设为 `/app/data/musicbot.db`

### 5. 启动

Railway 通过 `startCommand` 自动执行 `python -m bot.main`，日志可在服务 **Deployments → View Logs** 查看。机器人通过长轮询连接 Telegram，无需暴露端口。

**注意：** 不要设置 `healthcheckPath`（机器人不监听 HTTP 端口）。

## 技术说明

### 音乐来源

三个平台的音频直链通过公开接口获取：

| 平台 | 搜索 | 播放直链 |
|------|------|---------|
| 网易云音乐 | 网易云官方搜索接口 | 官方外链接口 |
| QQ音乐 | 网页版搜索接口 | `musicu.fcg` vkey 接口 |
| 汽水音乐 | 素颜 API 搜索 | pearapi 解析接口 |

**注意事项：**

- QQ音乐付费/VIP 歌曲无法获取播放链接，机器人会提示并建议换平台搜索
- 各平台接口为公开逆向接口，可能因平台调整而失效；代码已在服务层隔离，便于更新替换
- 汽水音乐解析依赖第三方公开 API（`api.suyanw.cn` / `api.pearapi.ai`），免费接口有频率限制，高频使用建议控制点歌频率

### 项目结构

```
music-bot/
├── bot/
│   ├── main.py              # 入口，机器人装配
│   ├── config.py            # 配置读取
│   ├── handlers/
│   │   ├── commands.py      # /start /help
│   │   ├── search.py        # 搜索、点歌、翻页
│   │   └── favorites.py     # 收藏歌单
│   ├── services/
│   │   ├── base.py          # 歌曲数据模型
│   │   ├── netease.py       # 网易云音乐
│   │   ├── qqmusic.py       # QQ音乐
│   │   └── qishui.py        # 汽水音乐
│   ├── db/database.py       # SQLite 收藏存储
│   └── utils/               # 缓存、下载、发送
├── requirements.txt
├── .env.example
└── start.sh
```

### 依赖

- Python 3.9+
- aiogram 3.x
- aiohttp
- python-dotenv

## 免责声明

本项目仅用于个人学习与技术交流，请勿用于商业用途。获取的音频版权归原平台所有，请在合法范围内使用。
