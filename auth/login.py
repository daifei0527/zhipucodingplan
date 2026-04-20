"""登录模块 - 使用Playwright处理登录和验证码"""
import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Page, Browser
import time

from config import Config
from auth.cookies import CookieManager, get_cookie_manager
from learner.recorder import get_recorder


class LoginManager:
    """登录管理器 - 支持多账号"""

    def __init__(self, config: Config, account=None):
        """
        初始化登录管理器

        Args:
            config: 全局配置
            account: 账号对象，如果提供则使用该账号的凭证登录
        """
        self.config = config
        self.account = account
        # 使用账号对应的Cookie管理器
        account_id = account.id if account else None
        self.cookie_manager = get_cookie_manager(account_id)
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
            # 配置浏览器参数，隐藏webdriver特征
            self._browser = await p.chromium.launch(
                headless=headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                ]
            )
            context = await self._browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='zh-CN',
            )
            self._page = await context.new_page()

            # 注入脚本隐藏webdriver特征
            await self._page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            try:
                # 访问登录页
                self.recorder.info(f"访问登录页: {self.config.zhipu.login_url}")
                await self._page.goto(self.config.zhipu.login_url, timeout=60000)
                # 等待页面基本加载完成，不等待networkidle（太慢）
                await self._page.wait_for_load_state("domcontentloaded", timeout=30000)

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

        # 获取用户名和密码（优先使用账号对象中的凭证）
        username = self.account.username if self.account else self.config.account.username
        password = self.account.password if self.account else self.config.account.password

        # 等待页面加载
        await asyncio.sleep(2)

        # 点击"账号登录"标签（默认显示的是手机号登录）
        self.recorder.info("切换到账号登录方式...")
        tabs = await self._page.query_selector_all('span, div')
        for tab in tabs:
            text = await tab.text_content() or ''
            if text.strip() == '账号登录':
                await tab.click()
                self.recorder.info("已切换到账号登录")
                break
        await asyncio.sleep(1)

        # 填写用户名
        self.recorder.info("填写用户名...")
        username_input = await self._page.query_selector('input[placeholder*="用户名"]')
        if username_input:
            await username_input.fill(username)
            self.recorder.info(f"用户名已填写")
        else:
            self.recorder.error("未找到用户名输入框")
            return

        # 填写密码
        await asyncio.sleep(0.5)
        password_elem = await self._page.query_selector('input[type="password"]')
        if password_elem:
            await password_elem.fill(password)
            self.recorder.info("密码已填写")

        self.recorder.info("表单填写完成，准备点击登录按钮...")

        # 点击登录按钮
        await asyncio.sleep(0.5)
        login_buttons = await self._page.query_selector_all('button')
        for btn in login_buttons:
            text = await btn.text_content() or ''
            if text.strip() == '登录':
                await btn.click()
                self.recorder.info("已点击登录按钮")
                return

        self.recorder.error("未找到登录按钮")

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


def get_login_manager(config: Config, account=None) -> LoginManager:
    """获取登录管理器实例

    Args:
        config: 全局配置
        account: 账号对象，如果提供则使用该账号的凭证

    Returns:
        LoginManager 实例
    """
    if account:
        # 多账号模式：每次创建新的登录管理器
        return LoginManager(config, account)

    # 单账号模式：使用全局单例
    global _login_manager
    if _login_manager is None:
        _login_manager = LoginManager(config)
    return _login_manager
