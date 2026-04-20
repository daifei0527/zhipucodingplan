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
