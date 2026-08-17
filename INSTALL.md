# 音乐机器人安装教程

本文档从零开始，一步步教你完成 Telegram 音乐机器人的部署，最终托管在 Railway 上，7×24 小时在线运行。

## 目录

1. [准备工作](#1-准备工作)
2. [创建 Telegram 机器人](#2-创建-telegram-机器人)
3. [推送代码到 GitHub](#3-推送代码到-github)
4. [Railway 部署](#4-railway-部署)
5. [验证机器人运行](#5-验证机器人运行)
6. [常见问题排查](#6-常见问题排查)

---

## 1. 准备工作

需要提前注册好的三个账号：

| 平台 | 用途 | 注册地址 |
|------|------|---------|
| Telegram | 创建机器人、日常使用 | 手机应用商店下载 |
| GitHub | 存放代码 | https://github.com |
| Railway | 托管机器人 | https://railway.app |

---

## 2. 创建 Telegram 机器人

1. 在 Telegram 中搜索 **@BotFather**（官方机器人，带蓝色认证标识）

2. 向 BotFather 发送 `/newbot`

3. 按提示依次填写：
   - **机器人昵称**：例如 `我的音乐机器人`
   - **机器人用户名**：必须以 `bot` 结尾，例如 `my_music_bot_2026`

4. 创建成功后，BotFather 会返回一段文字，其中包含 **Token**：

   ```
   Use this token to access the HTTP API:
   123456789:AAF-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

   ⚠️ **Token 是你的机器人唯一凭证，相当于密码，不要泄露给他人。**

5. 记下 Token，后面要用。此时去 Telegram 搜索你刚创建的机器人用户名，点「开始」，就能看到它了。

---

## 3. 推送代码到 GitHub

### 3.1 准备仓库

1. 登录 GitHub，点击右上角 **+ → New repository**

2. 仓库名随意，例如 `music-bot`，选择 **Public**（或 Private 均可）

3. 创建完成后，进入仓库空页面，记录下仓库地址（形如 `https://github.com/你的用户名/music-bot.git`）

### 3.2 推送项目代码

在本地电脑的终端中执行（需安装 Git）：

```bash
# 进入项目目录（music-bot 目录，含 Dockerfile 和 bot/ 子目录）
cd music-bot

# 初始化 git 仓库
git init

# 关联远程仓库（替换为你的仓库地址）
git remote add origin https://github.com/你的用户名/music-bot.git

# 添加所有文件并提交
git add .
git commit -m "init: 音乐机器人"

# 推送到 GitHub
git push -u origin main
```

> 如果提示需要登录，按提示在弹出的浏览器窗口中完成 GitHub 授权即可。

---

## 4. Railway 部署

### 4.1 新建项目

1. 登录 [Railway](https://railway.app)，使用 GitHub 账号登录

2. 点击 **New Project**

3. 选择 **Deploy from GitHub repo**

4. 按提示授权 Railway 访问你的 GitHub，然后选择刚创建的 `music-bot` 仓库

5. Railway 会自动检测到项目根目录的 `Dockerfile` 并开始构建

### 4.2 配置环境变量

构建完成后（可能需要 2-5 分钟），进入服务页面：

1. 点击顶部服务名进入服务详情

2. 切到 **Variables**（变量）标签页

3. 点击 **New Variable**，添加以下变量：

   | 变量名 | 值 |
   |--------|-----|
   | `BOT_TOKEN` | 第 2 步从 BotFather 获取的 Token |

   添加完成后，服务会自动重新部署一次。

### 4.3 挂载持久化存储（推荐）

机器人会把「用户收藏歌单」存在 SQLite 数据库中。Railway 的容器磁盘是临时的，重启会清空，所以需要挂载持久卷：

1. 切到 **Settings**（设置）标签页

2. 找到 **Volumes** 区域，点击 **Add Volume**

3. **Mount Path** 填写：`/app/data`

4. 点击创建

5. 回到 **Variables**，添加第二个变量：

   | 变量名 | 值 |
   |--------|-----|
   | `DB_PATH` | `/app/data/musicbot.db` |

   保存后等待自动重新部署。

### 4.4 确认启动

1. 切到 **Deployments**（部署）标签页

2. 找到最新一次部署，点击进入

3. 点击 **View Logs**（查看日志）

4. 看到如下日志即表示启动成功：

   ```
   [INFO] 音乐机器人启动成功，等待消息…
   ```

---

## 5. 验证机器人运行

1. 回到 Telegram，打开你创建的机器人对话

2. 发送 `/help`，机器人应回复使用说明

3. 发送 `/dian 晴天`，稍等几秒，机器人应发送歌曲音频（或搜索列表）

4. 发送 `/search 周杰伦`，查看跨平台搜索结果

5. 点歌后点击「❤️ 收藏」，再发送 `/fav` 确认歌单功能正常

---

## 6. 常见问题排查

### Q1：部署后日志报 `401 Unauthorized`

`BOT_TOKEN` 填写错误或已失效。重新在 BotFather 执行 `/token` 获取新的 Token，更新环境变量。

### Q2：日志没有「启动成功」字样

说明构建未完成或启动报错。打开 **View Logs** 查看具体错误信息，通常在日志末尾能看到 Python 报错堆栈。

### Q3：点歌时提示「付费/VIP 歌曲无法获取」

QQ 音乐的付费曲目在无登录态下无法获取播放链接，属正常现象。该歌曲在网易云或汽水音乐有版权时，可换平台搜索。

### Q4：重启后收藏的歌单没了

没有挂载 Volume 或 `DB_PATH` 未指向 `/app/data`。按 [4.3 节](#43-挂载持久化存储推荐) 重新配置。

### Q5：机器人响应很慢

免费音乐解析 API 有频率限制。点歌不要太频繁，间隔几秒即可。

### Q6：修改代码后如何更新？

把改动 `git push` 到 GitHub，Railway 检测到仓库更新会自动重新构建部署。

---

## 附：完整配置清单

| 项目 | 值 |
|------|-----|
| Bot Token | 从 @BotFather 获取 |
| 构建方式 | Dockerfile（自动检测） |
| 启动命令 | `python -m bot.main`（railway.json 已配置） |
| 环境变量 | `BOT_TOKEN`（必填）、`DB_PATH=/app/data/musicbot.db`（推荐） |
| 持久卷挂载点 | `/app/data` |
