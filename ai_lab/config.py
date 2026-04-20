"""AI实验配置"""
from dataclasses import dataclass
from typing import Optional
from config import Config, AILabConfig


@dataclass
class ExperimentConfig:
    """实验运行时配置"""
    enabled: bool
    api_url: str
    api_key: str
    model: str
    max_experiments_per_event: int
    experiment_timeout: int

    @classmethod
    def from_config(cls, config: Config) -> "ExperimentConfig":
        """从全局配置创建"""
        ai_lab = config.ai_lab
        if ai_lab is None:
            return cls(
                enabled=False,
                api_url="",
                api_key="",
                model="claude-3-sonnet",
                max_experiments_per_event=3,
                experiment_timeout=5
            )
        return cls(
            enabled=ai_lab.enabled,
            api_url=ai_lab.api_url,
            api_key=ai_lab.api_key,
            model=ai_lab.model,
            max_experiments_per_event=ai_lab.max_experiments_per_event,
            experiment_timeout=ai_lab.experiment_timeout
        )


# 全局配置实例
_experiment_config: Optional[ExperimentConfig] = None


def get_experiment_config(config: Config = None) -> ExperimentConfig:
    """获取实验配置"""
    global _experiment_config
    if config is not None:
        _experiment_config = ExperimentConfig.from_config(config)
    if _experiment_config is None:
        return ExperimentConfig(
            enabled=False,
            api_url="",
            api_key="",
            model="claude-3-sonnet",
            max_experiments_per_event=3,
            experiment_timeout=5
        )
    return _experiment_config
