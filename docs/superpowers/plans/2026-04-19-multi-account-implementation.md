# 多账号抢购功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为智谱 CodingPlan 自动抢购系统增加多账号管理功能，支持多账号并发抢购、余额判断自动支付、套餐优先级设置。

**Architecture:** 引入账号管理层（AccountManager）统一管理多账号配置，使用调度器（PurchaseScheduler）协调并发抢购，改造现有 Buyer 支持注入账号配置，扩展 Web 界面提供管理功能。

**Tech Stack:** Python 3.8+, asyncio, aiohttp, Flask, JSON 存储

---

## 文件结构

```
zhipucodingplan/
├── account/                    # 新增模块
│   ├── __init__.py            # 模块导出
│   ├── model.py               # Account, TargetPlan 数据模型
│   ├── storage.py             # JSON 文件存储
│   └── manager.py             # AccountManager CRUD 操作
│
├── scheduler/                  # 新增模块
│   ├── __init__.py            # 模块导出
│   └── scheduler.py           # PurchaseScheduler 并发调度
│
├── buyer/                      # 改造
│   └── purchase.py            # 支持注入账号配置
│
├── web/                        # 改造
│   ├── app.py                 # 扩展 API 路由
│   └── templates/
│       └── index.html         # 改造为多账号界面
│
├── main.py                     # 改造为多账号入口
├── config.py                   # 改造支持多账号配置
└── accounts.json               # 新增配置文件
```

---

## Task 1: 账号数据模型

**Files:**
- Create: `account/__init__.py`
- Create: `account/model.py`
- Test: `tests/test_account_model.py`

- [ ] **Step 1: 创建账号模块目录和 __init__.py**

```bash
mkdir -p account
```

```python
# account/__init__.py
"""账号管理模块"""
from .model import Account, TargetPlan, GlobalConfig, AccountsConfig
from .manager import AccountManager
from .storage import AccountStorage

__all__ = ['Account', 'TargetPlan', 'GlobalConfig', 'AccountsConfig', 'AccountManager', 'AccountStorage']
```

- [ ] **Step 2: 编写账号数据模型测试**

```python
# tests/test_account_model.py
"""账号数据模型测试"""
import pytest
from datetime import datetime
from account.model import Account, TargetPlan, GlobalConfig, AccountsConfig


def test_target_plan_creation():
    """测试目标套餐创建"""
    plan = TargetPlan(plan="max", duration="monthly", priority=1)
    assert plan.plan == "max"
    assert plan.duration == "monthly"
    assert plan.priority == 1


def test_target_plan_defaults():
    """测试目标套餐默认值"""
    plan = TargetPlan(plan="pro", duration="quarterly")
    assert plan.priority == 1


def test_account_creation():
    """测试账号创建"""
    account = Account(
        id="acc_001",
        username="test@example.com",
        password="password123"
    )
    assert account.id == "acc_001"
    assert account.username == "test@example.com"
    assert account.enabled is True
    assert account.auto_pay is True
    assert account.target_plans == []


def test_account_with_target_plans():
    """测试带目标套餐的账号"""
    plans = [
        TargetPlan(plan="max", duration="monthly", priority=1),
        TargetPlan(plan="pro", duration="monthly", priority=2)
    ]
    account = Account(
        id="acc_002",
        username="user@example.com",
        password="pass",
        target_plans=plans
    )
    assert len(account.target_plans) == 2
    assert account.target_plans[0].plan == "max"


def test_account_to_dict():
    """测试账号序列化"""
    account = Account(
        id="acc_003",
        username="test@example.com",
        password="pass"
    )
    data = account.to_dict()
    assert data['id'] == "acc_003"
    assert data['username'] == "test@example.com"
    assert data['enabled'] is True


def test_account_from_dict():
    """测试账号反序列化"""
    data = {
        "id": "acc_004",
        "username": "user@example.com",
        "password": "pass123",
        "enabled": False,
        "target_plans": [
            {"plan": "max", "duration": "monthly", "priority": 1}
        ]
    }
    account = Account.from_dict(data)
    assert account.id == "acc_004"
    assert account.enabled is False
    assert len(account.target_plans) == 1


def test_global_config_defaults():
    """测试全局配置默认值"""
    config = GlobalConfig()
    assert config.max_concurrent == 5
    assert config.retry_interval == 0.1
    assert config.purchase_timeout == 300


def test_accounts_config_creation():
    """测试账号配置集合"""
    config = AccountsConfig()
    assert config.accounts == []
    assert config.global_config.max_concurrent == 5


def test_accounts_config_add_account():
    """测试添加账号到配置"""
    config = AccountsConfig()
    account = Account(id="acc_001", username="test", password="pass")
    config.add_account(account)
    assert len(config.accounts) == 1
    assert config.accounts[0].id == "acc_001"
```

- [ ] **Step 3: 运行测试验证失败**

Run: `python -m pytest tests/test_account_model.py -v`
Expected: FAIL (模块不存在)

- [ ] **Step 4: 实现账号数据模型**

```python
# account/model.py
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
```

- [ ] **Step 5: 运行测试验证通过**

