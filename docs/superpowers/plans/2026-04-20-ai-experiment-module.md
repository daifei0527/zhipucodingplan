# AI实验模块实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在抢购过程中集成远程大模型服务，实时分析异常并执行探索性实验，实验结果用于改进下次抢购代码。

**Architecture:** 采用轻量级集成模式，实验模块异步运行不阻塞主进程。关键事件（限流/验证码/异常等）触发实验，大模型生成实验方案并执行，结果记录到日志文件供后续改进参考。

**Tech Stack:** Python 3.10+, aiohttp, anthropic SDK (兼容格式), dataclasses

---

## 文件结构

```
ai_lab/
├── __init__.py         # 模块入口，导出主要类
├── config.py           # AI实验配置模型
├── llm_client.py       # 大模型调用封装
├── experiment.py       # 实验执行器(核心)
└── prompts.py          # 提示词模板

buyer/
└── purchase.py         # 修改：添加实验触发点

web/
├── app.py              # 修改：添加AI实验API
└── templates/index.html # 修改：显示AI实验结果

config.py               # 修改：添加AILabConfig

tests/
└── test_ai_lab.py      # 新增：AI实验模块测试
```

---

### Task 1: AI实验配置模型

**Files:**
- Modify: `config.py`

- [ ] **Step 1: 添加AILabConfig数据类**

在 `config.py` 中添加：

```python
@dataclass
class AILabConfig:
    """AI实验配置"""
    enabled: bool = False
    api_url: str = ""
    api_key: str = ""
    model: str = "claude-3-sonnet"
    max_experiments_per_event: int = 3
    experiment_timeout: int = 5
```

- [ ] **Step 2: 修改Config类添加ai_lab字段**

```python
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
```

- [ ] **Step 3: 验证配置加载**

```bash
python3 -c "from config import Config, AILabConfig; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add config.py
git commit -m "feat: 添加AI实验配置模型"
```

---

### Task 2: 创建ai_lab模块结构

**Files:**
- Create: `ai_lab/__init__.py`
- Create: `ai_lab/config.py`

- [ ] **Step 1: 创建ai_lab目录**

```bash
mkdir -p ai_lab
```

- [ ] **Step 2: 创建ai_lab/__init__.py**

```python
"""AI实验模块 - 集成大模型进行实时分析和实验"""
from .config import ExperimentConfig, get_experiment_config
from .llm_client import LLMClient
from .experiment import ExperimentRunner, get_experiment_runner

__all__ = [
    'ExperimentConfig', 'get_experiment_config',
    'LLMClient',
    'ExperimentRunner', 'get_experiment_runner',
]
```

- [ ] **Step 3: 创建ai_lab/config.py**

```python
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
```

- [ ] **Step 4: 验证模块导入**

```bash
python3 -c "from ai_lab import ExperimentConfig, get_experiment_config; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add ai_lab/__init__.py ai_lab/config.py
git commit -m "feat: 创建AI实验模块基础结构"
```

---

### Task 3: LLM客户端实现

**Files:**
- Create: `ai_lab/llm_client.py`

- [ ] **Step 1: 创建ai_lab/llm_client.py**

```python
"""大模型客户端 - 兼容Claude API格式"""
import asyncio
import json
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
        import re
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
```

- [ ] **Step 2: 验证LLM客户端导入**

```bash
python3 -c "from ai_lab.llm_client import LLMClient; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add ai_lab/llm_client.py
git commit -m "feat: 实现LLM客户端"
```

---

### Task 4: 提示词模板

**Files:**
- Create: `ai_lab/prompts.py`

- [ ] **Step 1: 创建ai_lab/prompts.py**

```python
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
    }

    event_desc = event_descriptions.get(event_type, f"未知事件: {event_type}")

    # 格式化上下文信息
    recent_requests = context.get("recent_requests", [])[:5]
    recent_responses = context.get("recent_responses", [])[:5]
    inventory_status = context.get("inventory_status", "unknown")

    context_str = f"""
## 当前情况
- 事件类型: {event_type}
- 事件描述: {event_desc}
- 库存状态: {inventory_status}

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
```

- [ ] **Step 2: 验证模块导入**

```bash
python3 -c "from ai_lab.prompts import build_analysis_prompt; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add ai_lab/prompts.py
git commit -m "feat: 实现提示词模板"
```

---

### Task 5: 实验执行器

**Files:**
- Create: `ai_lab/experiment.py`

- [ ] **Step 1: 创建ai_lab/experiment.py**

```python
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
```

- [ ] **Step 2: 验证模块导入**

```bash
python3 -c "from ai_lab.experiment import ExperimentRunner, get_experiment_runner; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add ai_lab/experiment.py
git commit -m "feat: 实现实验执行器"
```

---

### Task 6: 集成到抢购模块

**Files:**
- Modify: `buyer/purchase.py`

- [ ] **Step 1: 添加AI实验模块导入**

在 `buyer/purchase.py` 顶部添加：

```python
from ai_lab.experiment import get_experiment_runner
from ai_lab.config import get_experiment_config
```

- [ ] **Step 2: 在Buyer.__init__中初始化实验运行器**

```python
def __init__(self, config: Config, account=None):
    # ... 现有代码 ...
    
    # AI实验运行器
    self._experiment_runner = get_experiment_runner(get_experiment_config(config))
```

- [ ] **Step 3: 在_try_purchase_api中添加实验触发点**

