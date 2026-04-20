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


def test_full_workflow(tmp_path):
    """测试完整工作流"""
    # 1. 创建账号管理器
    storage_path = tmp_path / "accounts.json"
    manager = AccountManager(str(storage_path))

    # 2. 添加账号
    account = manager.add_account(
        username="workflow@test.com",
        password="testpass",
        target_plans=[
            {"plan": "max", "duration": "monthly", "priority": 1},
            {"plan": "pro", "duration": "monthly", "priority": 2}
        ]
    )

    # 3. 验证账号
    assert account.id is not None
    assert len(account.target_plans) == 2

    # 4. 更新账号
    manager.update_account(account.id, enabled=False)
    updated = manager.get_account(account.id)
    assert updated.enabled is False

    # 5. 删除账号
    manager.delete_account(account.id)
    assert len(manager.list_accounts()) == 0
