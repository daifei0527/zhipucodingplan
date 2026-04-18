"""抢购模块 - 支持直接API调用"""
import asyncio
import time
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import aiohttp
from aiohttp import ClientSession

from config import Config
from auth.cookies import get_cookie_manager
from learner.recorder import get_recorder


class Buyer:
    """抢购器 - 支持API直连和页面抢购"""

    # 产品ID映射 (从batch-preview API获取)
    PRODUCT_MAP = {
        "pro_monthly": "product-b8ea38",  # Pro 包月
        "pro_quarterly": "product-2fc421",  # Pro 包季
        "max_monthly": "product-fef82f",  # Max 包月
    }

    def __init__(self, config: Config):
        self.config = config
        self.cookie_manager = get_cookie_manager()
        self.recorder = get_recorder()
        self._running = False
        self._success = False
        self._status = "idle"
        self._auth_token: Optional[str] = None
        self._product_info: Dict[str, Any] = {}

    @property
    def status(self) -> str:
        return self._status

    async def _get_auth_token(self) -> Optional[str]:
        """从Cookie中提取Authorization Token"""
        cookies = self.cookie_manager.load()
        if isinstance(cookies, list):
            for c in cookies:
                if c.get('name') == 'bigmodel_token_production':
                    return c.get('value')
        elif isinstance(cookies, dict):
            return cookies.get('bigmodel_token_production')
        return None

    async def _fetch_product_info(self, session: ClientSession) -> bool:
        """获取产品信息和价格"""
        try:
            async with session.post(
                "https://open.bigmodel.cn/api/biz/pay/batch-preview",
                json={"invitationCode": ""}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('success'):
                        products = data.get('data', {}).get('productList', [])
                        for p in products:
                            self._product_info[p['productId']] = p
                        self.recorder.info(f"获取到 {len(products)} 个产品信息")
                        return True
        except Exception as e:
            self.recorder.error(f"获取产品信息失败: {e}")
        return False

    async def run(self) -> bool:
        """执行抢购流程"""
        self._running = True
        self._success = False
        self._status = "running"

        self.recorder.start_session()
        self.recorder.info(f"抢购开始 - 目标: {self.config.target.plan} {self.config.target.duration}")

        # 获取Authorization Token
        self._auth_token = await self._get_auth_token()
        if not self._auth_token:
            self.recorder.error("未找到Authorization Token，请先登录")
            self._status = "error"
            return False

        self.recorder.info("已获取Authorization Token")

        # 准备请求头
        headers = {
            "Authorization": self._auth_token,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": "https://open.bigmodel.cn",
            "Referer": "https://open.bigmodel.cn/glm-coding",
        }

        cookie_dict = self.cookie_manager.to_aiohttp_format()

        async with aiohttp.ClientSession(cookies=cookie_dict, headers=headers) as session:
            # 阶段1: 预热并获取产品信息
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
        """预热阶段"""
        self._status = "warming"
        self.recorder.info("预热阶段开始...")

        # 获取产品信息
        await self._fetch_product_info(session)

        # 保持会话活跃
        for i in range(2):
            try:
                start = time.time()
                async with session.get(
                    self.config.zhipu.coding_url,
                    allow_redirects=False
                ) as resp:
                    elapsed = (time.time() - start) * 1000
                    self.recorder.info(f"预热请求 {i+1}: 状态={resp.status}, 耗时={elapsed:.0f}ms")
            except Exception as e:
                self.recorder.error(f"预热请求失败: {e}")
            await asyncio.sleep(3)

    async def _purchase_loop(self, session: ClientSession) -> bool:
        """抢购循环 - 使用API直接购买"""
        self.recorder.info("抢购循环开始...")

        # 抢购持续时间：5分钟
        end_time = time.time() + 300
        request_count = 0
        consecutive_failures = 0

        while self._running and time.time() < end_time:
            request_count += 1

            try:
                result = await self._try_purchase_api(session, request_count)

                if result is True:
                    return True
                elif result is None:
                    # 被限流，等待
                    consecutive_failures += 1
                    wait_time = min(1 + consecutive_failures * 0.5, 5)
                    self.recorder.info(f"等待 {wait_time:.1f}秒后重试...")
                    await asyncio.sleep(wait_time)
                else:
                    consecutive_failures = 0

            except Exception as e:
                self.recorder.error(f"抢购请求异常: {e}")
                consecutive_failures += 1

            # 控制请求频率
            await asyncio.sleep(0.1)

        return False

    async def _try_purchase_api(self, session: ClientSession, attempt: int) -> Optional[bool]:
        """
        尝试通过API购买
        Returns:
            True: 购买成功
            False: 购买失败（售罄等）
            None: 被限流，需要等待
        """
        # 1. 先检查产品状态
        try:
            async with session.post(
                "https://open.bigmodel.cn/api/biz/pay/batch-preview",
                json={"invitationCode": ""}
            ) as resp:
                if resp.status != 200:
                    self.recorder.info(f"请求 #{attempt}: 状态码 {resp.status}")
                    return None

                data = await resp.json()
                if not data.get('success'):
                    msg = data.get('msg', '')
                    if '验证' in msg or '安全' in msg:
                        self.recorder.info(f"请求 #{attempt}: 触发安全验证")
                        return None
                    return False

                products = data.get('data', {}).get('productList', [])

                # 找到目标产品
                for p in products:
                    if not p.get('soldOut', True):
                        # 有库存！尝试购买
                        self.recorder.info(f"请求 #{attempt}: 发现库存! 产品ID: {p['productId']}")
                        return await self._do_purchase(session, p)

                # 检查售罄状态
                self.recorder.info(f"请求 #{attempt}: 售罄中...")
                return False

        except aiohttp.ClientError as e:
            self.recorder.error(f"请求异常: {e}")
            return None

    async def _do_purchase(self, session: ClientSession, product: Dict) -> bool:
        """执行实际购买"""
        product_id = product.get('productId')
        pay_amount = product.get('payAmount', 0)

        self.recorder.info(f"尝试购买: {product_id}, 金额: {pay_amount}")

        # 尝试创建订单
        order_data = {
            "productId": product_id,
            "payPrice": pay_amount,
            "num": 1,
            "isMobile": False,
            "channelCode": "WEB"
        }

        try:
            async with session.post(
                "https://open.bigmodel.cn/api/biz/product/createPreOrder",
                json=order_data
            ) as resp:
                result = await resp.json()
                self.recorder.info(f"创建订单响应: {json.dumps(result, ensure_ascii=False)[:200]}")

                if result.get('success'):
                    biz_id = result.get('data', {}).get('bizId')
                    if biz_id:
                        # 订单创建成功，尝试支付
                        return await self._pay_order(session, biz_id, pay_amount)
                else:
                    msg = result.get('msg', {})
                    if isinstance(msg, dict):
                        for key, value in msg.items():
                            self.recorder.error(f"  {key}: {value}")
                    else:
                        self.recorder.error(f"创建订单失败: {msg}")

        except Exception as e:
            self.recorder.error(f"购买异常: {e}")

        return False

    async def _pay_order(self, session: ClientSession, biz_id: str, amount: float) -> bool:
        """支付订单"""
        self.recorder.info(f"尝试支付订单: {biz_id}")

        # 支付预览
        try:
            async with session.post(
                "https://open.bigmodel.cn/api/biz/pay/preview",
                json={
                    "productId": biz_id,
                    "payMethod": "BALANCE"
                }
            ) as resp:
                result = await resp.json()
                self.recorder.info(f"支付预览响应: {json.dumps(result, ensure_ascii=False)[:200]}")

                if result.get('success'):
                    self.recorder.info("支付成功！")
                    return True
                elif '验证' in str(result.get('msg', '')):
                    self.recorder.info("支付需要安全验证，跳过...")
                    return False

        except Exception as e:
            self.recorder.error(f"支付异常: {e}")

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
