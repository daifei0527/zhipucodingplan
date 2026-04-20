"""账号管理器"""
import uuid
from typing import List, Optional
from datetime import datetime

from .model import Account, TargetPlan, AccountsConfig
from .storage import AccountStorage


class AccountManager:
    """账号管理器 - CRUD 操作"""

    def __init__(self, storage_path: str = "accounts.json"):
        self.storage = AccountStorage(storage_path)
        self._config: Optional[AccountsConfig] = None

    @property
    def config(self) -> AccountsConfig:
        """懒加载配置"""
        if self._config is None:
            self._config = self.storage.load()
        return self._config

    def _save(self):
        """保存配置"""
        self.storage.save(self.config)

    def _generate_id(self) -> str:
        """生成账号ID"""
        return f"acc_{uuid.uuid4().hex[:8]}"

    def list_accounts(self) -> List[Account]:
        """列出所有账号"""
        return self.config.accounts

    def get_account(self, account_id: str) -> Optional[Account]:
        """获取单个账号"""
        return self.config.get_account(account_id)

    def add_account(
        self,
        username: str,
        password: str,
        enabled: bool = True,
        target_plans: List[dict] = None,
        auto_pay: bool = True
    ) -> Account:
        """添加账号"""
        account_id = self._generate_id()

        plans = []
        if target_plans:
            for p in target_plans:
                plans.append(TargetPlan(
                    plan=p["plan"],
                    duration=p["duration"],
                    priority=p.get("priority", 1)
                ))

        account = Account(
            id=account_id,
            username=username,
            password=password,
            enabled=enabled,
            target_plans=plans,
            auto_pay=auto_pay
        )

        self.config.add_account(account)
        self._save()
        return account

    def update_account(
        self,
        account_id: str,
        **kwargs
    ) -> Optional[Account]:
        """更新账号

        支持更新的字段: username, password, enabled, target_plans,
                       auto_pay, balance_threshold, balance, status
        """
        account = self.get_account(account_id)
        if not account:
            return None

        # 更新简单字段
        for field in ['username', 'password', 'enabled', 'auto_pay',
                      'balance_threshold', 'balance', 'status']:
            if field in kwargs:
                setattr(account, field, kwargs[field])

        # 更新目标套餐
        if 'target_plans' in kwargs:
            plans = []
            for p in kwargs['target_plans']:
                if isinstance(p, TargetPlan):
                    plans.append(p)
                else:
                    plans.append(TargetPlan(
                        plan=p["plan"],
                        duration=p["duration"],
                        priority=p.get("priority", 1)
                    ))
            account.target_plans = plans

        # 更新最后运行时间
        if kwargs.get('update_last_run'):
            account.last_run = datetime.now().isoformat()

        self._save()
        return account

    def delete_account(self, account_id: str) -> bool:
        """删除账号"""
        result = self.config.remove_account(account_id)
        if result:
            self._save()
        return result

    def get_enabled_accounts(self) -> List[Account]:
        """获取所有启用的账号"""
        return self.config.get_enabled_accounts()

    def reload(self):
        """重新加载配置"""
        self._config = self.storage.load()