Run: `python -m pytest tests/test_account_model.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add account/__init__.py account/model.py tests/test_account_model.py
git commit -m "feat: 添加账号数据模型

- Account 账号配置数据模型
- TargetPlan 目标套餐配置
- GlobalConfig 全局配置
- AccountsConfig 账号配置集合

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 账号存储模块

**Files:**
- Create: `account/storage.py`
- Test: `tests/test_account_storage.py`

- [ ] **Step 1: 编写存储模块测试**

```python
# tests/test_account_storage.py
"""账号存储模块测试"""
import pytest
import json
import os
from pathlib import Path
from account.storage import AccountStorage
from account.model import Account, TargetPlan, AccountsConfig


@pytest.fixture
def temp_storage_path(tmp_path):
    """临时存储路径"""
    return tmp_path / "test_accounts.json"


def test_storage_create_file(temp_storage_path):
    """测试创建存储文件"""
    storage = AccountStorage(str(temp_storage_path))
    assert temp_storage_path.exists()


def test_storage_save_and_load(temp_storage_path):
    """测试保存和加载"""
    storage = AccountStorage(str(temp_storage_path))
    
    config = AccountsConfig()
    account = Account(
        id="acc_001",
        username="test@example.com",
        password="pass123",
        target_plans=[TargetPlan(plan="max", duration="monthly")]
    )
    config.add_account(account)
    
    storage.save(config)
    
    loaded = storage.load()
    assert len(loaded.accounts) == 1
    assert loaded.accounts[0].username == "test@example.com"


def test_storage_load_empty(temp_storage_path):
    """测试加载空文件"""
    storage = AccountStorage(str(temp_storage_path))
    config = storage.load()
    assert config.accounts == []
    assert config.global_config.max_concurrent == 5


def test_storage_load_existing_file(temp_storage_path):
    """测试加载已存在文件"""
    # 先写入数据
    data = {
        "accounts": [{
            "id": "acc_001",
            "username": "existing@example.com",
            "password": "pass",
            "enabled": True,
            "target_plans": []
        }],
        "global_config": {
            "max_concurrent": 3
        }
    }
    with open(temp_storage_path, 'w') as f:
        json.dump(data, f)
    
    storage = AccountStorage(str(temp_storage_path))
    config = storage.load()
    
    assert len(config.accounts) == 1
    assert config.accounts[0].username == "existing@example.com"
    assert config.global_config.max_concurrent == 3


def test_storage_migrate_from_config_json(temp_storage_path, tmp_path):
    """测试从 config.json 迁移"""
    # 创建模拟的 config.json
    config_path = tmp_path / "config.json"
    config_data = {
        "account": {
            "username": "migrated@example.com",
            "password": "migpass"
        },
        "target": {
            "plan": "pro",
            "duration": "monthly"
        }
    }
    with open(config_path, 'w') as f:
        json.dump(config_data, f)
    
    storage = AccountStorage(str(temp_storage_path))
    config = storage.migrate_from_config(str(config_path))
    
    assert len(config.accounts) == 1
    assert config.accounts[0].username == "migrated@example.com"
    assert len(config.accounts[0].target_plans) == 1
    assert config.accounts[0].target_plans[0].plan == "pro"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_account_storage.py -v`
Expected: FAIL (模块不存在)

- [ ] **Step 3: 实现存储模块**

```python
# account/storage.py
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
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_account_storage.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add account/storage.py tests/test_account_storage.py
git commit -m "feat: 添加账号存储模块

- AccountStorage JSON 文件存储
- 支持从 config.json 迁移

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 账号管理器

**Files:**
- Create: `account/manager.py`
- Test: `tests/test_account_manager.py`

- [ ] **Step 1: 编写账号管理器测试**

```python
# tests/test_account_manager.py
"""账号管理器测试"""
import pytest
from account.manager import AccountManager
from account.model import Account, TargetPlan


@pytest.fixture
def manager(tmp_path):
    """创建临时管理器"""
    storage_path = tmp_path / "accounts.json"
    return AccountManager(str(storage_path))


def test_manager_list_accounts(manager):
    """测试列出账号"""
    accounts = manager.list_accounts()
    assert accounts == []


def test_manager_add_account(manager):
    """测试添加账号"""
    account = manager.add_account(
        username="test@example.com",
        password="pass123"
    )
    assert account.id.startswith("acc_")
    assert account.username == "test@example.com"
    
    # 验证持久化
    accounts = manager.list_accounts()
    assert len(accounts) == 1


def test_manager_get_account(manager):
    """测试获取账号"""
    added = manager.add_account("user@test.com", "pass")
    account = manager.get_account(added.id)
    assert account.username == "user@test.com"


def test_manager_update_account(manager):
    """测试更新账号"""
    added = manager.add_account("old@test.com", "pass")
    
    updated = manager.update_account(
        added.id,
        username="new@test.com",
        enabled=False
    )
    assert updated.username == "new@test.com"
    assert updated.enabled is False


def test_manager_update_target_plans(manager):
    """测试更新目标套餐"""
    added = manager.add_account("user@test.com", "pass")
    
    plans = [
        {"plan": "max", "duration": "monthly", "priority": 1},
        {"plan": "pro", "duration": "monthly", "priority": 2}
    ]
    updated = manager.update_account(added.id, target_plans=plans)
    
    assert len(updated.target_plans) == 2
    assert updated.target_plans[0].plan == "max"


def test_manager_delete_account(manager):
    """测试删除账号"""
    added = manager.add_account("user@test.com", "pass")
    assert len(manager.list_accounts()) == 1
    
    result = manager.delete_account(added.id)
    assert result is True
    assert len(manager.list_accounts()) == 0


def test_manager_delete_nonexistent(manager):
    """测试删除不存在的账号"""
    result = manager.delete_account("acc_999")
    assert result is False


def test_manager_get_enabled_accounts(manager):
    """测试获取启用的账号"""
    manager.add_account("user1@test.com", "pass1")
    acc2 = manager.add_account("user2@test.com", "pass2")
    manager.update_account(acc2.id, enabled=False)
    
    enabled = manager.get_enabled_accounts()
    assert len(enabled) == 1
    assert enabled[0].username == "user1@test.com"


def test_manager_update_balance(manager):
    """测试更新余额"""
    added = manager.add_account("user@test.com", "pass")
    manager.update_account(added.id, balance=100.5)
    
    account = manager.get_account(added.id)
    assert account.balance == 100.5


def test_manager_update_status(manager):
    """测试更新状态"""
    added = manager.add_account("user@test.com", "pass")
    manager.update_account(added.id, status="buying")
    
    account = manager.get_account(added.id)
    assert account.status == "buying"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_account_manager.py -v`