在检测到限流、验证码、网络错误时触发实验：

```python
# 在 rate_limit 检测后添加
if '限流' in msg or '频繁' in msg or 'rate' in msg.lower():
    error_type = "rate_limit"
    # 触发AI实验
    self._experiment_runner.trigger_experiment(
        "rate_limit",
        session,
        self.account.id if self.account else None,
        {"message": msg}
    )

# 在 captcha 检测后添加
if '验证' in msg or '安全' in msg:
    error_type = "captcha"
    # 触发AI实验
    self._experiment_runner.trigger_experiment(
        "captcha",
        session,
        self.account.id if self.account else None,
        {"message": msg}
    )

# 在 network_error 处理后添加
except aiohttp.ClientError as e:
    # 触发AI实验
    self._experiment_runner.trigger_experiment(
        "network_error",
        session,
        self.account.id if self.account else None,
        {"error": str(e)}
    )
```

- [ ] **Step 4: 记录请求和响应到实验运行器**

```python
# 在 _try_purchase_api 中，记录请求
self._experiment_runner.record_request({
    "url": "https://open.bigmodel.cn/api/biz/pay/batch-preview",
    "method": "POST",
    "attempt": attempt
})

# 在获取响应后，记录响应
self._experiment_runner.record_response({
    "status_code": resp.status,
    "has_inventory": has_inventory,
    "products_count": len(products) if products else 0
})
```

- [ ] **Step 5: 验证集成**

```bash
python3 -c "from buyer.purchase import Buyer; print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add buyer/purchase.py
git commit -m "feat: 集成AI实验模块到抢购流程"
```

---

### Task 7: Web API和界面

**Files:**
- Modify: `web/app.py`
- Modify: `web/templates/index.html`

- [ ] **Step 1: 在web/app.py添加AI实验API**

```python
from ai_lab.experiment import get_experiment_runner

@app.route("/api/ai-experiments", methods=["GET"])
def get_ai_experiments():
    """获取AI实验记录"""
    runner = get_experiment_runner()
    experiments = runner.get_recent_experiments(20)
    suggestions = runner.get_improvement_suggestions()
    return jsonify({
        "experiments": experiments,
        "suggestions": suggestions
    })
```

- [ ] **Step 2: 在index.html添加AI实验显示区域**

在"分析报告"Tab中添加：

```html
<div class="panel">
    <h3>🧪 AI实验结果</h3>
    <div id="ai-experiments-content">
        <div class="empty-state">暂无AI实验数据</div>
    </div>
</div>

<div class="panel">
    <h3>💡 AI改进建议</h3>
    <div id="ai-suggestions-content">
        <div class="empty-state">暂无改进建议</div>
    </div>
</div>
```

- [ ] **Step 3: 添加JavaScript加载AI实验数据**

```javascript
function loadAIExperiments() {
    fetch('/api/ai-experiments')
        .then(r => r.json())
        .then(data => {
            const expContent = document.getElementById('ai-experiments-content');
            const sugContent = document.getElementById('ai-suggestions-content');

            if (data.experiments && data.experiments.length > 0) {
                expContent.innerHTML = data.experiments.slice(-5).map(exp => `
                    <div class="suggestion-card ${exp.experiments_tried?.some(e => e.result === 'success') ? 'low' : 'medium'}">
                        <h4>🧪 ${exp.trigger_event} - ${exp.id}</h4>
                        <p>${exp.model_analysis || '分析中...'}</p>
                        <p><strong>实验数:</strong> ${exp.experiments_tried?.length || 0}</p>
                        <p><strong>时间:</strong> ${exp.timestamp}</p>
                    </div>
                `).join('');
            }

            if (data.suggestions && data.suggestions.length > 0) {
                sugContent.innerHTML = data.suggestions.map(s => `
                    <div class="suggestion-card low">
                        <p>💡 ${s}</p>
                    </div>
                `).join('');
            }
        });
}
```

- [ ] **Step 4: 在loadAnalysis中调用loadAIExperiments**

```javascript
function loadAnalysis() {
    // ... 现有代码 ...
    loadAIExperiments();
}
```

- [ ] **Step 5: 验证Web API**

```bash
# 启动程序后测试
curl http://127.0.0.1:5000/api/ai-experiments
```

- [ ] **Step 6: Commit**

```bash
git add web/app.py web/templates/index.html
git commit -m "feat: 添加AI实验Web界面"
```

---

### Task 8: 更新配置示例

**Files:**
- Modify: `config.json` (如存在) 或创建示例

- [ ] **Step 1: 添加ai_lab配置示例**

```json
{
    "ai_lab": {
        "enabled": false,
        "api_url": "https://your-qianfan-url/v1",
        "api_key": "your-api-key",
        "model": "claude-3-sonnet",
        "max_experiments_per_event": 3,
        "experiment_timeout": 5
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add config.json 2>/dev/null || echo "config.json not tracked"
git commit -m "docs: 添加AI实验配置示例" --allow-empty
```

---

## 验收清单

- [ ] `config.py` 包含 `AILabConfig` 数据类
- [ ] `ai_lab/` 模块可正常导入
- [ ] `LLMClient` 可调用兼容Claude API的服务
- [ ] `ExperimentRunner` 可触发异步实验
- [ ] 抢购流程中集成了实验触发点
- [ ] Web界面可查看AI实验结果
- [ ] 主抢购流程不受实验模块影响
