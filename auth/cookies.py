"""Cookie管理模块 - 支持多账号独立Cookie"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta


class CookieManager:
    """Cookie存储和管理 - 支持按账号ID独立存储"""

    def __init__(self, account_id: str = None):
        """
        初始化Cookie管理器

        Args:
            account_id: 账号ID，如果提供则使用独立存储路径 cookies/{account_id}.json
        """
        if account_id:
            self.cookie_file = Path(f"cookies/{account_id}.json")
            self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.cookie_file = Path("cookies.json")
        self._cookies: Optional[dict] = None
        self.account_id = account_id

    def load(self) -> Optional[dict]:
        """从文件加载Cookie"""
        if not self.cookie_file.exists():
            return None

        try:
            with open(self.cookie_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._cookies = data.get("cookies", data)
            return self._cookies
        except (json.JSONDecodeError, KeyError):
            return None

    def save(self, cookies: dict):
        """保存Cookie到文件"""
        data = {
            "cookies": cookies,
            "saved_at": datetime.now().isoformat(),
            "account_id": self.account_id
        }

        with open(self.cookie_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # 设置文件权限
        os.chmod(self.cookie_file, 0o600)
        self._cookies = cookies

    def clear(self):
        """清除保存的Cookie"""
        if self.cookie_file.exists():
            self.cookie_file.unlink()
        self._cookies = None

    def to_aiohttp_format(self) -> dict:
        """转换为aiohttp可用的Cookie格式"""
        if not self._cookies:
            return {}

        # 如果是playwright格式的cookie列表
        if isinstance(self._cookies, list):
            return {c["name"]: c["value"] for c in self._cookies}

        return self._cookies

    def to_playwright_format(self) -> list[dict]:
        """转换为Playwright可用的Cookie格式"""
        if not self._cookies:
            return []

        # 如果已经是列表格式
        if isinstance(self._cookies, list):
            return self._cookies

        # 从dict格式转换
        return [
            {"name": k, "value": v, "domain": ".bigmodel.cn", "path": "/"}
            for k, v in self._cookies.items()
        ]

    def is_valid(self) -> bool:
        """检查Cookie是否有效（存在且不太可能过期）"""
        if not self.cookie_file.exists():
            return False

        try:
            with open(self.cookie_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            saved_at_str = data.get("saved_at")
            if not saved_at_str:
                return True  # 没有时间戳，假设有效

            saved_at = datetime.fromisoformat(saved_at_str)
            # 假设Cookie有效期7天
            if datetime.now() - saved_at > timedelta(days=7):
                return False

            return True
        except:
            return False


def get_cookie_manager(account_id: str = None) -> CookieManager:
    """获取Cookie管理器实例

    Args:
        account_id: 账号ID，如果提供则返回该账号独立的Cookie管理器
                   如果为 None 则使用全局共享的 cookies.json

    Returns:
        CookieManager 实例
    """
    return CookieManager(account_id)
