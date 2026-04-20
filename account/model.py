"""账号数据模型"""
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class TargetPlan:
    """目标套餐配置"""
    plan: str  # lite, pro, max
    duration: str  # monthly, quarterly, yearly
    priority: int = 1  # 优先级，数字越小优先级越高

    def to_dict(self) -> dict:
        return {
            "plan": self.plan,
            "duration": self.duration,
            "priority": self.priority
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TargetPlan":
        return cls(
            plan=data["plan"],
            duration=data["duration"],
            priority=data.get("priority", 1)
        )


@dataclass
class Account:
    """账号配置"""
    id: str
    username: str
    password: str
    enabled: bool = True
    target_plans: List[TargetPlan] = field(default_factory=list)
    auto_pay: bool = True
    balance_threshold: float = 0
    created_at: Optional[str] = None
    last_run: Optional[str] = None
    balance: Optional[float] = None
    status: str = "idle"  # idle, warming, buying, success, failed

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "password": self.password,
            "enabled": self.enabled,
            "target_plans": [p.to_dict() for p in self.target_plans],
            "auto_pay": self.auto_pay,
            "balance_threshold": self.balance_threshold,
            "created_at": self.created_at,
            "last_run": self.last_run
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Account":
        target_plans = [TargetPlan.from_dict(p) for p in data.get("target_plans", [])]
        return cls(
            id=data["id"],
            username=data["username"],
            password=data["password"],
            enabled=data.get("enabled", True),
            target_plans=target_plans,
            auto_pay=data.get("auto_pay", True),
            balance_threshold=data.get("balance_threshold", 0),
            created_at=data.get("created_at"),
            last_run=data.get("last_run")
        )


@dataclass
class GlobalConfig:
    """全局配置"""
    max_concurrent: int = 5
    retry_interval: float = 0.1
    purchase_timeout: int = 300

    def to_dict(self) -> dict:
        return {
            "max_concurrent": self.max_concurrent,
            "retry_interval": self.retry_interval,
            "purchase_timeout": self.purchase_timeout
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GlobalConfig":
        return cls(
            max_concurrent=data.get("max_concurrent", 5),
            retry_interval=data.get("retry_interval", 0.1),
            purchase_timeout=data.get("purchase_timeout", 300)
        )


@dataclass
class AccountsConfig:
    """账号配置集合"""
    accounts: List[Account] = field(default_factory=list)
    global_config: GlobalConfig = field(default_factory=GlobalConfig)

    def add_account(self, account: Account):
        """添加账号"""
        self.accounts.append(account)

    def remove_account(self, account_id: str) -> bool:
        """移除账号"""
        for i, acc in enumerate(self.accounts):
            if acc.id == account_id:
                self.accounts.pop(i)
                return True
        return False

    def get_account(self, account_id: str) -> Optional[Account]:
        """获取账号"""
        for acc in self.accounts:
            if acc.id == account_id:
                return acc
        return None

    def get_enabled_accounts(self) -> List[Account]:
        """获取所有启用的账号"""
        return [acc for acc in self.accounts if acc.enabled]

    def to_dict(self) -> dict:
        return {
            "accounts": [acc.to_dict() for acc in self.accounts],
            "global_config": self.global_config.to_dict()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AccountsConfig":
        accounts = [Account.from_dict(acc) for acc in data.get("accounts", [])]
        global_config = GlobalConfig.from_dict(data.get("global_config", {}))
        return cls(accounts=accounts, global_config=global_config)
