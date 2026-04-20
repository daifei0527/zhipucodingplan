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
