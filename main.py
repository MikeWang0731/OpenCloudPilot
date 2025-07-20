#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIOps CloudPilot 主启动文件
支持两种启动模式：
1. 即时app模式 - 直接使用集群内权限
2. Server模式 - 支持多集群管理
"""

import argparse
import asyncio
import sys
import urllib3

from src.core.config import Settings
from src.core.logger import setup_logger
from src.modes.instant_app import InstantAppMode
from src.modes.server_mode import ServerMode


async def main():
    """主启动函数"""
    parser = argparse.ArgumentParser(description="AIOps CloudPilot")
    parser.add_argument(
        "--mode",
        choices=["instant", "server"],
        default="server",
        help="启动模式: instant(即时app) 或 server(服务器模式)",
    )
    parser.add_argument("--port", type=int, default=8000, help="服务端口 (默认: 8000)")
    parser.add_argument("--host", default="0.0.0.0", help="服务地址 (默认: 0.0.0.0)")
    parser.add_argument("--config", help="配置文件路径")

    args = parser.parse_args()

    # 初始化配置
    settings = Settings(config_file=args.config)

    # 设置日志
    logger = setup_logger(settings.log_level)
    logger.info("启动 AIOps CloudPilot - 模式: %s", args.mode)

    try:
        if args.mode == "instant":
            # 即时app模式
            app_mode = InstantAppMode(settings)
            await app_mode.start(host=args.host, port=args.port)
        else:
            # Server模式
            server_mode = ServerMode(settings)
            await server_mode.start(host=args.host, port=args.port)

    except KeyboardInterrupt:
        logger.info("收到停止信号，正在关闭服务...")
    except Exception as e:
        logger.error("启动失败: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    urllib3.disable_warnings()
    asyncio.run(main())
