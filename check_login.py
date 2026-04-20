#!/usr/bin/env python3
"""账号登录预检查 - 9:55 运行，检查所有账号登录状态"""
import asyncio
import sys
from datetime import datetime

from config import get_config
from account import get_account_manager
from auth.multi_login import check_and_login_accounts
from learner.recorder import get_recorder


def log_time_info():
    """记录时间信息"""
    now = datetime.now()
    print(f"=== 时间信息 ===")
    print(f"本地时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"时区: Asia/Shanghai")


async def main():
    """主入口"""
    log_time_info()

    recorder = get_recorder()
    recorder.info("=== 账号登录预检查开始 ===")

    try:
        config = get_config()
    except FileNotFoundError:
        recorder.error("配置文件 config.json 不存在")
        print("错误: 配置文件 config.json 不存在")
        sys.exit(1)

    account_manager = get_account_manager()
    accounts = account_manager.get_enabled_accounts()

    if not accounts:
        recorder.info("没有启用的账号，跳过预检查")
        print("没有启用的账号")
        return

    recorder.info(f"检查 {len(accounts)} 个账号...")
    print(f"检查 {len(accounts)} 个账号...")

    results = await check_and_login_accounts(config, accounts)

    # 统计结果
    success_count = sum(1 for r in results.values() if r["success"])
    recorder.info(f"预检查完成: {success_count}/{len(accounts)} 成功")
    print(f"\n预检查完成: {success_count}/{len(accounts)} 成功")

    # 打印详细结果
    for account_id, result in results.items():
        status = "✓" if result["success"] else "✗"
        print(f"  {status} [{result['username']}] {result['message']}")


if __name__ == "__main__":
    asyncio.run(main())
