# 智谱 CodingPlan 自动抢购脚本实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个自动化脚本，在每天10:00自动抢购智谱 CodingPlan Pro 包月会员。

**Architecture:** 混合架构 - Playwright处理登录和验证码（headless模式），aiohttp发送高频HTTP请求抢购，Flask提供Web监控界面，学习模块记录每次运行数据逐步完善流程。

**Tech Stack:** Python 3.10+, Playwright, aiohttp, Flask, systemd

---

## 文件结构

```
zhipu-buyer/
├── config.json              # 配置文件（账号密码等）
├── cookies.json             # 保存的Cookie
├── main.py                  # 主入口
├── config.py                # 配置读取模块
├── auth/
│   ├── __init__.py
│   └── login.py             # 登录逻辑
├── buyer/
│   ├── __init__.py
│   └── purchase.py          # 抢购逻辑
├── learner/
│   ├── __init__.py
│   └── recorder.py          # 学习记录逻辑
├── web/
│   ├── __init__.py
│   ├── app.py               # Flask应用
│   └── templates/
│       └── index.html       # 监控页面
├── logs/                    # 日志目录
└── requirements.txt         # Python依赖
```

---

## Task 1: 项目初始化

**Files:**
- Create: `requirements.txt`
- Create: `config.json`
- Create: `config.py`
- Create: `logs/.gitkeep`
- Create: `auth/__init__.py`
- Create: `buyer/__init__.py`
- Create: `learner/__init__.py`
- Create: `web/__init__.py`

- [ ] **Step 1: 创建项目目录结构**

```bash
cd /home/daifei/zhipucodingplan
mkdir -p auth buyer learner web/templates logs
touch auth/__init__.py buyer/__init__.py learner/__init__.py web/__init__.py logs/.gitkeep
```

- [ ] **Step 2: 创建 requirements.txt**

```text
playwright==1.51.0
aiohttp==3.9.5
flask==3.0.3
python-dateutil==2.9.0
```

- [ ] **Step 3: 创建 config.json 模板**

```json
{
  "account": {
    "username": "",
    "password": ""
  },
  "target": {
    "plan": "pro",
    "duration": "monthly"
  },
  "schedule": {
    "time": "10:00",
    "timezone": "Asia/Shanghai"
  },
  "web": {
    "port": 5000,
    "host": "127.0.0.1"
  },
  "zhipu": {
    "login_url": "https://open.bigmodel.cn/login",
    "coding_url": "https://open.bigmodel.cn/glm-coding"
  }
}
```

- [ ] **Step 4: 创建 config.py 配置读取模块**

```python
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
```

- [ ] **Step 5: 安装依赖**

```bash
pip install -r requirements.txt
playwright install chromium
```

- [ ] **Step 6: 设置配置文件权限**

```bash
chmod 600 config.json
```

- [ ] **Step 7: 初始化 git 并提交**

```bash
git init
git add .
git commit -m "feat: 初始化项目结构"
```

---

## Task 2: 学习/日志模块

**Files:**
- Create: `learner/recorder.py`

这个模块最先实现，因为其他模块都需要用它记录日志。

- [ ] **Step 1: 编写 learner/recorder.py**

