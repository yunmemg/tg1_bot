# Anti-Login

基于 Telethon 的 Telegram Bot，提供订阅支付、账号托管、反登录监控、托管工具和账号转让。

Developed and open-sourced by 秦屿泊 (@qinyubo). Free for everyone to use and modify under the MIT License.

## 快速开始

要求 Python 3。

```powershell
pip install -r requirements.txt
Copy-Item config.example.py config.py
```

编辑 `config.py`，填写 Telegram、管理员和 OkayPay 配置，然后启动：

```powershell
python bot_main.py
```

## 项目结构

```text
bot_main.py       程序入口
project_info.py   作者、许可证与项目元数据
config.example.py 配置模板
accounts/         账号登录、托管、监控与转让
handlers/         Bot 命令和回调处理
payments/         OkayPay 建单、查单与支付处理
reminders/        VIP 到期提醒
storage/          数据读写和缓存
tests/            自动化测试
```

## 运行数据

以下内容可能包含密钥或用户数据，不应提交或打包：

- `config.py`
- `bot.session`
- `user_data.json`
- `sessions/`
- `logs/`
- `storage/*.json`
- `storage/*.jsonl`
- `__pycache__/`、`.pytest_cache/`

配置项及默认值以 `config.example.py` 为准。首次部署时复制该文件为 `config.py`，不要把真实配置覆盖回模板。
所有相对运行路径都以 `DATA_ROOT` 为基准；也可用环境变量
`ANTI_LOGIN_DATA_ROOT` 为测试或独立实例指定数据目录。

旧格式数据升级前先停止程序并检查迁移摘要：

```powershell
python migrate_runtime_data.py --check
python migrate_runtime_data.py --apply
```

`--apply` 只改写真正发生变化的文件，并在同目录创建
`*.migration.backup`。迁移可重复运行；完成后再次执行 `--check` 应显示
`changed_files` 为空。

## 测试

```powershell
python -m pytest -q
```

## 用户界面本地化

所有用户可见界面支持简体中文（`zh`）和英文（`en`），包括普通用户流程、
管理员面板、托管操作结果、Session/ZIP 导入、账号转让、VIP、
订阅支付和主动通知。用户第一次发送 `/start` 时会按 Telegram 客户端语言
保存默认值，之后可通过主菜单的“语言 / Language”按钮或 `/language` 修改。

修改用户界面时必须遵守以下规则：

- 所有普通用户可见的消息、按钮、回调提示、文件说明和后台通知，都必须同时提供 `zh` 与 `en` 文案。
- 文案统一放在 `localization.py`，两种语言必须使用相同的键和格式参数，不得在输出位置新增硬编码文案。
- 中文文案保持明确、完整；英文按功能含义编写，使用简短、直接的表达，不照搬中文修饰语。
- 异步提醒和跨用户通知必须读取接收者保存的语言，不能沿用发起者的语言。
- 管理员面板、管理员专属命令、权限提示、审计展示、支付异常提醒和系统启动通知均读取接收管理员保存的语言。
- 回调数据、内部日志、审计动作/错误码、磁盘 JSONL 和下载的原始审计文件保持机器格式，不进行翻译。
- 提交界面改动前运行完整测试，确认语言目录键、占位符和语言持久化行为均通过。

本地化专项检查：

```powershell
python -m pytest tests/test_localization.py tests/test_english_coverage.py -q
```

专项测试会检查词条与占位符一致性、英文词库中文泄漏，以及托管、导入、
转让、VIP 和支付结果等关键英文路径。发布前仍需运行完整测试：

```powershell
python -m pytest -q
```

## GitHub 发布

公开仓库使用 `main` 分支和语义化 tag。`v1.0.0` Release 应附加：

- `Anti-Login-v1.0.0.zip`：不含测试、CI、开发依赖和任何运行数据的部署包；
- `RELEASE_NOTES-v1.0.0.md`：发布说明；
- `SHA256SUMS.txt`：部署包的 SHA-256 校验值。

GitHub 会为 tag 自动生成完整仓库的 Source code ZIP/TAR，其中包含公开测试。
实际部署请下载 Release 页面单独附加的 `Anti-Login-v1.0.0.zip`。

发布前必须运行完整测试、审查 Git 状态、扫描敏感信息，并确认压缩包不含
`config.py`、Session、用户数据、日志、缓存、测试或嵌套压缩包。不要绕过
GitHub secret scanning 或 push protection 告警。

## 开源许可与贡献

Copyright (c) 2026 秦屿泊 (`@qinyubo`)。

本项目采用 [MIT License](LICENSE)，允许任何人免费使用、学习、修改、商用和
再发布，但必须保留版权与许可声明。贡献代码前请阅读
[CONTRIBUTING.md](CONTRIBUTING.md)，安全问题请遵循 [SECURITY.md](SECURITY.md)。

## 部署提示

- 安装依赖后，将 `config.example.py` 复制为 `config.py` 并填写真实配置。
- 持久化保存 `sessions/`、`user_data.json` 和 `storage/*.json`。
- 发布前先停止旧进程并确认没有其他程序占用 `sessions/*.session`；程序会通过
  `sessions/.anti_login.instance.lock` 拒绝同目录双实例启动。
- 使用带退避重启策略的进程守护器运行 `python bot_main.py`。
- 可设置 `BOT_BUILD_REVISION` 环境变量；启动日志会同时记录构建版本和 Telethon
  版本。Git 工作区启动时会自动读取当前提交。
- 运行日志是 UTF-8；PowerShell 读取无 BOM 日志时请使用
  `Get-Content -Encoding utf8 logs/bot_runtime.log`。
- 不要关闭 HTTPS 证书校验，不要公开 Token、支付密钥或 session 文件。
