"""账号管理模块"""
from .model import Account, TargetPlan, GlobalConfig, AccountsConfig
from .manager import AccountManager
from .storage import AccountStorage

__all__ = ['Account', 'TargetPlan', 'GlobalConfig', 'AccountsConfig',
           'AccountManager', 'AccountStorage']


def get_account_manager(path: str = "accounts.json") -> AccountManager:
    """获取账号管理器单例"""
    global _manager
    if '_manager' not in globals():
        _manager = AccountManager(path)
    return _manager
