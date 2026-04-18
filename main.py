#!/usr/bin/env python3
"""智谱 CodingPlan 自动抢购 - 主入口"""
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
import threading


def run_web_thread(config: Config):
    """在单独线程中运行Web服务器"""
    from web.app import run_web
    run_web(config)


def calculate_wait_seconds(target_time: str) -> int:
    """计算距离目标时间还有多少秒"""
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
    """异步主函数"""
    recorder = get_recorder()
    login_manager = get_login_manager(config)
    buyer = get_buyer(config)

    recorder.info("=== 智谱 CodingPlan 自动抢购启动 ===")
    recorder.info(f"目标: {config.target.plan} - {config.target.duration}")
    recorder.info(f"抢购时间: {config.schedule.time}")

    # 启动Web服务器（在单独线程）
    web_thread = threading.Thread(
        target=run_web_thread,
        args=(config,),
        daemon=True
    )
    web_thread.start()
    recorder.info(f"Web监控界面: http://{config.web.host}:{config.web.port}")

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
    remaining = calculate_wait_seconds(config.schedule.time)
    if remaining > 0:
        recorder.info(f"等待 {remaining} 秒后开始抢购...")
        await asyncio.sleep(remaining)

    # 执行抢购 - 使用sniffer获取详细日志
    recorder.info("启动抢购监控...")
    from buyer.sniffer import PurchaseSniffer
    sniffer = PurchaseSniffer(config)
    success = await sniffer.run()

    if success:
        recorder.info("抢购成功!")
    else:
        recorder.info("抢购未成功，等待下次运行")

    return success


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

    # 运行主循环
    asyncio.run(main_async(config))


if __name__ == "__main__":
    main()
