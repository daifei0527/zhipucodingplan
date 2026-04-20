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