```python
"""学习和日志记录模块"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, asdict
import asyncio
from aiohttp import ClientResponse


@dataclass
class RequestRecord:
    """单次请求记录"""
    timestamp: str
    url: str
    method: str
    headers: dict
    params: Optional[dict]
    data: Optional[dict]
    status_code: int
    response_text: str[:1000]  # 限制长度
    response_time_ms: float
    error: Optional[str] = None


class Recorder:
    """请求记录器"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_session: list[RequestRecord] = []
        self._session_start: Optional[datetime] = None
    
    def start_session(self):
        """开始新的记录会话"""
        self._current_session = []
        self._session_start = datetime.now()
        self.info(f"=== 新会话开始 {self._session_start.isoformat()} ===")
    
    def _get_log_file(self) -> Path:
        """获取当天的日志文件路径"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"{date_str}.log"
    
    def info(self, message: str):
        """记录信息日志"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] INFO: {message}\n"
        self._append_log(line)
        print(line.strip())
    
    def error(self, message: str):
        """记录错误日志"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] ERROR: {message}\n"
        self._append_log(line)
        print(line.strip())
    
    def _append_log(self, line: str):
        """追加日志行到文件"""
        log_file = self._get_log_file()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
    
    async def record_request(
        self,
        url: str,
        method: str,
        headers: dict,
        params: Optional[dict],
        data: Optional[dict],
        response: Optional[ClientResponse],
        response_time_ms: float,
        error: Optional[str] = None
    ) -> RequestRecord:
        """记录一次HTTP请求"""
        status_code = response.status if response else 0
        response_text = ""
        if response:
            try:
                response_text = await response.text()
            except:
                response_text = "[无法读取响应]"
        
        record = RequestRecord(
            timestamp=datetime.now().isoformat(),
            url=url,
            method=method,
            headers=dict(headers) if headers else {},
            params=params,
            data=data,
            status_code=status_code,
            response_text=response_text[:1000],
            response_time_ms=response_time_ms,
            error=error
        )
        
        self._current_session.append(record)
        
        # 记录简要日志
        log_msg = f"请求 {method} {url} -> {status_code} ({response_time_ms:.0f}ms)"
        if error:
            log_msg += f" ERROR: {error}"
        self.info(log_msg)
        
        return record
    
    def save_session(self):
        """保存当前会话记录到JSON文件"""
        if not self._current_session:
            return
        
        session_file = self.log_dir / f"session_{self._session_start.strftime('%Y%m%d_%H%M%S')}.json"
        data = {
            "session_start": self._session_start.isoformat() if self._session_start else None,
            "records": [asdict(r) for r in self._current_session]
        }
        
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        self.info(f"会话记录已保存: {session_file}")
    
    def get_discoveries(self) -> list[dict]:
        """从历史记录中发现的API接口"""
        discoveries = []
        for record in self._current_session:
            if record.status_code == 200 and "api" in record.url.lower():
                discoveries.append({
                    "url": record.url,
                    "method": record.method,
                    "params": record.params,
                    "data": record.data
                })
        return discoveries


# 全局记录器实例
_recorder: Optional[Recorder] = None


def get_recorder() -> Recorder:
    """获取全局记录器实例"""
    global _recorder
    if _recorder is None:
        _recorder = Recorder()
    return _recorder
```

- [ ] **Step 2: 提交代码**

```bash
git add learner/recorder.py
git commit -m "feat: 添加学习/日志记录模块"
```

---

## Task 3: Cookie 管理

**Files:**
- Create: `auth/cookies.py`

- [ ] **Step 1: 编写 auth/cookies.py**

```python
"""Cookie管理模块"""
import json
import os
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta


class CookieManager:
    """Cookie存储和管理"""
    
    def __init__(self, cookie_file: str = "cookies.json"):
        self.cookie_file = Path(cookie_file)
        self._cookies: Optional[dict] = None
    
    def load(self) -> Optional[dict]:
        """从文件加载Cookie"""
        if not self.cookie_file.exists():
            return None
        
        try:
            with open(self.cookie_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._cookies = data.get("cookies", data)
            return self._cookies
        except (json.JSONDecodeError, KeyError):
            return None
    
    def save(self, cookies: dict):
        """保存Cookie到文件"""
        data = {
            "cookies": cookies,
            "saved_at": datetime.now().isoformat()
        }
        
        with open(self.cookie_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 设置文件权限
        os.chmod(self.cookie_file, 0o600)
        self._cookies = cookies
    
    def clear(self):
        """清除保存的Cookie"""
        if self.cookie_file.exists():
            self.cookie_file.unlink()
        self._cookies = None
    
    def to_aiohttp_format(self) -> dict:
        """转换为aiohttp可用的Cookie格式"""
        if not self._cookies:
            return {}
        
        # 如果是playwright格式的cookie列表
        if isinstance(self._cookies, list):
            return {c["name"]: c["value"] for c in self._cookies}
        
        return self._cookies
    
    def to_playwright_format(self) -> list[dict]:
        """转换为Playwright可用的Cookie格式"""
        if not self._cookies:
            return []
        
        # 如果已经是列表格式
        if isinstance(self._cookies, list):
            return self._cookies
        
        # 从dict格式转换
        return [
            {"name": k, "value": v, "domain": ".bigmodel.cn", "path": "/"}
            for k, v in self._cookies.items()
        ]
    
    def is_valid(self) -> bool:
        """检查Cookie是否有效（存在且不太可能过期）"""
        if not self.cookie_file.exists():
            return False
        
        try:
            with open(self.cookie_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            saved_at_str = data.get("saved_at")
            if not saved_at_str:
                return True  # 没有时间戳，假设有效
            
            saved_at = datetime.fromisoformat(saved_at_str)
            # 假设Cookie有效期7天
            if datetime.now() - saved_at > timedelta(days=7):
                return False
            
            return True
        except:
            return False


# 全局Cookie管理器
_cookie_manager: Optional[CookieManager] = None


def get_cookie_manager() -> CookieManager:
    """获取全局Cookie管理器实例"""
    global _cookie_manager
    if _cookie_manager is None:
        _cookie_manager = CookieManager()
    return _cookie_manager
```