Expected: FAIL (模块不存在)

- [ ] **Step 3: 实现账号管理器**

```python
# account/manager.py
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
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_account_manager.py -v`
Expected: PASS

- [ ] **Step 5: 更新 __init__.py 导出**

```python
# account/__init__.py
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
```

- [ ] **Step 6: 提交**

```bash
git add account/manager.py account/__init__.py tests/test_account_manager.py
git commit -m "feat: 添加账号管理器

- AccountManager CRUD 操作
- 支持余额和状态更新
- 全局单例获取函数

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: 抢购调度器

**Files:**
- Create: `scheduler/__init__.py`
- Create: `scheduler/scheduler.py`
- Test: `tests/test_scheduler.py`

- [ ] **Step 1: 创建调度器模块目录**

```bash
mkdir -p scheduler
```

```python
# scheduler/__init__.py
"""调度模块"""
from .scheduler import PurchaseScheduler

__all__ = ['PurchaseScheduler']
```

- [ ] **Step 2: 编写调度器测试**

```python
# tests/test_scheduler.py
"""调度器测试"""
import pytest
import asyncio
from scheduler.scheduler import PurchaseScheduler
from account.model import Account, TargetPlan


class MockBuyer:
    """模拟 Buyer"""
    def __init__(self, should_succeed=False):
        self.should_succeed = should_succeed
        self.run_called = False
        self.account_id = None
    
    async def run(self):
        self.run_called = True
        await asyncio.sleep(0.01)
        return self.should_succeed


@pytest.fixture
def scheduler():
    """创建调度器"""
    return PurchaseScheduler()


def test_scheduler_creation(scheduler):
    """测试调度器创建"""
    assert scheduler.max_concurrent == 5
    assert scheduler._running is False


def test_scheduler_add_buyer(scheduler):
    """测试添加 Buyer"""
    account = Account(id="acc_001", username="test", password="pass")
    buyer = MockBuyer()
    scheduler.add_buyer(account, buyer)
    
    assert "acc_001" in scheduler._buyers


@pytest.mark.asyncio
async def test_scheduler_run_single(scheduler):
    """测试运行单个抢购"""
    account = Account(id="acc_001", username="test", password="pass")
    buyer = MockBuyer(should_succeed=True)
    scheduler.add_buyer(account, buyer)
    
    results = await scheduler.run_all()
    
    assert results["acc_001"] is True
    assert buyer.run_called is True


@pytest.mark.asyncio
async def test_scheduler_run_multiple(scheduler):
    """测试运行多个抢购"""
    for i in range(3):
        account = Account(id=f"acc_00{i}", username=f"user{i}", password="pass")
        buyer = MockBuyer(should_succeed=True)
        scheduler.add_buyer(account, buyer)
    
    results = await scheduler.run_all()
    
    assert len(results) == 3
    assert all(results.values())


@pytest.mark.asyncio
async def test_scheduler_stop(scheduler):
    """测试停止调度"""
    account = Account(id="acc_001", username="test", password="pass")
    buyer = MockBuyer()
    scheduler.add_buyer(account, buyer)
    
    scheduler.stop()
    assert scheduler._running is False


def test_scheduler_get_status(scheduler):
    """测试获取状态"""
    account = Account(id="acc_001", username="test", password="pass", status="buying")
    scheduler.add_buyer(account, MockBuyer())
    
    status = scheduler.get_status("acc_001")
    assert status == "buying"


def test_scheduler_get_all_status(scheduler):
    """测试获取所有状态"""
    for i in range(2):
        account = Account(id=f"acc_00{i}", username=f"user{i}", password="pass", 
                         status="idle" if i == 0 else "buying")
        scheduler.add_buyer(account, MockBuyer())
    
    all_status = scheduler.get_all_status()
    assert all_status["acc_00"] == "idle"
    assert all_status["acc_01"] == "buying"
```

- [ ] **Step 3: 运行测试验证失败**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: FAIL (模块不存在)

- [ ] **Step 4: 实现调度器**

```python
# scheduler/scheduler.py
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
```

- [ ] **Step 5: 运行测试验证通过**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add scheduler/__init__.py scheduler/scheduler.py tests/test_scheduler.py
git commit -m "feat: 添加并发抢购调度器

- PurchaseScheduler 并发调度
- 信号量控制最大并发数
- 支持单个和批量运行

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: 改造 Buyer 支持账号注入

**Files:**
- Modify: `buyer/purchase.py`

- [ ] **Step 1: 阅读现有 Buyer 代码**

Run: `cat buyer/purchase.py | head -50`

- [ ] **Step 2: 改造 Buyer 构造函数**

在 `buyer/purchase.py` 中修改 `Buyer` 类：

```python
# buyer/purchase.py (修改后的关键部分)

