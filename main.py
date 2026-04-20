#!/usr/bin/env python3
"""智谱 CodingPlan 自动抢购 - 多账号主入口"""
import asyncio
import signal
import sys
from datetime import datetime, time as dt_time
from typing import Optional

from config import get_config, Config
from auth.login import get_login_manager
from auth.cookies import get_cookie_manager
from buyer.purchase import get_buyer
from learner.recorder import get_recorder
from account.manager import get_account_manager
from scheduler.scheduler import PurchaseScheduler
import threading


def run_web_thread(config: Config):
    """在单独线程中运行Web服务器"""
    from web.app import run_web
    run_web(config)


def calculate_wait_seconds(target_time: str, immediate: bool = False) -> int:
    """计算距离目标时间还有多少秒

    Args:
        target_time: 目标时间 HH:MM
        immediate: 是否立即开始（用于已过抢购时间的情况）
    """
    if immediate:
        return 0  # 立即开始

    hour, minute = map(int, target_time.split(":"))
    target = dt_time(hour, minute)
    now = datetime.now().time()

    now_minutes = now.hour * 60 + now.minute
    target_minutes = target.hour * 60 + target.minute

    diff = target_minutes - now_minutes
    if diff < 0:
        diff += 24 * 60  # 加一天

    # 减去30秒作为预热时间
    return max(0, diff * 60 - 30)


async def main_async(config: Config):
    """异步主函数 - 多账号模式"""
    recorder = get_recorder()
    account_manager = get_account_manager()
    scheduler = PurchaseScheduler(max_concurrent=5)

    # 检查是否有配置的账号
    accounts = account_manager.get_enabled_accounts()

    if not accounts:
        # 没有多账号配置，使用单账号模式
        recorder.info("=== 单账号模式启动 ===")
        await single_account_mode(config, recorder)
    else:
        # 多账号模式
        recorder.info(f"=== 多账号模式启动 ({len(accounts)} 个账号) ===")
        await multi_account_mode(config, accounts, scheduler, recorder)


async def single_account_mode(config: Config, recorder):
    """单账号模式"""
    login_manager = get_login_manager(config)
    buyer = get_buyer(config)

    recorder.info(f"账号: {config.account.username}")
    recorder.info(f"目标: {config.target.plan} - {config.target.duration}")
    recorder.info(f"抢购时间: {config.schedule.time}")

    # 检查是否已经过了抢购时间（30分钟窗口内）
    hour, minute = map(int, config.schedule.time.split(":"))
    now = datetime.now()
    target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    time_diff = (now - target_time).total_seconds()

    # 如果在抢购时间后30分钟内，立即开始
    immediate_mode = 0 < time_diff < 1800

    if immediate_mode:
        recorder.info("检测到已过抢购时间但在30分钟窗口内，立即开始抢购!")
        wait_seconds = 0
    else:
        # 计算等待时间
        wait_seconds = calculate_wait_seconds(config.schedule.time)
        recorder.info(f"距离抢购时间还有 {wait_seconds // 60} 分钟")

    # 等待到抢购时间
    if wait_seconds > 60:
        recorder.info("进入等待模式...")
        await asyncio.sleep(wait_seconds - 60)

    # 抢购前检查登录状态
    recorder.info("检查登录状态...")
    if not await login_manager.check_login_status():
        recorder.info("需要重新登录...")
        success = await login_manager.login(headless=True)
        if not success:
            recorder.error("登录失败，无法继续抢购")
            return False

    # 等待剩余时间
    remaining = calculate_wait_seconds(config.schedule.time, immediate_mode)
    if remaining > 0:
        recorder.info(f"等待 {remaining} 秒后开始抢购...")
        await asyncio.sleep(remaining)

    # 执行抢购
    recorder.info("启动抢购...")
    success = await buyer.run()

    if success:
        recorder.info("抢购成功!")
    else:
        recorder.info("抢购未成功，等待下次运行")

    return success


async def multi_account_mode(config: Config, accounts, scheduler: PurchaseScheduler, recorder):
    """多账号并发模式"""
    recorder.info(f"抢购时间: {config.schedule.time}")

    for acc in accounts:
        recorder.info(f"  - {acc.username}: 目标 {[p.plan for p in acc.target_plans]}")

    # 计算等待时间
    hour, minute = map(int, config.schedule.time.split(":"))
    now = datetime.now()
    target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    time_diff = (now - target_time).total_seconds()

    immediate_mode = 0 < time_diff < 1800

    if immediate_mode:
        wait_seconds = 0
        recorder.info("立即开始抢购!")
    else:
        wait_seconds = calculate_wait_seconds(config.schedule.time)
        recorder.info(f"距离抢购时间还有 {wait_seconds // 60} 分钟")

    if wait_seconds > 60:
        recorder.info("进入等待模式...")
        await asyncio.sleep(wait_seconds - 60)

    # 检查登录状态（使用第一个账号）
    recorder.info("检查登录状态...")
    login_manager = get_login_manager(config)
    if not await login_manager.check_login_status():
        recorder.info("需要重新登录...")
        success = await login_manager.login(headless=True)
        if not success:
            recorder.error("登录失败，无法继续抢购")
            return False

    remaining = calculate_wait_seconds(config.schedule.time, immediate_mode)
    if remaining > 0:
        recorder.info(f"等待 {remaining} 秒后开始抢购...")
        await asyncio.sleep(remaining)

    # 添加所有买家到调度器
    for acc in accounts:
        buyer = get_buyer(config, acc)
        scheduler.add_buyer(acc, buyer)

    # 并发抢购
    recorder.info("启动多账号并发抢购...")
    results = await scheduler.run_all()

    # 统计结果
    success_count = sum(1 for v in results.values() if v)
    recorder.info(f"抢购完成: {success_count}/{len(results)} 成功")

    return success_count > 0


def main():
    """主入口"""
    try:
        config = get_config()
    except FileNotFoundError:
        print("错误: 配置文件 config.json 不存在")
        print("请复制 config.json 模板并填写账号密码")
        sys.exit(1)

    if not config.validate():
        print("错误: 配置文件不完整，请填写账号密码")
        sys.exit(1)

    # 启动 Web 服务器
    web_thread = threading.Thread(
        target=run_web_thread,
        args=(config,),
        daemon=True
    )
    web_thread.start()

    from learner.recorder import get_recorder
    get_recorder().info(f"Web监控界面: http://{config.web.host}:{config.web.port}")

    # 运行主循环
    asyncio.run(main_async(config))


if __name__ == "__main__":
    main()