- [ ] **Step 2: 提交代码**

```bash
git add auth/cookies.py
git commit -m "feat: 添加Cookie管理模块"
```

---

## Task 4: 登录模块

**Files:**
- Create: `auth/login.py`

- [ ] **Step 1: 编写 auth/login.py**

```python
"""登录模块 - 使用Playwright处理登录和验证码"""
import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Page, Browser
import time

from config import Config
from auth.cookies import CookieManager, get_cookie_manager
from learner.recorder import get_recorder


class LoginManager:
    """登录管理器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.cookie_manager = get_cookie_manager()
        self.recorder = get_recorder()
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._captcha_event = asyncio.Event()
        self._captcha_resolved = False
    
    async def check_login_status(self) -> bool:
        """检查当前登录状态"""
        cookies = self.cookie_manager.load()
        if not cookies:
            return False
        
        # 使用aiohttp发送测试请求验证Cookie有效性
        import aiohttp
        cookie_dict = self.cookie_manager.to_aiohttp_format()
        
        try:
            async with aiohttp.ClientSession(cookies=cookie_dict) as session:
                async with session.get(
                    self.config.zhipu.coding_url,
                    allow_redirects=False
                ) as resp:
                    # 如果被重定向到登录页，说明Cookie无效
                    if resp.status in (301, 302, 303, 307, 308):
                        location = resp.headers.get("Location", "")
                        if "login" in location.lower():
                            return False
                    return resp.status == 200
        except Exception as e:
            self.recorder.error(f"检查登录状态失败: {e}")
            return False
    
    async def login(self, headless: bool = True) -> bool:
        """执行登录流程"""
        self.recorder.info("开始登录流程...")
        
        # 先检查现有Cookie
        if await self.check_login_status():
            self.recorder.info("Cookie有效，无需重新登录")
            return True
        
        self.recorder.info("Cookie无效，启动浏览器登录...")
        
        async with async_playwright() as p:
            self._browser = await p.chromium.launch(headless=headless)
            context = await self._browser.new_context()
            self._page = await context.new_page()
            
            try:
                # 访问登录页
                self.recorder.info(f"访问登录页: {self.config.zhipu.login_url}")
                await self._page.goto(self.config.zhipu.login_url)
                await self._page.wait_for_load_state("networkidle")
                
                # 等待页面加载并填写表单
                await self._fill_login_form()
                
                # 等待登录完成或处理验证码
                success = await self._wait_for_login_complete()
                
                if success:
                    # 保存Cookie
                    cookies = await context.cookies()
                    self.cookie_manager.save(cookies)
                    self.recorder.info("登录成功，Cookie已保存")
                    return True
                else:
                    self.recorder.error("登录失败")
                    return False
                    
            except Exception as e:
                self.recorder.error(f"登录过程出错: {e}")
                return False
            finally:
                await self._browser.close()
    
    async def _fill_login_form(self):
        """填写登录表单"""
        self.recorder.info("填写登录表单...")
        
        # 等待用户名输入框出现
        await self._page.wait_for_selector('input[type="text"], input[name="username"], input[placeholder*="手机"]', timeout=10000)
        
        # 查找并填写用户名
        username_selectors = [
            'input[name="username"]',
            'input[placeholder*="手机"]',
            'input[type="text"]'
        ]
        for selector in username_selectors:
            try:
                await self._page.fill(selector, self.config.account.username)
                break
            except:
                continue
        
        # 查找并填写密码
        await asyncio.sleep(0.5)
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]'
        ]
        for selector in password_selectors:
            try:
                await self._page.fill(selector, self.config.account.password)
                break
            except:
                continue
        
        self.recorder.info("表单填写完成")
    
    async def _wait_for_login_complete(self, timeout: int = 120) -> bool:
        """等待登录完成"""
        self.recorder.info("等待登录完成...")
        
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            current_url = self._page.url
            
            # 如果已经跳转到目标页面，登录成功
            if "login" not in current_url.lower():
                self.recorder.info(f"检测到URL跳转: {current_url}")
                return True
            
            # 检查是否有验证码
            captcha_present = await self._check_captcha()
            if captcha_present:
                self.recorder.info("检测到验证码，等待手动处理...")
                self.recorder.info("请在Web界面完成验证码操作")
                # 设置等待标记，Web界面会处理
                self._captcha_event.clear()
                await self._captcha_event.wait()  # 等待Web界面触发
            
            await asyncio.sleep(1)
        
        return False
    
    async def _check_captcha(self) -> bool:
        """检查页面是否有验证码"""
        captcha_selectors = [
            '.captcha',
            '.verify',
            '#captcha',
            'iframe[src*="captcha"]',
            '.geetest',
            '.gt_slider'
        ]
        for selector in captcha_selectors:
            try:
                element = await self._page.query_selector(selector)
                if element:
                    return True
            except:
                continue
        return False
    
    def resolve_captcha(self):
        """从外部调用，表示验证码已解决"""
        self._captcha_event.set()
    
    async def get_page_screenshot(self) -> bytes:
        """获取当前页面截图，用于Web界面显示"""
        if self._page:
            return await self._page.screenshot(type="png")
        return b""


# 全局登录管理器
_login_manager: Optional[LoginManager] = None


def get_login_manager(config: Config) -> LoginManager:
    """获取全局登录管理器实例"""
    global _login_manager
    if _login_manager is None:
        _login_manager = LoginManager(config)
    return _login_manager
```

