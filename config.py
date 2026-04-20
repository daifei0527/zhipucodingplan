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
class AILabConfig:
    """AI实验配置"""
    enabled: bool = False
    api_url: str = ""
    api_key: str = ""
    model: str = "claude-3-sonnet"
    max_experiments_per_event: int = 3
    experiment_timeout: int = 5


@dataclass
class Config:
    account: AccountConfig
    target: TargetConfig
    schedule: ScheduleConfig
    web: WebConfig
    zhipu: ZhipuConfig
    ai_lab: Optional[AILabConfig] = None

    @classmethod
    def load(cls, path: str = "config.json") -> "Config":
        """从JSON文件加载配置"""
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {path}")

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        ai_lab = None
        if "ai_lab" in data:
            ai_lab = AILabConfig(**data["ai_lab"])

        return cls(
            account=AccountConfig(**data["account"]),
            target=TargetConfig(**data["target"]),
            schedule=ScheduleConfig(**data["schedule"]),
            web=WebConfig(**data["web"]),
            zhipu=ZhipuConfig(**data["zhipu"]),
            ai_lab=ai_lab,
        )

    def validate(self) -> bool:
        """验证配置是否完整"""
        if not self.account.username or not self.account.password:
            return False
        return True


def get_config(path: str = "config.json") -> Config:
    """获取配置实例"""
    return Config.load(path)