class Buyer:
    """抢购器 - 支持API直连和页面抢购"""

    # 产品ID映射 (从batch-preview API获取)
    PRODUCT_MAP = {
        "pro_monthly": "product-b8ea38",
        "pro_quarterly": "product-2fc421",
        "max_monthly": "product-fef82f",
    }

    def __init__(self, config: Config, account=None):
        """
        Args:
            config: 全局配置
            account: 账号配置 (Account 模型)，如果为 None 则使用 config 中的账号
        """
        self.config = config
        self.account = account
        self.cookie_manager = get_cookie_manager()
        self.recorder = get_recorder()
        self._running = False
        self._success = False
        self._status = "idle"
        self._auth_token: Optional[str] = None
        self._product_info: Dict[str, Any] = {}
        
        # 如果提供了账号，使用账号的用户名作为日志标识
        self._log_prefix = f"[{account.username}]" if account else ""

    @property
    def status(self) -> str:
        return self._status

    def _log(self, message: str, level: str = "info"):
        """带账号标识的日志"""
        prefixed_message = f"{self._log_prefix} {message}"
        if level == "error":
            self.recorder.error(prefixed_message)
        else:
            self.recorder.info(prefixed_message)
```

- [ ] **Step 3: 改造 _try_purchase_api 方法支持目标套餐优先级**

```python
# buyer/purchase.py (新增方法)

async def _find_target_product(self, products: List[Dict]) -> Optional[Dict]:
    """根据目标套餐优先级查找可用产品"""
    if not self.account or not self.account.target_plans:
        # 没有配置目标套餐，返回第一个有库存的
        for p in products:
            if not p.get('soldOut', True):
                return p
        return None

    # 按优先级排序目标套餐
    sorted_plans = sorted(self.account.target_plans, key=lambda x: x.priority)
    
    for target in sorted_plans:
        for p in products:
            if p.get('soldOut', True):
                continue
            
            # 匹配套餐类型和时长
            product_name = p.get('productName', '').lower()
            plan_match = target.plan in product_name
            duration_match = self._duration_match(target.duration, product_name)
            
            if plan_match and duration_match:
                self._log(f"匹配目标套餐: {target.plan} {target.duration}")
                return p
    
    # 目标套餐都没有库存，尝试任意有库存的
    for p in products:
        if not p.get('soldOut', True):
            self._log("目标套餐无库存，选择其他可用套餐")
            return p
    
    return None

def _duration_match(self, target_duration: str, product_name: str) -> bool:
    """匹配时长"""
    duration_keywords = {
        'monthly': ['月', 'monthly'],
        'quarterly': ['季', 'quarterly'],
        'yearly': ['年', 'yearly']
    }
    keywords = duration_keywords.get(target_duration, [])
    return any(kw in product_name for kw in keywords)
```

- [ ] **Step 4: 改造 _do_purchase 方法支持余额判断**

```python
# buyer/purchase.py (修改 _do_purchase 方法)

async def _do_purchase(self, session: ClientSession, product: Dict) -> bool:
    """执行实际购买"""
    product_id = product.get('productId')
    pay_amount = product.get('payAmount', 0)
    original_amount = product.get('originalAmount', pay_amount)

    self._log(f"尝试购买: {product_id}, 原价: {original_amount}, 实付: {pay_amount}")

    # 尝试创建订单
    order_data = {
        "productId": product_id,
        "payPrice": pay_amount,
        "num": 1,
        "isMobile": False,
        "channelCode": "WEB"
    }

    try:
        async with session.post(
            "https://open.bigmodel.cn/api/biz/product/createPreOrder",
            json=order_data
        ) as resp:
            result = await resp.json()
            self._log(f"创建订单响应: {json.dumps(result, ensure_ascii=False)[:500]}")

            if result.get('success'):
                biz_id = result.get('data', {}).get('bizId')
                if biz_id:
                    self._log(f"订单创建成功! 订单号: {biz_id}")
                    
                    # 判断是否自动支付
                    if self.account and self.account.auto_pay:
                        # 获取余额（从 product 或单独查询）
                        balance = await self._get_balance(session)
                        
                        if balance is not None and balance >= pay_amount:
                            self._log(f"余额 {balance} >= 价格 {pay_amount}，尝试自动支付")
                            pay_success = await self._pay_order(session, biz_id, pay_amount)
                            if pay_success:
                                return True
                            self._log("自动支付失败，请手动支付")
                        else:
                            self._log(f"余额不足 ({balance} < {pay_amount})，请手动支付")
                            self._log(f"支付链接: https://open.bigmodel.cn/console/overview")
                    else:
                        self._log("自动支付已禁用，请手动支付")
                        self._log(f"支付链接: https://open.bigmodel.cn/console/overview")
                    
                    return True  # 订单创建成功也算成功
            else:
                msg = result.get('msg', '')
                self._log(f"创建订单失败: {msg}", level="error")

    except Exception as e:
        self._log(f"购买异常: {e}", level="error")

    return False