- [ ] **Step 2: 提交代码**

```bash
git add auth/login.py
git commit -m "feat: 添加登录模块"
```

---

## Task 5: 抢购模块

**Files:**
- Create: `buyer/purchase.py`

- [ ] **Step 1: 编写 buyer/purchase.py**

```python
"""抢购模块"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional
import aiohttp
from aiohttp import ClientSession

from config import Config
from auth.cookies import get_cookie_manager
from learner.recorder import get_recorder


class Buyer:
    """抢购器"""
    
    def __init__(self, config: Config):
        self.config = config
        self.cookie_manager = get_cookie_manager()
        self.recorder = get_recorder()
        self._running = False
        self._success = False
        self._status = "idle"
    
    @property
    def status(self) -> str:
        return self._status
    
    async def run(self) -> bool:
        """执行抢购流程"""
        self._running = True
        self._success = False
        self._status = "running"
        
        self.recorder.start_session()
        self.recorder.info(f"抢购开始 - 目标: {self.config.target.plan} {self.config.target.duration}")
        
        # 加载Cookie
        cookies = self.cookie_manager.load()
        if not cookies:
            self.recorder.error("没有有效的Cookie，请先登录")
            self._status = "error"
            return False
        
        cookie_dict = self.cookie_manager.to_aiohttp_format()
        
        async with aiohttp.ClientSession(cookies=cookie_dict) as session:
            # 阶段1: 预热
            await self._warmup(session)
            
            # 阶段2: 抢购
            self._status = "buying"
            result = await self._purchase_loop(session)
            
            if result:
                self._status = "success"
                self._success = True
            else:
                self._status = "failed"
        
        self.recorder.save_session()
        return self._success
    
    async def _warmup(self, session: ClientSession):
        """预热阶段 - 保持Cookie活跃"""
        self._status = "warming"
        self.recorder.info("预热阶段开始...")
        
        for i in range(3):
            try:
                start = time.time()
                async with session.get(
                    self.config.zhipu.coding_url,
                    allow_redirects=True
                ) as resp:
                    elapsed = (time.time() - start) * 1000
                    await self.recorder.record_request(
                        url=self.config.zhipu.coding_url,
                        method="GET",
                        headers=dict(session.headers),
                        params=None,
                        data=None,
                        response=resp,
                        response_time_ms=elapsed
                    )
                    
                    if resp.status == 200:
                        html = await resp.text()
                        self.recorder.info(f"预热成功，页面长度: {len(html)}")
                        # 分析页面，查找抢购相关的API
                        self._analyze_page(html)
            except Exception as e:
                self.recorder.error(f"预热请求失败: {e}")
            
            await asyncio.sleep(5)
    
    def _analyze_page(self, html: str):
        """分析页面内容，寻找抢购相关信息"""
        # 查找API端点
        import re
        
        # 查找JSON数据
        json_patterns = [
            r'"apiUrl"\s*:\s*"([^"]+)"',
            r'"purchaseUrl"\s*:\s*"([^"]+)"',
            r'/api/[^"]+',
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, html)
            for match in matches:
                self.recorder.info(f"发现可能的API: {match}")
    
    async def _purchase_loop(self, session: ClientSession) -> bool:
        """抢购循环"""
        self.recorder.info("抢购循环开始...")
        
        # 抢购持续时间：5分钟
        end_time = time.time() + 300
        request_count = 0
        consecutive_rate_limit = 0
        
        while self._running and time.time() < end_time:
            request_count += 1
            
            try:
                result = await self._try_purchase(session, request_count)
                if result:
                    return True
                
                # 检查是否被限流
                if result is None:  # 限流
                    consecutive_rate_limit += 1
                    if consecutive_rate_limit > 10:
                        # 指数退避
                        wait_time = min(2 ** (consecutive_rate_limit - 10), 30)
                        self.recorder.info(f"持续被限流，等待 {wait_time}秒")
                        await asyncio.sleep(wait_time)
                else:
                    consecutive_rate_limit = 0
                
            except Exception as e:
                self.recorder.error(f"抢购请求异常: {e}")
            
            # 请求间隔：50-100ms
            await asyncio.sleep(0.05 + (request_count % 5) * 0.01)
        
        return False
    
    async def _try_purchase(self, session: ClientSession, attempt: int) -> Optional[bool]:
        """
        尝试一次抢购
        Returns:
            True: 抢购成功
            False: 抢购失败（无名额等）
            None: 被限流
        """
        start = time.time()
        
        try:
            # 首先获取coding页面状态
            async with session.get(
                self.config.zhipu.coding_url,
                allow_redirects=False
            ) as resp:
                elapsed = (time.time() - start) * 1000
                
                record = await self.recorder.record_request(
                    url=self.config.zhipu.coding_url,
                    method="GET",
                    headers=dict(session.headers),
                    params=None,
                    data=None,
                    response=resp,
                    response_time_ms=elapsed
                )
                
                if resp.status == 429:
                    self.recorder.info(f"请求 #{attempt}: 被限流")
                    return None
                
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location", "")
                    if "login" in location.lower():
                        self.recorder.error("Cookie已失效，需要重新登录")
                        self._running = False
                        return False
                
                if resp.status != 200:
                    self.recorder.info(f"请求 #{attempt}: 状态码 {resp.status}")
                    return False
                
                html = await resp.text()
                
                # 检查页面内容
                if "售罄" in html or "已售罄" in html:
                    self.recorder.info(f"请求 #{attempt}: 已售罄")
                    return False
                
                if "访问量大" in html or "请稍后" in html:
                    self.recorder.info(f"请求 #{attempt}: 访问量大提示")
                    return None
                
                # 检查是否有购买按钮或名额
                if "立即购买" in html or "立即抢购" in html or "购买" in html:
                    self.recorder.info(f"请求 #{attempt}: 发现购买入口！尝试下单...")
                    return await self._do_purchase(session, html)
                
                # 记录页面内容用于分析
                self.recorder.info(f"请求 #{attempt}: 页面状态未知，长度: {len(html)}")
                return False
                
        except aiohttp.ClientError as e:
            self.recorder.error(f"请求异常: {e}")
            return None
    
    async def _do_purchase(self, session: ClientSession, page_html: str) -> bool:
        """执行实际购买操作"""
        self.recorder.info("尝试执行购买...")
        
        # 这里需要根据实际API来实现
        # 先记录页面内容，后续根据实际情况完善
        self.recorder.info("购买流程待完善，记录页面内容...")
        
        # 尝试查找购买API
        import re
        
        # 查找可能的购买API
        api_patterns = [
            r'"purchaseUrl"\s*:\s*"([^"]+)"',
            r'"buyUrl"\s*:\s*"([^"]+)"',
            r'/api/v\d+/[^"]*purchase[^"]*',
            r'/api/v\d+/[^"]*buy[^"]*',
        ]
        
        found_apis = []
        for pattern in api_patterns:
            matches = re.findall(pattern, page_html)
            found_apis.extend(matches)
        
        if found_apis:
            self.recorder.info(f"发现可能的购买API: {found_apis}")
            
            # 尝试调用API
            for api in found_apis[:3]:  # 尝试前3个
                if not api.startswith("http"):
                    api = f"https://open.bigmodel.cn{api}"
                
                try:
                    start = time.time()
                    async with session.post(api, json={
                        "plan": self.config.target.plan,
                        "duration": self.config.target.duration
                    }) as resp:
                        elapsed = (time.time() - start) * 1000
                        
                        await self.recorder.record_request(
                            url=api,
                            method="POST",
                            headers=dict(session.headers),
                            params=None,
                            data={"plan": self.config.target.plan, "duration": self.config.target.duration},
                            response=resp,
                            response_time_ms=elapsed
                        )
                        
                        if resp.status == 200:
                            result = await resp.json()
                            self.recorder.info(f"购买API响应: {result}")
                            
                            # 检查是否成功
                            if result.get("success") or result.get("code") == 0:
                                self.recorder.info("购买成功！")
                                return True
                except Exception as e:
                    self.recorder.error(f"调用购买API失败: {e}")
        
        return False
    
    def stop(self):
        """停止抢购"""
        self._running = False


# 全局购买器
_buyer: Optional[Buyer] = None


def get_buyer(config: Config) -> Buyer:
    """获取全局购买器实例"""
    global _buyer
    if _buyer is None:
        _buyer = Buyer(config)
    return _buyer
```

