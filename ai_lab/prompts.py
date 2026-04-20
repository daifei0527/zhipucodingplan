"""提示词模板"""
import json
from typing import Dict, Any, List


def build_analysis_prompt(event_type: str, context: Dict[str, Any]) -> str:
    """构建分析提示词"""

    error_message = context.get("error_message", context.get("message", ""))
    product_id = context.get("product_id", "")
    product_name = context.get("product_name", "")
    request_body = context.get("request_body", {})

    return f"""分析抢购API错误，返回JSON格式结果。

错误: {error_message}
产品: {product_name} ({product_id})
请求体: {json.dumps(request_body, ensure_ascii=False)}

这是下单API调用失败的错误。账户是新注册且已实名的。
分析可能原因，特别是API参数是否正确。

返回JSON:
{{
    "analysis": "分析原因",
    "possible_causes": ["可能原因1", "可能原因2"],
    "suggestions": ["改进建议"]
}}

只返回JSON。"""


def build_experiment_prompt(event_type: str, context: Dict[str, Any]) -> str:
    """生成实验方案的提示词"""

    error_message = context.get("error_message", context.get("message", ""))
    product_id = context.get("product_id", "")

    return f"""生成API实验方案来诊断下单错误。

错误: {error_message}
产品ID: {product_id}

需要探索:
1. 查询产品详情API看是否有额外字段
2. 查询账户信息API看购买资格
3. 尝试不同的API端点

返回JSON格式的实验方案:
{{
    "experiments": [
        {{
            "type": "api",
            "method": "GET",
            "url": "https://open.bigmodel.cn/api/xxx",
            "description": "实验目的"
        }}
    ]
}}

注意: 只生成查询类请求，不要下单。只返回JSON。"""


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
