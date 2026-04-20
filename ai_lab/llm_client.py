"""大模型客户端 - 兼容Claude API格式"""
import asyncio
import json
import re
from typing import Optional, Dict, Any, List
import aiohttp

from ai_lab.config import ExperimentConfig, get_experiment_config
from learner.recorder import get_recorder


class LLMClient:
    """大模型客户端 - 支持Claude API兼容接口"""

    def __init__(self, config: ExperimentConfig = None):
        self.config = config or get_experiment_config()
        self.recorder = get_recorder()

    async def analyze(
        self,
        event_type: str,
        context: Dict[str, Any],
        timeout: int = None
    ) -> Optional[Dict[str, Any]]:
        """分析异常并生成实验方案

        Args:
            event_type: 事件类型 (rate_limit, captcha, auth_error, etc.)
            context: 上下文信息
            timeout: 超时时间(秒)

        Returns:
            {
                "analysis": "分析结果",
                "experiments": [...],
                "suggestions": [...]
            }
        """
        if not self.config.enabled:
            return None

        timeout = timeout or self.config.experiment_timeout

        from ai_lab.prompts import build_analysis_prompt

        prompt = build_analysis_prompt(event_type, context)

        try:
            result = await self._call_api(prompt, timeout)
            if result:
                return self._parse_response(result)
        except Exception as e:
            self.recorder.error(f"[AI Lab] LLM调用失败: {e}")

        return None

    async def _call_api(self, prompt: str, timeout: int) -> Optional[str]:
        """调用大模型API"""
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.config.api_key,
        }

        payload = {
            "model": self.config.model,
            "max_tokens": 2048,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.config.api_url.rstrip('/')}/messages"
                async with session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        # 兼容Claude API响应格式
                        if "content" in data:
                            for block in data["content"]:
                                if block.get("type") == "text":
                                    return block.get("text", "")
                        # 兼容OpenAI格式
                        elif "choices" in data:
                            return data["choices"][0].get("message", {}).get("content", "")
                    else:
                        self.recorder.error(f"[AI Lab] API返回错误: {resp.status}")
        except asyncio.TimeoutError:
            self.recorder.error(f"[AI Lab] API调用超时 ({timeout}s)")
        except Exception as e:
            self.recorder.error(f"[AI Lab] API调用异常: {e}")

        return None

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """解析LLM响应，提取JSON"""
        # 尝试提取JSON块
        try:
            # 尝试直接解析
            return json.loads(response)
        except:
            pass

        # 尝试提取代码块中的JSON
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except:
                pass

        # 返回原始文本作为分析结果
        return {
            "analysis": response,
            "experiments": [],
            "suggestions": []
        }


# 全局客户端实例
_llm_client: Optional[LLMClient] = None


def get_llm_client(config: ExperimentConfig = None) -> LLMClient:
    """获取LLM客户端实例"""
    global _llm_client
    if config is not None:
        _llm_client = LLMClient(config)
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
