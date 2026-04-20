"""提示词模板"""
import json
from typing import Dict, Any, List


def build_analysis_prompt(event_type: str, context: Dict[str, Any]) -> str:
    """构建分析提示词

    Args:
        event_type: 事件类型
        context: 上下文信息，包含 recent_requests, recent_responses, inventory_status 等

    Returns:
        完整的提示词
    """
    event_descriptions = {
        "rate_limit": "服务器返回限流错误，请求被拒绝",
        "captcha": "检测到验证码要求，需要安全验证",
        "auth_error": "认证失败，Token无效或过期",
        "inventory_found": "首次发现库存，准备下单",
        "network_error": "网络请求失败，连接异常",
        "unexpected_response": "收到未知格式的响应",
        "order_error": "创建订单失败，服务器返回错误",
    }

    event_desc = event_descriptions.get(event_type, f"未知事件: {event_type}")

    # 格式化上下文信息
    recent_requests = context.get("recent_requests", [])[:5]
    recent_responses = context.get("recent_responses", [])[:5]
    inventory_status = context.get("inventory_status", "unknown")
    error_message = context.get("error_message", context.get("message", ""))

    context_str = f"""
## 当前情况
- 事件类型: {event_type}
- 事件描述: {event_desc}
- 库存状态: {inventory_status}
- 错误信息: {error_message}

## 最近请求记录
{json.dumps(recent_requests, ensure_ascii=False, indent=2)}

## 最近响应记录
{json.dumps(recent_responses, ensure_ascii=False, indent=2)}
"""

    return f"""你是一个抢购系统的问题分析专家。当前抢购过程遇到了异常情况，请分析原因并提出实验方案。

{context_str}

请分析以上情况，并以JSON格式返回你的分析和建议。格式如下：

```json
{{
    "analysis": "对当前异常的简要分析",
    "experiments": [
        {{
            "type": "api|header|timing|param",
            "description": "实验描述",
            "method": "GET|POST",
            "url": "请求URL",
            "headers": {{}},
            "body": {{}},
            "expected": "预期结果"
        }}
    ],
    "suggestions": [
        "改进建议1",
        "改进建议2"
    ]
}}
```

注意事项：
1. experiments数组最多3个实验方案
2. 实验请求必须是只读查询，不能下单或支付
3. 优先探索可能提高成功率的方法
4. 如果是限流，考虑降低频率或换端点
5. 如果是验证码，分析触发原因
6. 如果是订单错误，分析错误原因

请只返回JSON，不要有其他内容。"""


def build_summary_prompt(experiments: List[Dict[str, Any]]) -> str:
    """构建总结提示词，用于生成最终改进建议"""
    return f"""基于以下实验结果，请总结改进建议：

{json.dumps(experiments, ensure_ascii=False, indent=2)}

请以JSON格式返回改进建议：
```json
{{
    "improvements": [
        {{
            "priority": "high|medium|low",
            "category": "api|header|timing|param",
            "description": "改进描述",
            "code_suggestion": "具体代码修改建议（可选）"
        }}
    ],
    "summary": "总体改进方向"
}}
```
"""