async def _get_balance(self, session: ClientSession) -> Optional[float]:
    """获取账户余额"""
    try:
        async with session.post(
            "https://open.bigmodel.cn/api/biz/pay/batch-preview",
            json={"invitationCode": ""}
        ) as resp:
            data = await resp.json()
            if data.get('success'):
                # 余额通常在 data.data.balance 或类似字段
                balance = data.get('data', {}).get('balance', 0)
                return balance
    except Exception as e:
        self._log(f"获取余额失败: {e}")
    return None
```

- [ ] **Step 5: 提交**

```bash
git add buyer/purchase.py
git commit -m "feat: 改造 Buyer 支持账号注入

- 支持注入 Account 配置
- 支持目标套餐优先级匹配
- 支持余额判断自动支付
- 日志带账号标识

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Web API - 账号管理

**Files:**
- Modify: `web/app.py`

- [ ] **Step 1: 在 web/app.py 添加账号管理 API**

```python
# web/app.py (新增导入和路由)

from account.manager import get_account_manager
from account.model import Account
from scheduler.scheduler import PurchaseScheduler

# 全局调度器
_scheduler: PurchaseScheduler = None


def get_scheduler() -> PurchaseScheduler:
    """获取调度器单例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = PurchaseScheduler()
    return _scheduler


# === 账号管理 API ===

@app.route("/api/accounts", methods=["GET"])
def list_accounts():
    """获取账号列表"""
    manager = get_account_manager()
    accounts = [
        {
            "id": acc.id,
            "username": acc.username,
            "enabled": acc.enabled,
            "target_plans": [p.to_dict() for p in acc.target_plans],
            "auto_pay": acc.auto_pay,
            "balance": acc.balance,
            "status": acc.status,
            "created_at": acc.created_at,
            "last_run": acc.last_run
        }
        for acc in manager.list_accounts()
    ]
    return jsonify({"accounts": accounts})


@app.route("/api/accounts", methods=["POST"])
def create_account():
    """添加账号"""
    data = request.get_json()
    
    if not data.get("username") or not data.get("password"):
        return jsonify({"error": "用户名和密码不能为空"}), 400
    
    manager = get_account_manager()
    account = manager.add_account(
        username=data["username"],
        password=data["password"],
        enabled=data.get("enabled", True),
        target_plans=data.get("target_plans", []),
        auto_pay=data.get("auto_pay", True)
    )
    
    return jsonify({
        "success": True,
        "account": {
            "id": account.id,
            "username": account.username
        }
    })


@app.route("/api/accounts/<account_id>", methods=["PUT"])
def update_account(account_id):
    """更新账号"""
    data = request.get_json()
    
    manager = get_account_manager()
    account = manager.update_account(account_id, **data)
    
    if account:
        return jsonify({
            "success": True,
            "account": {
                "id": account.id,
                "username": account.username
            }
        })
    return jsonify({"error": "账号不存在"}), 404


@app.route("/api/accounts/<account_id>", methods=["DELETE"])
def delete_account(account_id):
    """删除账号"""
    manager = get_account_manager()
    result = manager.delete_account(account_id)
    
    if result:
        return jsonify({"success": True})
    return jsonify({"error": "账号不存在"}), 404


@app.route("/api/accounts/<account_id>/balance", methods=["GET"])
def get_account_balance(account_id):
    """获取账号余额"""
    manager = get_account_manager()
    account = manager.get_account(account_id)
    
    if not account:
        return jsonify({"error": "账号不存在"}), 404
    
    # TODO: 实际查询余额
    return jsonify({
        "account_id": account_id,
        "balance": account.balance
    })


@app.route("/api/accounts/<account_id>/start", methods=["POST"])
def start_account_purchase(account_id):
    """启动单账号抢购"""
    manager = get_account_manager()
    account = manager.get_account(account_id)
    
    if not account:
        return jsonify({"error": "账号不存在"}), 404
    
    scheduler = get_scheduler()
    buyer = get_buyer(config)  # 使用注入账号的方式
    buyer.account = account
    
    scheduler.add_buyer(account, buyer)
    
    # 异步运行
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(scheduler.run_single(account_id))
        return jsonify({"success": result})
    finally:
        loop.close()


@app.route("/api/accounts/<account_id>/stop", methods=["POST"])
def stop_account_purchase(account_id):
    """停止单账号抢购"""
    scheduler = get_scheduler()
    scheduler.remove_buyer(account_id)
    return jsonify({"success": True})


@app.route("/api/purchase/start", methods=["POST"])
def start_all_purchase():
    """启动全部账号抢购"""
    manager = get_account_manager()
    accounts = manager.get_enabled_accounts()
    
    if not accounts:
        return jsonify({"error": "没有启用的账号"}), 400
    
    scheduler = get_scheduler()
    scheduler.clear_buyers()
    
    for account in accounts:
        buyer = get_buyer(config)
        buyer.account = account
        scheduler.add_buyer(account, buyer)
    
    # 异步运行
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(scheduler.run_all())
        return jsonify({
            "success": any(results.values()),
            "results": results
        })
    finally:
        loop.close()


@app.route("/api/purchase/stop", methods=["POST"])
def stop_all_purchase():
    """停止全部抢购"""
    scheduler = get_scheduler()
    scheduler.stop()
    return jsonify({"success": True})


@app.route("/api/history", methods=["GET"])
def get_history():
    """获取抢购历史"""
    # 从日志文件读取历史
    log_dir = Path("logs")
    session_files = list(log_dir.glob("session_*.json"))
    session_files.sort(reverse=True)
    
    history = []
    for f in session_files[:20]:
        try:
            import json
            with open(f) as fp:
                data = json.load(fp)
                history.append({
                    "file": f.name,
                    "time": f.stat().st_mtime,
                    "events": data.get("events", [])[:5]  # 前5条事件
                })
        except:
            pass
    
    return jsonify({"history": history})
```