- [ ] **Step 2: 提交代码**

```bash
git add buyer/purchase.py
git commit -m "feat: 添加抢购模块"
```

---

## Task 6: Web监控界面

**Files:**
- Create: `web/app.py`
- Create: `web/templates/index.html`

- [ ] **Step 1: 编写 web/app.py**

```python
"""Web监控界面"""
import asyncio
import os
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from pathlib import Path

from config import Config
from learner.recorder import get_recorder
from buyer.purchase import get_buyer
from auth.login import get_login_manager

app = Flask(__name__)
config: Config = None


def create_app(cfg: Config) -> Flask:
    """创建Flask应用"""
    global config
    config = cfg
    return app


@app.route("/")
def index():
    """主页"""
    return render_template("index.html")


@app.route("/api/status")
def status():
    """获取当前状态"""
    buyer = get_buyer(config) if config else None
    recorder = get_recorder()
    
    return jsonify({
        "status": buyer.status if buyer else "idle",
        "time": datetime.now().isoformat(),
        "target": {
            "plan": config.target.plan,
            "duration": config.target.duration
        } if config else None
    })


@app.route("/api/logs")
def logs():
    """获取最新日志"""
    log_dir = Path("logs")
    today_log = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    
    if today_log.exists():
        with open(today_log, "r", encoding="utf-8") as f:
            content = f.read()
            lines = content.strip().split("\n")
            return jsonify({"logs": lines[-100:]})  # 最后100行
    
    return jsonify({"logs": []})


@app.route("/api/sessions")
def sessions():
    """获取历史会话列表"""
    log_dir = Path("logs")
    session_files = list(log_dir.glob("session_*.json"))
    session_files.sort(reverse=True)
    
    result = []
    for f in session_files[:10]:  # 最近10个
        result.append({
            "name": f.name,
            "time": f.stat().st_mtime
        })
    
    return jsonify({"sessions": result})


@app.route("/api/trigger", methods=["POST"])
def trigger():
    """手动触发抢购"""
    buyer = get_buyer(config)
    
    # 在后台运行抢购
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        success = loop.run_until_complete(buyer.run())
        return jsonify({
            "success": success,
            "status": buyer.status
        })
    finally:
        loop.close()


@app.route("/api/login", methods=["POST"])
def login():
    """手动触发登录"""
    login_manager = get_login_manager(config)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        success = loop.run_until_complete(login_manager.login(headless=True))
        return jsonify({
            "success": success
        })
    finally:
        loop.close()


def run_web(cfg: Config):
    """运行Web服务器"""
    create_app(cfg)
    app.run(
        host=cfg.web.host,
        port=cfg.web.port,
        debug=False,
        threaded=True
    )


if __name__ == "__main__":
    from config import get_config
    cfg = get_config()
    run_web(cfg)
```

