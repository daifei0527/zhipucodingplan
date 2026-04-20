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
    account1 = Account(id="acc_001", username="user1", password="pass", status="idle")
    account2 = Account(id="acc_002", username="user2", password="pass", status="buying")
    scheduler.add_buyer(account1, MockBuyer())
    scheduler.add_buyer(account2, MockBuyer())

    all_status = scheduler.get_all_status()
    assert all_status["acc_001"] == "idle"
    assert all_status["acc_002"] == "buying"
