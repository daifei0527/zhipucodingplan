"""实验执行器 - 核心模块"""
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import aiohttp

from ai_lab.config import ExperimentConfig, get_experiment_config
from ai_lab.llm_client import LLMClient, get_llm_client
from learner.recorder import get_recorder


class ExperimentRunner:
    """实验执行器"""

    def __init__(self, config: ExperimentConfig = None):
        self.config = config or get_experiment_config()
        self.llm_client = LLMClient(self.config)
        self.recorder = get_recorder()

        # 实验记录文件
        self.log_file = Path("logs/ai_experiments.json")
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # 运行时状态
        self._recent_requests: List[Dict] = []
        self._recent_responses: List[Dict] = []
        self._experiments_log: List[Dict] = []

    def record_request(self, request_info: Dict):
        """记录请求信息供分析"""
        self._recent_requests.append({
            **request_info,
            "timestamp": datetime.now().isoformat()
        })
        # 只保留最近20条
        if len(self._recent_requests) > 20:
            self._recent_requests = self._recent_requests[-20:]

    def record_response(self, response_info: Dict):
        """记录响应信息供分析"""
        self._recent_responses.append({
            **response_info,
            "timestamp": datetime.now().isoformat()
        })
        # 只保留最近20条
        if len(self._recent_responses) > 20:
            self._recent_responses = self._recent_responses[-20:]

    async def trigger_experiment(
        self,
        event_type: str,
        session: aiohttp.ClientSession,
        account_id: str = None,
        extra_context: Dict = None
    ):
        """触发实验（异步，不阻塞主流程）

        Args:
            event_type: 事件类型
            session: aiohttp会话
            account_id: 账号ID
            extra_context: 额外上下文
        """
        if not self.config.enabled:
            return

        # 异步执行实验
        asyncio.create_task(self._run_experiment(
            event_type, session, account_id, extra_context
        ))

    async def _run_experiment(
        self,
        event_type: str,
        session: aiohttp.ClientSession,
        account_id: str,
        extra_context: Dict
    ):
        """执行实验"""
        experiment_id = f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.recorder.info(f"[AI Lab] 开始实验: {experiment_id}, 事件: {event_type}")

        # 构建上下文
        context = {
            "event_type": event_type,
            "recent_requests": self._recent_requests[-5:],
            "recent_responses": self._recent_responses[-5:],
            "inventory_status": self._get_inventory_status(),
            **(extra_context or {})
        }

        # 调用LLM分析
        analysis_result = await self.llm_client.analyze(event_type, context)

        if not analysis_result:
            self.recorder.error(f"[AI Lab] 实验分析失败: {experiment_id}")
            return

        # 执行实验请求
        experiments_tried = []
        experiments = analysis_result.get("experiments", [])[:self.config.max_experiments_per_event]

        for exp in experiments:
            result = await self._execute_experiment(session, exp)
            if result:
                experiments_tried.append(result)

        # 记录实验结果
        experiment_record = {
            "id": experiment_id,
            "timestamp": datetime.now().isoformat(),
            "trigger_event": event_type,
            "account_id": account_id,
            "model_analysis": analysis_result.get("analysis", ""),
            "experiments_tried": experiments_tried,
            "improvement_suggestions": analysis_result.get("suggestions", [])
        }

        self._save_experiment(experiment_record)

        self.recorder.info(
            f"[AI Lab] 实验完成: {experiment_id}, "
            f"尝试 {len(experiments_tried)} 个实验"
        )

    async def _execute_experiment(
        self,
        session: aiohttp.ClientSession,
        experiment: Dict
    ) -> Optional[Dict]:
        """执行单个实验请求"""
        exp_type = experiment.get("type", "api")
        method = experiment.get("method", "GET")
        url = experiment.get("url", "")
        headers = experiment.get("headers", {})
        body = experiment.get("body")
        expected = experiment.get("expected", "")

        # 安全检查：只允许查询类请求
        if "createPreOrder" in url or "pay" in url.lower():
            self.recorder.info(f"[AI Lab] 跳过非查询实验: {url}")
            return None

        self.recorder.info(f"[AI Lab] 执行实验: {exp_type} - {experiment.get('description', '')}")

        start_time = time.time()
        try:
            async with session.request(
                method,
                url,
                headers=headers,
                json=body if body else None,
                timeout=aiohttp.ClientTimeout(total=self.config.experiment_timeout)
            ) as resp:
                response_time = (time.time() - start_time) * 1000
                response_text = await resp.text()

                # 判断结果
                result = "success" if resp.status == 200 else "failed"

                # 尝试解析响应发现新信息
                discovery = ""
                try:
                    data = json.loads(response_text)
                    # 检查是否有意外的新字段
                    if isinstance(data, dict):
                        keys = list(data.keys())
                        if keys:
                            discovery = f"发现字段: {keys[:5]}"
                except:
                    pass

                return {
                    "type": exp_type,
                    "description": experiment.get("description", ""),
                    "url": url,
                    "result": result,
                    "status_code": resp.status,
                    "response_time_ms": round(response_time, 0),
                    "discovery": discovery
                }

        except asyncio.TimeoutError:
            return {
                "type": exp_type,
                "description": experiment.get("description", ""),
                "result": "timeout"
            }
        except Exception as e:
            return {
                "type": exp_type,
                "description": experiment.get("description", ""),
                "result": "error",
                "error": str(e)[:100]
            }

    def _get_inventory_status(self) -> str:
        """获取库存状态"""
        for resp in reversed(self._recent_responses):
            if "productList" in str(resp):
                return "available"
        return "unknown"

    def _save_experiment(self, record: Dict):
        """保存实验记录"""
        experiments = []
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    experiments = json.load(f)
            except:
                experiments = []

        experiments.append(record)

        # 只保留最近50条
        if len(experiments) > 50:
            experiments = experiments[-50:]

        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(experiments, f, ensure_ascii=False, indent=2)

        self._experiments_log = experiments

    def get_recent_experiments(self, limit: int = 10) -> List[Dict]:
        """获取最近实验记录"""
        if self._experiments_log:
            return self._experiments_log[-limit:]
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    experiments = json.load(f)
                    return experiments[-limit:]
            except:
                pass
        return []

    def get_improvement_suggestions(self) -> List[str]:
        """获取所有改进建议"""
        suggestions = []
        for exp in self.get_recent_experiments(20):
            for s in exp.get("improvement_suggestions", []):
                if s and s not in suggestions:
                    suggestions.append(s)
        return suggestions[:10]


# 全局实验运行器
_experiment_runner: Optional[ExperimentRunner] = None


def get_experiment_runner(config: ExperimentConfig = None) -> ExperimentRunner:
    """获取实验运行器实例"""
    global _experiment_runner
    if config is not None:
        _experiment_runner = ExperimentRunner(config)
    if _experiment_runner is None:
        _experiment_runner = ExperimentRunner()
    return _experiment_runner
