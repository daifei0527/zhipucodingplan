"""并发抢购调度器"""
import asyncio
from typing import Dict, Optional
from datetime import datetime

from account.model import Account


class PurchaseScheduler:
    """并发抢购调度器"""

    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self._buyers: Dict[str, tuple] = {}  # account_id -> (account, buyer)
        self._running = False
        self._results: Dict[str, bool] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    def add_buyer(self, account: Account, buyer):
        """添加抢购器"""
        self._buyers[account.id] = (account, buyer)

    def remove_buyer(self, account_id: str):
        """移除抢购器"""
        if account_id in self._buyers:
            del self._buyers[account_id]

    def clear_buyers(self):
        """清空所有抢购器"""
        self._buyers.clear()
        self._results.clear()

    async def run_single(self, account_id: str) -> bool:
        """运行单个账号的抢购"""
        if account_id not in self._buyers:
            return False

        account, buyer = self._buyers[account_id]
        account.status = "buying"

        try:
            result = await buyer.run()
            account.status = "success" if result else "failed"
            self._results[account_id] = result
            return result
        except Exception as e:
            account.status = "error"
            self._results[account_id] = False
            return False

    async def run_all(self) -> Dict[str, bool]:
        """并发运行所有账号的抢购"""
        self._running = True
        self._results.clear()

        # 创建信号量控制并发数
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def run_with_semaphore(account_id: str):
            async with semaphore:
                if not self._running:
                    return False
                return await self.run_single(account_id)

        # 创建所有任务
        tasks = [
            run_with_semaphore(account_id)
            for account_id in self._buyers
        ]

        # 并发执行
        await asyncio.gather(*tasks, return_exceptions=True)

        self._running = False
        return self._results

    def stop(self):
        """停止所有抢购"""
        self._running = False
        # 取消所有运行中的任务
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        self._tasks.clear()

    def get_status(self, account_id: str) -> Optional[str]:
        """获取单个账号状态"""
        if account_id in self._buyers:
            return self._buyers[account_id][0].status
        return None

    def get_all_status(self) -> Dict[str, str]:
        """获取所有账号状态"""
        return {
            acc_id: data[0].status
            for acc_id, data in self._buyers.items()
        }

    def get_results(self) -> Dict[str, bool]:
        """获取抢购结果"""
        return self._results.copy()
