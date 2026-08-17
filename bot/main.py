async def _main() -> None:
    if not config.BOT_TOKEN:
        logger.error("未配置 BOT_TOKEN，请填写环境变量")
        sys.exit(1)

    database.init_db()
    # ✅ bot只在这里新建一次
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()

    dp.message.middleware(WhitelistMiddleware())
    dp.callback_query.middleware(WhitelistMiddleware())

    dp.include_router(_build_router())
    await _setup_commands(bot)

    logger.info("音乐机器人启动成功，等待消息…")
    try:
        # ✅ 唯一一次启动轮询，bot=bot命名参数
        await dp.start_polling(bot=bot)
    finally:
        # ✅ 退出时正确关闭bot会话，释放资源，防止重复复用报错
        await bot.session.close()