- [ ] **Step 2: 编写 web/templates/index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>智谱 CodingPlan 抢购监控</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            margin-bottom: 30px;
            color: #00d9ff;
        }
        .panel {
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .status-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px;
            background: #0f3460;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .status-indicator {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        .status-dot.idle { background: #888; }
        .status-dot.warming { background: #ffc107; }
        .status-dot.buying { background: #00d9ff; }
        .status-dot.success { background: #00ff88; }
        .status-dot.failed { background: #ff4444; }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            margin: 5px;
            transition: all 0.3s;
        }
        .btn-primary {
            background: #00d9ff;
            color: #000;
        }
        .btn-primary:hover {
            background: #00b8d9;
        }
        .btn-danger {
            background: #ff4444;
            color: #fff;
        }
        
        .logs {
            background: #0a0a15;
            border-radius: 8px;
            padding: 15px;
            font-family: 'Monaco', 'Consolas', monospace;
            font-size: 12px;
            max-height: 400px;
            overflow-y: auto;
        }
        .logs .line {
            padding: 2px 0;
            border-bottom: 1px solid #1a1a2e;
        }
        .logs .line.error {
            color: #ff4444;
        }
        .logs .line.info {
            color: #00d9ff;
        }
        
        .actions {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }
        
        .target-info {
            background: #0f3460;
            padding: 10px 15px;
            border-radius: 8px;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>智谱 CodingPlan 抢购监控</h1>
        
        <div class="panel">
            <div class="status-bar">
                <div class="status-indicator">
                    <span class="status-dot" id="statusDot"></span>
                    <span id="statusText">空闲</span>
                    <span class="target-info" id="targetInfo"></span>
                </div>
                <div class="actions">
                    <button class="btn btn-primary" onclick="triggerLogin()">登录</button>
                    <button class="btn btn-primary" onclick="triggerPurchase()">手动抢购</button>
                </div>
            </div>
            
            <h3>实时日志</h3>
            <div class="logs" id="logs">
                <div class="line">等待日志...</div>
            </div>
        </div>
    </div>
    
    <script>
        const statusDot = document.getElementById('statusDot');
        const statusText = document.getElementById('statusText');
        const targetInfo = document.getElementById('targetInfo');
        const logsDiv = document.getElementById('logs');
        
        const statusMap = {
            'idle': { text: '空闲', class: 'idle' },
            'warming': { text: '预热中', class: 'warming' },
            'buying': { text: '抢购中', class: 'buying' },
            'success': { text: '抢购成功!', class: 'success' },
            'failed': { text: '抢购失败', class: 'failed' },
            'error': { text: '错误', class: 'failed' }
        };
        
        function updateStatus() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    const s = statusMap[data.status] || statusMap['idle'];
                    statusDot.className = 'status-dot ' + s.class;
                    statusText.textContent = s.text;
                    
                    if (data.target) {
                        targetInfo.textContent = `目标: ${data.target.plan} - ${data.target.duration}`;
                    }
                });
        }
        
        function updateLogs() {
            fetch('/api/logs')
                .then(r => r.json())
                .then(data => {
                    if (data.logs && data.logs.length > 0) {
                        logsDiv.innerHTML = data.logs.map(line => {
                            const cls = line.includes('ERROR') ? 'error' : 'info';
                            return `<div class="line ${cls}">${escapeHtml(line)}</div>`;
                        }).join('');
                        logsDiv.scrollTop = logsDiv.scrollHeight;
                    }
                });
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function triggerLogin() {
            fetch('/api/login', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    alert(data.success ? '登录成功' : '登录失败');
                });
        }
        
        function triggerPurchase() {
            if (!confirm('确定要手动触发抢购吗？')) return;
            
            fetch('/api/trigger', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    alert(data.success ? '抢购成功!' : '抢购失败');
                });
        }
        
        // 定时刷新
        setInterval(updateStatus, 2000);
        setInterval(updateLogs, 3000);
        updateStatus();
        updateLogs();
    </script>
</body>
</html>
```

- [ ] **Step 3: 提交代码**

```bash
git add web/
git commit -m "feat: 添加Web监控界面"
```

---

## Task 7: 主程序

**Files:**
- Create: `main.py`

- [ ] **Step 1: 编写 main.py**

```python
#!/usr/bin/env python3
"""智谱 CodingPlan 自动抢购 - 主入口"""
import asyncio
import signal
import sys
from datetime import datetime, time as dt_time
from typing import Optional

from config import get_config, Config
from auth.login import get_login_manager
from auth.cookies import get_cookie_manager
from buyer.purchase import get_buyer
from learner.recorder import get_recorder
import threading


def run_web_thread(config: Config):
    """在单独线程中运行Web服务器"""
    from web.app import run_web
    run_web(config)


def calculate_wait_seconds(target_time: str) -> int:
    """计算距离目标时间还有多少秒"""
    hour, minute = map(int, target_time.split(":"))
    target = dt_time(hour, minute)
    now = datetime.now().time()
    
    now_minutes = now.hour * 60 + now.minute
    target_minutes = target.hour * 60 + target.minute
    
    diff = target_minutes - now_minutes
    if diff < 0:
        diff += 24 * 60  # 加一天
    
    # 减去30秒作为预热时间
    return max(0, diff * 60 - 30)


async def main_async(config: Config):
    """异步主函数"""
    recorder = get_recorder()
    login_manager = get_login_manager(config)
    buyer = get_buyer(config)
    
    recorder.info("=== 智谱 CodingPlan 自动抢购启动 ===")
    recorder.info(f"目标: {config.target.plan} - {config.target.duration}")
    recorder.info(f"抢购时间: {config.schedule.time}")
    
    # 启动Web服务器（在单独线程）
    web_thread = threading.Thread(
        target=run_web_thread,
        args=(config,),
        daemon=True
    )
    web_thread.start()
    recorder.info(f"Web监控界面: http://{config.web.host}:{config.web.port}")
    
    # 计算等待时间
    wait_seconds = calculate_wait_seconds(config.schedule.time)
    recorder.info(f"距离抢购时间还有 {wait_seconds // 60} 分钟")
    
    # 等待到抢购时间
    if wait_seconds > 60:
        recorder.info("进入等待模式...")
        await asyncio.sleep(wait_seconds - 60)
    
    # 抢购前检查登录状态
    recorder.info("检查登录状态...")
    if not await login_manager.check_login_status():
        recorder.info("需要重新登录...")
        success = await login_manager.login(headless=True)
        if not success:
            recorder.error("登录失败，无法继续抢购")
            return False
    
    # 等待剩余时间
    remaining = calculate_wait_seconds(config.schedule.time)
    if remaining > 0:
        recorder.info(f"等待 {remaining} 秒后开始抢购...")
        await asyncio.sleep(remaining)
    
    # 执行抢购
    success = await buyer.run()
    
    if success:
        recorder.info("🎉 抢购成功!")
    else:
        recorder.info("抢购未成功，等待下次运行")
    
    return success


def main():
    """主入口"""
    try:
        config = get_config()
    except FileNotFoundError:
        print("错误: 配置文件 config.json 不存在")
        print("请复制 config.json 模板并填写账号密码")
        sys.exit(1)
    
    if not config.validate():
        print("错误: 配置文件不完整，请填写账号密码")
        sys.exit(1)
    
    # 运行主循环
    asyncio.run(main_async(config))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 提交代码**

```bash
git add main.py
git commit -m "feat: 添加主程序入口"
```

---

## Task 8: 定时任务配置

**Files:**
- Create: `zhipu-buyer.service`
- Create: `zhipu-buyer.timer`

- [ ] **Step 1: 创建 systemd service 文件**

```ini
[Unit]
Description=智谱 CodingPlan 自动抢购
After=network.target

[Service]
Type=simple
User=daifei
WorkingDirectory=/home/daifei/zhipucodingplan
ExecStart=/usr/bin/python3 /home/daifei/zhipucodingplan/main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: 创建 systemd timer 文件**

```ini
[Unit]
Description=每天9:55运行智谱抢购

[Timer]
OnCalendar=*-*-* 09:55:00 Asia/Shanghai
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: 提交配置文件**

```bash
git add zhipu-buyer.service zhipu-buyer.timer
git commit -m "feat: 添加systemd定时任务配置"
```

- [ ] **Step 4: 安装定时任务（需要root权限）**

```bash
sudo cp zhipu-buyer.service /etc/systemd/system/
sudo cp zhipu-buyer.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable zhipu-buyer.timer
sudo systemctl start zhipu-buyer.timer
```

---

## Task 9: 填写配置并测试

- [ ] **Step 1: 编辑配置文件**

请用户编辑 `config.json`，填写实际的账号密码：

```json
{
  "account": {
    "username": "实际用户名",
    "password": "实际密码"
  },
  "target": {
    "plan": "pro",
    "duration": "monthly"
  },
  "schedule": {
    "time": "10:00",
    "timezone": "Asia/Shanghai"
  },
  "web": {
    "port": 5000,
    "host": "127.0.0.1"
  },
  "zhipu": {
    "login_url": "https://open.bigmodel.cn/login",
    "coding_url": "https://open.bigmodel.cn/glm-coding"
  }
}
```

- [ ] **Step 2: 测试登录功能**

```bash
# 通过SSH隧道访问Web界面
ssh -L 5000:127.0.0.1:5000 user@your-server

# 浏览器访问 http://localhost:5000
# 点击"登录"按钮测试登录
```

- [ ] **Step 3: 手动测试抢购（可选）**

在非10点时间测试流程：
```bash
python3 main.py
```

---

## 自检清单

完成所有任务后检查：

- [ ] 所有文件已创建并提交
- [ ] config.json 已填写账号密码
- [ ] `pip install -r requirements.txt` 已执行
- [ ] `playwright install chromium` 已执行
- [ ] Web界面可通过SSH隧道访问
- [ ] systemd定时任务已安装

---

## 注意事项

1. **首次运行**：由于抢购流程未知，脚本会在学习模式下运行，记录每次请求的响应。需要多次运行来逐步完善抢购逻辑。

2. **验证码处理**：如果登录时遇到验证码，需要通过Web界面手动完成。

3. **日志查看**：每天的日志保存在 `logs/YYYY-MM-DD.log`，会话详情保存在 `logs/session_*.json`。

4. **安全**：config.json 和 cookies.json 包含敏感信息，已设置权限600，注意不要泄露。