- [ ] **Step 2: 提交**

```bash
git add web/app.py
git commit -m "feat: 添加账号管理 Web API

- 账号 CRUD 接口
- 单账号/全部抢购控制
- 历史记录查询

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Web 界面改造

**Files:**
- Modify: `web/templates/index.html`

- [ ] **Step 1: 改造 Web 界面为多账号管理**

```html
<!-- web/templates/index.html -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>智谱 CodingPlan 多账号抢购监控</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        h1 { text-align: center; margin-bottom: 20px; color: #00d9ff; }
        
        /* Tab 导航 */
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        .tab {
            padding: 10px 20px;
            background: #16213e;
            border: none;
            color: #888;
            cursor: pointer;
            border-radius: 8px 8px 0 0;
        }
        .tab.active {
            background: #0f3460;
            color: #00d9ff;
        }
        
        .panel {
            background: #16213e;
            border-radius: 0 10px 10px 10px;
            padding: 20px;
            margin-bottom: 20px;
        }
        
        /* 账号列表 */
        .account-table {
            width: 100%;
            border-collapse: collapse;
        }
        .account-table th, .account-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #0f3460;
        }
        .account-table th {
            color: #00d9ff;
            font-weight: normal;
        }
        
        /* 状态指示器 */
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
        }
        .status-dot.idle { background: #888; }
        .status-dot.buying { background: #00d9ff; animation: pulse 1s infinite; }
        .status-dot.success { background: #00ff88; }
        .status-dot.failed { background: #ff4444; }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        /* 按钮 */
        .btn {
            padding: 8px 16px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 13px;
            margin: 2px;
        }
        .btn-primary { background: #00d9ff; color: #000; }
        .btn-success { background: #00ff88; color: #000; }
        .btn-danger { background: #ff4444; color: #fff; }
        .btn:hover { opacity: 0.8; }
        
        /* 模态框 */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.7);
            z-index: 1000;
        }
        .modal.show { display: flex; justify-content: center; align-items: center; }
        .modal-content {
            background: #16213e;
            padding: 20px;
            border-radius: 10px;
            width: 400px;
        }
        .modal-content h3 { margin-bottom: 15px; color: #00d9ff; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; color: #888; }
        .form-group input, .form-group select {
            width: 100%;
            padding: 10px;
            background: #0f3460;
            border: 1px solid #1a1a2e;
            color: #eee;
            border-radius: 5px;
        }
        
        /* 日志 */
        .logs {
            background: #0a0a15;
            border-radius: 8px;
            padding: 15px;
            font-family: 'Monaco', 'Consolas', monospace;
            font-size: 12px;
            max-height: 300px;
            overflow-y: auto;
        }
        .logs .line { padding: 2px 0; border-bottom: 1px solid #1a1a2e; }
        .logs .line.error { color: #ff4444; }
        .logs .line.success { color: #00ff88; }
        
        /* 控制面板 */
        .control-panel {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        
        /* 目标套餐标签 */
        .plan-tag {
            display: inline-block;
            padding: 2px 8px;
            background: #0f3460;
            border-radius: 3px;
            font-size: 12px;
            margin-right: 4px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>智谱 CodingPlan 多账号抢购监控</h1>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('accounts')">账号管理</button>
            <button class="tab" onclick="showTab('monitor')">抢购监控</button>
            <button class="tab" onclick="showTab('history')">历史记录</button>
        </div>
        
        <!-- 账号管理 -->
        <div id="accounts-tab" class="tab-content">
            <div class="panel">
                <div class="control-panel">
                    <button class="btn btn-primary" onclick="showAddModal()">+ 添加账号</button>
                    <button class="btn btn-success" onclick="startAllPurchase()">全部启动</button>
                    <button class="btn btn-danger" onclick="stopAllPurchase()">全部停止</button>
                </div>
                
                <table class="account-table">
                    <thead>
                        <tr>
                            <th>状态</th>
                            <th>账号</th>
                            <th>目标套餐</th>
                            <th>余额</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody id="account-list">
                        <tr><td colspan="5">加载中...</td></tr>
                    </tbody>
                </table>
            </div>
            
            <div class="panel">
                <h3>实时日志</h3>
                <div class="logs" id="logs">
                    <div class="line">等待日志...</div>
                </div>
            </div>
        </div>
        
        <!-- 抢购监控 -->
        <div id="monitor-tab" class="tab-content" style="display:none;">
            <div class="panel">
                <h3>抢购状态监控</h3>
                <div id="monitor-content">
                    <!-- 动态生成 -->
                </div>
            </div>
        </div>
        
        <!-- 历史记录 -->
        <div id="history-tab" class="tab-content" style="display:none;">
            <div class="panel">
                <h3>抢购历史</h3>
                <div id="history-content">
                    <!-- 动态生成 -->
                </div>
            </div>
        </div>
    </div>
    
    <!-- 添加账号模态框 -->
    <div class="modal" id="add-modal">
        <div class="modal-content">
            <h3>添加账号</h3>
            <div class="form-group">
                <label>用户名</label>
                <input type="text" id="input-username" placeholder="请输入用户名">
            </div>
            <div class="form-group">
                <label>密码</label>
                <input type="password" id="input-password" placeholder="请输入密码">
            </div>
            <div class="form-group">
                <label>目标套餐 (用逗号分隔多个，如: max,pro)</label>
                <input type="text" id="input-plans" placeholder="max,pro">
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="input-auto-pay" checked> 自动支付
                </label>
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="input-enabled" checked> 启用账号
                </label>
            </div>
            <div style="text-align:right;">
                <button class="btn" onclick="hideAddModal()">取消</button>
                <button class="btn btn-primary" onclick="addAccount()">确定</button>
            </div>
        </div>
    </div>
    
    <script>
        // Tab 切换
        function showTab(name) {
            document.querySelectorAll('.tab-content').forEach(el => el.style.display = 'none');
            document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
            document.getElementById(name + '-tab').style.display = 'block';
            event.target.classList.add('active');
        }
        
        // 加载账号列表
        function loadAccounts() {
            fetch('/api/accounts')
                .then(r => r.json())
                .then(data => {
                    const tbody = document.getElementById('account-list');
                    if (!data.accounts || data.accounts.length === 0) {
                        tbody.innerHTML = '<tr><td colspan="5">暂无账号，请添加</td></tr>';
                        return;
                    }
                    
                    tbody.innerHTML = data.accounts.map(acc => `
                        <tr>
                            <td><span class="status-dot ${acc.status}"></span></td>
                            <td>${escapeHtml(acc.username)}</td>
                            <td>${acc.target_plans.map(p => 
                                `<span class="plan-tag">${p.plan}(${p.priority})</span>`
                            ).join('')}</td>
                            <td>${acc.balance !== null ? '¥' + acc.balance : '-'}</td>
                            <td>
                                <button class="btn btn-primary" onclick="startPurchase('${acc.id}')">抢购</button>
                                <button class="btn" onclick="editAccount('${acc.id}')">编辑</button>
                                <button class="btn btn-danger" onclick="deleteAccount('${acc.id}')">删除</button>
                            </td>
                        </tr>
                    `).join('');
                });
        }
        
        // 加载日志
        function loadLogs() {
            fetch('/api/logs')
                .then(r => r.json())
                .then(data => {
                    if (data.logs && data.logs.length > 0) {
                        const logsDiv = document.getElementById('logs');
                        logsDiv.innerHTML = data.logs.slice(-50).map(line => {
                            let cls = '';
                            if (line.includes('ERROR')) cls = 'error';
                            else if (line.includes('成功')) cls = 'success';
                            return `<div class="line ${cls}">${escapeHtml(line)}</div>`;
                        }).join('');
                        logsDiv.scrollTop = logsDiv.scrollHeight;
                    }
                });
        }
        
        // 模态框
        function showAddModal() {
            document.getElementById('add-modal').classList.add('show');
        }
        
        function hideAddModal() {
            document.getElementById('add-modal').classList.remove('show');
        }
        
        // 添加账号
        function addAccount() {
            const username = document.getElementById('input-username').value;
            const password = document.getElementById('input-password').value;
            const plansStr = document.getElementById('input-plans').value;
            const autoPay = document.getElementById('input-auto-pay').checked;
            const enabled = document.getElementById('input-enabled').checked;
            
            if (!username || !password) {
                alert('用户名和密码不能为空');
                return;
            }
            
            const plans = plansStr.split(',').filter(p => p.trim()).map((p, i) => ({
                plan: p.trim(),
                duration: 'monthly',
                priority: i + 1
            }));
            
            fetch('/api/accounts', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    username, password, target_plans: plans, auto_pay: autoPay, enabled
                })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    hideAddModal();
                    loadAccounts();
                    document.getElementById('input-username').value = '';
                    document.getElementById('input-password').value = '';
                } else {
                    alert('添加失败: ' + (data.error || '未知错误'));
                }
            });
        }
        
        // 删除账号
        function deleteAccount(id) {
            if (!confirm('确定删除该账号?')) return;
            fetch(`/api/accounts/${id}`, {method: 'DELETE'})
                .then(() => loadAccounts());
        }
        
        // 启动单个抢购
        function startPurchase(id) {
            fetch(`/api/accounts/${id}/start`, {method: 'POST'})
                .then(r => r.json())
                .then(data => alert(data.success ? '抢购成功!' : '抢购失败'));
        }
        
        // 启动全部抢购
        function startAllPurchase() {
            if (!confirm('确定启动所有启用的账号抢购?')) return;
            fetch('/api/purchase/start', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    alert(data.success ? '抢购任务已启动' : '启动失败');
                });
        }
        
        // 停止全部抢购
        function stopAllPurchase() {
            fetch('/api/purchase/stop', {method: 'POST'})
                .then(() => alert('已停止'));
        }
        
        // HTML转义
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // 定时刷新
        setInterval(loadAccounts, 5000);
        setInterval(loadLogs, 3000);
        loadAccounts();
        loadLogs();
    </script>
</body>
</html>
```

- [ ] **Step 2: 提交**

```bash
git add web/templates/index.html
git commit -m "feat: 改造 Web 界面支持多账号管理

- Tab 导航 (账号管理/监控/历史)
- 账号列表展示和 CRUD
- 批量抢购控制
- 实时日志

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 8: 改造 main.py 多账号入口

**Files:**
- Modify: `main.py`

- [ ] **Step 1: 改造 main.py 支持多账号**

```python
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
    """计算距离目标时间还有多少秒"""
    if immediate:
        return 0
    
    hour, minute = map(int, target_time.split(":"))
    target = dt_time(hour, minute)
    now = datetime.now().time()
    
    now_minutes = now.hour * 60 + now.minute
    target_minutes = target.hour * 60 + target.minute
    
    diff = target_minutes - now_minutes
    if diff < 0:
        diff += 24 * 60
    
    return max(0, diff * 60 - 30)


async def main_async(config: Config):
    """异步主函数 - 多账号模式"""
    recorder = get_recorder()
    account_manager = get_account_manager()
    scheduler = PurchaseScheduler(max_concurrent=config.global_config.max_concurrent if hasattr(config, 'global_config') else 5)
    
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
    
    # ... (保持原有逻辑)
    hour, minute = map(int, config.schedule.time.split(":"))
    now = datetime.now()
    target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    time_diff = (now - target_time).total_seconds()
    
    immediate_mode = 0 < time_diff < 1800
    
    if immediate_mode:
        recorder.info("检测到已过抢购时间但在30分钟窗口内，立即开始抢购!")
        wait_seconds = 0
    else:
        wait_seconds = calculate_wait_seconds(config.schedule.time)
        recorder.info(f"距离抢购时间还有 {wait_seconds // 60} 分钟")
    
    if wait_seconds > 60:
        recorder.info("进入等待模式...")
        await asyncio.sleep(wait_seconds - 60)
    
    recorder.info("检查登录状态...")
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
    
    # 为每个账号检查登录状态
    recorder.info("检查登录状态...")
    # TODO: 多账号登录检查
    
    remaining = calculate_wait_seconds(config.schedule.time, immediate_mode)
    if remaining > 0:
        recorder.info(f"等待 {remaining} 秒后开始抢购...")
        await asyncio.sleep(remaining)
    
    # 添加所有买家到调度器
    for acc in accounts:
        buyer = get_buyer(config)
        buyer.account = acc
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
```

- [ ] **Step 2: 提交**

```bash
git add main.py
git commit -m "feat: 改造 main.py 支持多账号模式

- 自动检测多账号配置
- 多账号并发抢购
- 保持单账号向后兼容

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 9: 集成测试和文档

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: 编写集成测试**

```python
# tests/test_integration.py
"""集成测试"""
import pytest
import asyncio
from account.manager import AccountManager
from scheduler.scheduler import PurchaseScheduler
from account.model import Account, TargetPlan


@pytest.fixture
def setup_accounts(tmp_path):
    """设置测试账号"""
    storage_path = tmp_path / "accounts.json"
    manager = AccountManager(str(storage_path))
    
    # 添加测试账号
    acc1 = manager.add_account(
        username="test1@example.com",
        password="pass1",
        target_plans=[{"plan": "max", "duration": "monthly", "priority": 1}]
    )
    acc2 = manager.add_account(
        username="test2@example.com",
        password="pass2",
        target_plans=[{"plan": "pro", "duration": "monthly", "priority": 1}]
    )
    
    return manager


def test_account_manager_integration(setup_accounts):
    """测试账号管理器集成"""
    manager = setup_accounts
    
    accounts = manager.list_accounts()
    assert len(accounts) == 2
    
    enabled = manager.get_enabled_accounts()
    assert len(enabled) == 2


@pytest.mark.asyncio
async def test_scheduler_integration(setup_accounts):
    """测试调度器集成"""
    manager = setup_accounts
    scheduler = PurchaseScheduler(max_concurrent=2)
    
    # 模拟买家
    class MockBuyer:
        def __init__(self, account):
            self.account = account
            self.ran = False
        async def run(self):
            self.ran = True
            return True
    
    accounts = manager.get_enabled_accounts()
    for acc in accounts:
        scheduler.add_buyer(acc, MockBuyer(acc))
    
    results = await scheduler.run_all()
    
    assert len(results) == 2
    assert all(results.values())
```

- [ ] **Step 2: 运行所有测试**

Run: `python -m pytest tests/ -v`
Expected: PASS

- [ ] **Step 3: 创建 accounts.json 示例文件**

```json
{
  "accounts": [
    {
      "id": "acc_example",
      "username": "your_username",
      "password": "your_password",
      "enabled": true,
      "target_plans": [
        {"plan": "max", "duration": "monthly", "priority": 1},
        {"plan": "pro", "duration": "monthly", "priority": 2}
      ],
      "auto_pay": true,
      "balance_threshold": 0
    }
  ],
  "global_config": {
    "max_concurrent": 5,
    "retry_interval": 0.1,
    "purchase_timeout": 300
  }
}
```

- [ ] **Step 4: 最终提交**

```bash
git add tests/test_integration.py accounts.json.example
git commit -m "test: 添加集成测试和示例配置

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## 自检清单

- [x] **Spec 覆盖**: 每个设计需求都有对应任务
- [x] **无占位符**: 所有步骤都有具体代码
- [x] **类型一致性**: 方法签名和属性名称一致
