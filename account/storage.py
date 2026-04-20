"""账号配置存储"""
import json
from pathlib import Path
from typing import Optional

from .model import AccountsConfig, Account, TargetPlan


class AccountStorage:
    """账号配置 JSON 文件存储"""

    def __init__(self, path: str = "accounts.json"):
        self.path = Path(path)
        self._ensure_file()

    def _ensure_file(self):
        """确保存储文件存在"""
        if not self.path.exists():
            self.save(AccountsConfig())

    def load(self) -> AccountsConfig:
        """加载配置"""
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return AccountsConfig.from_dict(data)
        except (json.JSONDecodeError, FileNotFoundError):
            return AccountsConfig()

    def save(self, config: AccountsConfig):
        """保存配置"""
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)

    def migrate_from_config(self, config_path: str) -> AccountsConfig:
        """从旧的 config.json 迁移"""
        with open(config_path, 'r', encoding='utf-8') as f:
            old_config = json.load(f)

        accounts_config = AccountsConfig()

        # 从旧配置创建账号
        if "account" in old_config:
            account = Account(
                id="acc_001",
                username=old_config["account"]["username"],
                password=old_config["account"]["password"]
            )

            # 添加目标套餐
            if "target" in old_config:
                target = TargetPlan(
                    plan=old_config["target"]["plan"],
                    duration=old_config["target"]["duration"],
                    priority=1
                )
                account.target_plans.append(target)

            accounts_config.add_account(account)

        self.save(accounts_config)
        return accounts_config
