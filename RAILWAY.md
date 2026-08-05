# Railway 部署（写在仓库里的说明）

## 1. 代码

用本仓库部署。启动命令已写在 `Procfile` / `railway.toml`：

```text
python bot_main.py
```

## 2. 环境变量

在 Railway → Variables 按 `.env.example` 填写。最少：

```text
API_ID=
API_HASH=
BOT_TOKEN=
ADMIN_IDS=
MERCHANT_ID=
PAYMENT_TOKEN=
```

`config.py` 会从环境变量读取上述项，无需再改代码。

## 3. 数据目录（挂载）

1. Railway → 服务 → Volumes → 添加卷  
2. 挂载路径填：`/data`  
3. 可选再设：`ANTI_LOGIN_DATA_ROOT=/data`  

若检测到 Railway 且 `/data` 可写，`config.py` 会自动用 `/data`，即使忘了设 `ANTI_LOGIN_DATA_ROOT`。

持久化内容：`sessions/`、`user_data.json`、`storage/`、`logs/`。

## 4. 部署

Deploy 后看日志，Telegram 对 Bot 发送 `/start`。
