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
