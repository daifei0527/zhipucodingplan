"""抢购模块 - 支持直接API调用和多账号"""
import asyncio
import time
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import aiohttp
from aiohttp import ClientSession

from config import Config
from auth.cookies import get_cookie_manager
from learner.recorder import get_recorder


class Buyer:
    """抢购器 - 支持API直连和页面抢购，支持多账号"""

    # 产品ID映射 (从batch-preview API获取)
    PRODUCT_MAP = {
        "pro_monthly": "product-b8ea38",  # Pro 包月
        "pro_quarterly": "product-2fc421",  # Pro 包季
        "max_monthly": "product-fef82f",  # Max 包月
    }

    def __init__(self, config: Config, account=None):
        """
        Args:
            config: 全局配置
            account: 账号配置 (Account 模型)，如果为 None 则使用 config 中的账号
        """
        self.config = config
        self.account = account
        self.cookie_manager = get_cookie_manager()
        self.recorder = get_recorder()
        self._running = False
        self._success = False
        self._status = "idle"
        self._auth_token: Optional[str] = None
        self._product_info: Dict[str, Any] = {}

        # 如果提供了账号，使用账号的用户名作为日志标识
        self._log_prefix = f"[{account.username}]" if account else ""

    @property
    def status(self) -> str:
        return self._status

    def _log(self, message: str, level: str = "info"):
        """带账号标识的日志"""
        prefixed_message = f"{self._log_prefix} {message}"
        if level == "error":
            self.recorder.error(prefixed_message)
        else:
            self.recorder.info(prefixed_message)

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
                        self._log(f"获取到 {len(products)} 个产品信息")
                        return True
        except Exception as e:
            self._log(f"获取产品信息失败: {e}", level="error")
        return False

    async def run(self) -> bool:
        """执行抢购流程"""
        self._running = True
        self._success = False
        self._status = "running"

        self.recorder.start_session()

        # 获取目标配置
        if self.account and self.account.target_plans:
            target_desc = f"{self.account.target_plans[0].plan}"
            if len(self.account.target_plans) > 1:
                target_desc += f" (备选: {[p.plan for p in self.account.target_plans[1:]]})"
        else:
            target_desc = f"{self.config.target.plan} {self.config.target.duration}"

        self._log(f"抢购开始 - 目标: {target_desc}")

        # 获取Authorization Token
        self._auth_token = await self._get_auth_token()
        if not self._auth_token:
            self._log("未找到Authorization Token，请先登录", level="error")
            self._status = "error"
            return False

        self._log("已获取Authorization Token")

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
        self._log("预热阶段开始...")

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
                    self._log(f"预热请求 {i+1}: 状态={resp.status}, 耗时={elapsed:.0f}ms")
            except Exception as e:
                self._log(f"预热请求失败: {e}", level="error")
            await asyncio.sleep(3)

    async def _purchase_loop(self, session: ClientSession) -> bool:
        """抢购循环 - 使用API直接购买"""
        self._log("抢购循环开始...")

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
                    self._log(f"等待 {wait_time:.1f}秒后重试...")
                    await asyncio.sleep(wait_time)
                else:
                    consecutive_failures = 0

            except Exception as e:
                self._log(f"抢购请求异常: {e}", level="error")
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
                    self._log(f"请求 #{attempt}: 状态码 {resp.status}")
                    return None

                data = await resp.json()
                if not data.get('success'):
                    msg = data.get('msg', '')
                    if '验证' in msg or '安全' in msg:
                        self._log(f"请求 #{attempt}: 触发安全验证")
                        return None
                    return False

                products = data.get('data', {}).get('productList', [])

                # 根据目标套餐优先级查找产品
                target_product = await self._find_target_product(products)

                if target_product:
                    self._log(f"请求 #{attempt}: 发现库存! 产品ID: {target_product['productId']}")
                    return await self._do_purchase(session, target_product)

                # 检查售罄状态
                self._log(f"请求 #{attempt}: 售罄中...")
                return False

        except aiohttp.ClientError as e:
            self._log(f"请求异常: {e}", level="error")
            return None

    async def _find_target_product(self, products: List[Dict]) -> Optional[Dict]:
        """根据目标套餐优先级查找可用产品"""
        if not self.account or not self.account.target_plans:
            # 没有配置目标套餐，返回第一个有库存的
            for p in products:
                if not p.get('soldOut', True):
                    return p
            return None

        # 按优先级排序目标套餐
        sorted_plans = sorted(self.account.target_plans, key=lambda x: x.priority)

        for target in sorted_plans:
            for p in products:
                if p.get('soldOut', True):
                    continue

                # 匹配套餐类型和时长
                product_name = p.get('productName', '').lower()
                plan_match = target.plan in product_name
                duration_match = self._duration_match(target.duration, product_name)

                if plan_match and duration_match:
                    self._log(f"匹配目标套餐: {target.plan} {target.duration}")
                    return p

        # 目标套餐都没有库存，尝试任意有库存的
        for p in products:
            if not p.get('soldOut', True):
                self._log("目标套餐无库存，选择其他可用套餐")
                return p

        return None

    def _duration_match(self, target_duration: str, product_name: str) -> bool:
        """匹配时长"""
        duration_keywords = {
            'monthly': ['月', 'monthly', 'month'],
            'quarterly': ['季', 'quarterly', 'quarter'],
            'yearly': ['年', 'yearly', 'year']
        }
        keywords = duration_keywords.get(target_duration, [])
        return any(kw in product_name.lower() for kw in keywords)

    async def _do_purchase(self, session: ClientSession, product: Dict) -> bool:
        """执行实际购买"""
        product_id = product.get('productId')
        pay_amount = product.get('payAmount', 0)
        original_amount = product.get('originalAmount', pay_amount)

        self._log(f"尝试购买: {product_id}, 原价: {original_amount}, 实付: {pay_amount}")

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
                self._log(f"创建订单响应: {json.dumps(result, ensure_ascii=False)[:500]}")

                if result.get('success'):
                    biz_id = result.get('data', {}).get('bizId')
                    if biz_id:
                        self._log(f"🎉 订单创建成功! 订单号: {biz_id}")

                        # 判断是否自动支付
                        if self.account and self.account.auto_pay:
                            # 获取余额
                            balance = await self._get_balance(session)

                            if balance is not None and balance >= pay_amount:
                                self._log(f"余额 {balance} >= 价格 {pay_amount}，尝试自动支付")
                                pay_success = await self._pay_order(session, biz_id, pay_amount)
                                if pay_success:
                                    return True
                                self._log("自动支付失败，请手动支付")
                            else:
                                self._log(f"余额不足 ({balance} < {pay_amount})，请手动支付")
                                self._log(f"支付链接: https://open.bigmodel.cn/console/overview")
                        else:
                            self._log("自动支付已禁用，请手动支付")
                            self._log(f"支付链接: https://open.bigmodel.cn/console/overview")

                        return True  # 订单创建成功也算成功
                else:
                    msg = result.get('msg', '')
                    self._log(f"创建订单失败: {msg}", level="error")
                    # 分析错误原因
                    if '类型' in str(msg):
                        self._log("可能原因: 账户已有相同套餐或账户类型不匹配", level="error")
                    elif '余额' in str(msg) or '余额不足' in str(msg):
                        self._log("可能原因: 账户余额不足，请先充值", level="error")

        except Exception as e:
            self._log(f"购买异常: {e}", level="error")

        return False

    async def _get_balance(self, session: ClientSession) -> Optional[float]:
        """获取账户余额"""
        try:
            async with session.post(
                "https://open.bigmodel.cn/api/biz/pay/batch-preview",
                json={"invitationCode": ""}
            ) as resp:
                data = await resp.json()
                if data.get('success'):
                    # 余额通常在 data.data.balance 或类似字段
                    balance = data.get('data', {}).get('balance', 0)
                    return balance
        except Exception as e:
            self._log(f"获取余额失败: {e}")
        return None

    async def _pay_order(self, session: ClientSession, biz_id: str, amount: float) -> bool:
        """支付订单"""
        self._log(f"尝试支付订单: {biz_id}")

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
                self._log(f"支付预览响应: {json.dumps(result, ensure_ascii=False)[:200]}")

                if result.get('success'):
                    self._log("支付成功！")
                    return True
                elif '验证' in str(result.get('msg', '')):
                    self._log("支付需要安全验证，跳过...")
                    return False

        except Exception as e:
            self._log(f"支付异常: {e}", level="error")

        return False

    def stop(self):
        """停止抢购"""
        self._running = False


# 全局购买器
_buyer: Optional[Buyer] = None


def get_buyer(config: Config, account=None) -> Buyer:
    """获取购买器实例

    Args:
        config: 全局配置
        account: 可选的账号配置，如果提供则创建新的 Buyer 实例
    """
    if account:
        # 多账号模式：每次创建新的 Buyer
        return Buyer(config, account)

    # 单账号模式：使用全局单例
    global _buyer
    if _buyer is None:
        _buyer = Buyer(config)
    return _buyer
