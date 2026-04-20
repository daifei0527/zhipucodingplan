"""多账号登录检查模块"""
import asyncio
from typing import List, Dict
from datetime import datetime

from account.model import Account
from auth.cookies import get_cookie_manager
from auth.login import LoginManager
from config import Config
from learner.recorder import get_recorder


async def check_account_login_status(account: Account) -> Dict:
    """检查单个账号的登录状态

    Args:
        account: 账号对象

    Returns:
        {"valid": bool, "message": str}
    """
    cookie_manager = get_cookie_manager(account.id)

    # 检查Cookie文件是否存在
    if not cookie_manager.cookie_file.exists():
        return {"valid": False, "message": "无Cookie"}

    # 检查Cookie是否有效（未过期）
    if not cookie_manager.is_valid():
        return {"valid": False, "message": "Cookie已过期"}

    # 加载Cookie
    cookies = cookie_manager.load()
    if not cookies:
        return {"valid": False, "message": "无法加载Cookie"}

    return {"valid": True, "message": "Cookie有效"}


async def login_single_account(config: Config, account: Account, headless: bool = True) -> Dict:
    """登录单个账号

    Args:
        config: 全局配置
        account: 账号对象
        headless: 是否无头模式

    Returns:
        {"success": bool, "message": str}
    """
    recorder = get_recorder()
    recorder.info(f"开始登录账号: {account.username}")

    try:
        # 创建登录管理器，使用账号对应的Cookie存储
        login_manager = LoginManager(config, account)
        success = await login_manager.login(headless=headless)

        if success:
            return {"success": True, "message": "登录成功"}
        else:
            return {"success": False, "message": "登录失败"}
    except Exception as e:
        recorder.error(f"登录异常: {e}")
        return {"success": False, "message": f"登录异常: {e}"}


async def check_and_login_accounts(config: Config, accounts: List[Account], headless: bool = True) -> Dict:
    """检查所有账号登录状态，未登录自动登录

    Args:
        config: 全局配置
        accounts: 账号列表
        headless: 是否无头模式

    Returns:
        {account_id: {"success": bool, "message": str, "username": str}}
    """
    recorder = get_recorder()
    results = {}

    recorder.info(f"=== 开始检查 {len(accounts)} 个账号登录状态 ===")

    for account in accounts:
        recorder.info(f"检查账号 [{account.username}] ...")

        # 检查登录状态
        status = await check_account_login_status(account)

        if status["valid"]:
            recorder.info(f"账号 [{account.username}] {status['message']}")
            results[account.id] = {
                "success": True,
                "message": status["message"],
                "username": account.username
            }
            continue

        # 需要登录
        recorder.info(f"账号 [{account.username}] {status['message']}，开始登录...")
        login_result = await login_single_account(config, account, headless)

        results[account.id] = {
            "success": login_result["success"],
            "message": login_result["message"],
            "username": account.username
        }

        if login_result["success"]:
            recorder.info(f"账号 [{account.username}] 登录成功")
        else:
            recorder.error(f"账号 [{account.username}] 登录失败: {login_result['message']}")

    # 统计结果
    success_count = sum(1 for r in results.values() if r["success"])
    recorder.info(f"=== 登录检查完成: {success_count}/{len(accounts)} 成功 ===")

    return results


async def verify_account_cookies(config: Config, accounts: List[Account]) -> Dict:
    """验证所有账号的Cookie是否可用（通过发送测试请求）

    Args:
        config: 全局配置
        accounts: 账号列表

    Returns:
        {account_id: {"valid": bool, "message": str}}
    """
    import aiohttp
    recorder = get_recorder()
    results = {}

    for account in accounts:
        cookie_manager = get_cookie_manager(account.id)
        cookies = cookie_manager.load()

        if not cookies:
            results[account.id] = {"valid": False, "message": "无Cookie"}
            continue

        cookie_dict = cookie_manager.to_aiohttp_format()

        try:
            async with aiohttp.ClientSession(cookies=cookie_dict) as session:
                async with session.get(
                    config.zhipu.coding_url,
                    allow_redirects=False
                ) as resp:
                    if resp.status in (301, 302, 303, 307, 308):
                        location = resp.headers.get("Location", "")
                        if "login" in location.lower():
                            results[account.id] = {"valid": False, "message": "Cookie已失效"}
                            continue

                    if resp.status == 200:
                        results[account.id] = {"valid": True, "message": "Cookie有效"}
                    else:
                        results[account.id] = {"valid": False, "message": f"状态码: {resp.status}"}
        except Exception as e:
            results[account.id] = {"valid": False, "message": f"验证失败: {e}"}

    return results
