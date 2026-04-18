"""配置管理模块"""
import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class AccountConfig:
    username: str
    password: str


@dataclass
class TargetConfig:
    plan: str  # lite, pro, max
    duration: str  # monthly, quarterly, yearly


@dataclass
class ScheduleConfig:
    time: str  # HH:MM format
    timezone: str


@dataclass
class WebConfig:
    port: int
    host: str


@dataclass
class ZhipuConfig:
    login_url: str
    coding_url: str


@dataclass
class Config:
    account: AccountConfig
    target: TargetConfig
    schedule: ScheduleConfig
    web: WebConfig
    zhipu: ZhipuConfig

    @classmethod
    def load(cls, path: str = "config.json") -> "Config":
        """从JSON文件加载配置"""
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return cls(
            account=AccountConfig(**data["account"]),
            target=TargetConfig(**data["target"]),
            schedule=ScheduleConfig(**data["schedule"]),
            web=WebConfig(**data["web"]),
            zhipu=ZhipuConfig(**data["zhipu"]),
        )

    def validate(self) -> bool:
        """验证配置是否完整"""
        if not self.account.username or not self.account.password:
            return False
        return True


def get_config(path: str = "config.json") -> Config:
    """获取配置实例"""
    return Config.load(path)
