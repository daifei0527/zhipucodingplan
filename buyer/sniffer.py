"""抢购监控脚本 - 10点自动抓包分析"""
import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from playwright.async_api import async_playwright, Page, Browser

from config import Config
from auth.cookies import get_cookie_manager
from learner.recorder import get_recorder


# 产品ID映射 (从实际API获取)
PRODUCT_INFO = {
    # Lite 套餐
    "product-c8a7e5": {"name": "Lite 包月", "plan": "lite", "duration": "monthly"},
    "product-d3b8f2": {"name": "Lite 包季", "plan": "lite", "duration": "quarterly"},
    "product-e4c9a1": {"name": "Lite 包年", "plan": "lite", "duration": "yearly"},
    # Pro 套餐
    "product-b8ea38": {"name": "Pro 包月", "plan": "pro", "duration": "monthly"},
    "product-2fc421": {"name": "Pro 包季", "plan": "pro", "duration": "quarterly"},
    "product-a5d7e3": {"name": "Pro 包年", "plan": "pro", "duration": "yearly"},
    # Max 套餐
    "product-fef82f": {"name": "Max 包月", "plan": "max", "duration": "monthly"},
    "product-1a2b3c": {"name": "Max 包季", "plan": "max", "duration": "quarterly"},
    "product-4d5e6f": {"name": "Max 包年", "plan": "max", "duration": "yearly"},
}


class PurchaseSniffer:
    """购买流程抓包分析器 - 支持多套餐库存监控"""

    def __init__(self, config: Config, immediate: bool = False):
        self.config = config
        self.cookie_manager = get_cookie_manager()
        self.recorder = get_recorder()
        self._browser: Browser = None
        self._page: Page = None
        self._all_requests: List[Dict] = []
        self._all_responses: List[Dict] = []
        self._product_found = False
        self._purchase_success = False
        self._product_map: Dict[str, Dict] = {}  # 动态获取的产品映射
        self._immediate = immediate  # 立即抢购模式

    async def run(self):
        """运行监控抢购"""
        self.recorder.info("=== 购买监控脚本启动 ===")
        self.recorder.info(f"目标时间: {self.config.schedule.time}")

        # 计算等待时间（如果是立即模式则跳过等待）
        if self._immediate:
            wait_seconds = 0
            self.recorder.info("立即抢购模式，跳过等待")
        else:
            wait_seconds = self._calculate_wait_seconds()
            self.recorder.info(f"距离抢购时间还有 {wait_seconds // 60} 分钟")

        async with async_playwright() as p:
            # 启动浏览器（隐藏webdriver）
            self._browser = await p.chromium.launch(
                headless=True,
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

            # 隐藏webdriver
            self._page = await context.new_page()
            await self._page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)

            # 加载Cookie
            cookies = self.cookie_manager.load()
            if cookies:
                if isinstance(cookies, list):
                    await context.add_cookies(cookies)
                self.recorder.info("已加载登录Cookie")

            # 设置请求监听
            self._setup_request_monitoring()

            # 等待到抢购时间
            if wait_seconds > 60:
                self.recorder.info("进入等待模式...")
                await asyncio.sleep(wait_seconds - 60)

            # 抢购前检查
            self.recorder.info("检查登录状态...")
            current_url = self._page.url

            # 访问Coding页面
            self.recorder.info("访问Coding页面...")
            await self._page.goto(self.config.zhipu.coding_url, timeout=60000)
            await asyncio.sleep(2)

            # 记录当前URL（检查是否被排队）
            current_url = self._page.url
            self.recorder.info(f"当前URL: {current_url}")

            if 'queue' in current_url.lower() or 'wait' in current_url.lower():
                self.recorder.error("检测到排队页面!")
                await self._page.screenshot(path="logs/queue_page.png")
                # 保存排队页面HTML
                queue_html = await self._page.content()
                with open("logs/queue_page.html", "w") as f:
                    f.write(queue_html)
                self.recorder.info("排队页面已保存到 logs/queue_page.html")

            # 等待到10点整
            remaining = self._calculate_wait_seconds()
            if remaining > 0:
                self.recorder.info(f"等待 {remaining} 秒...")
                await asyncio.sleep(remaining)

            # 开始抢购循环
            self.recorder.info("=== 开始抢购 ===")
            await self._purchase_loop()

            # 保存所有抓包数据
            self._save_capture_data()

            # 保存最终页面截图
            try:
                await self._page.screenshot(path="logs/final_page.png")
                self.recorder.info("最终页面截图已保存")
            except:
                pass

            await self._browser.close()

        return self._purchase_success

    def _calculate_wait_seconds(self) -> int:
        """计算距离目标时间的秒数"""
        hour, minute = map(int, self.config.schedule.time.split(":"))
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if target <= now:
            target += timedelta(days=1)

        diff = (target - now).total_seconds()
        return max(0, int(diff) - 30)  # 提前30秒

    def _setup_request_monitoring(self):
        """设置请求监控"""
        async def on_request(request):
            self._all_requests.append({
                'time': datetime.now().isoformat(),
                'url': request.url,
                'method': request.method,
                'headers': dict(request.headers),
                'postData': request.post_data
            })

        async def on_response(response):
            url = response.url
            status = response.status

            # 记录关键API响应
            if '/api/biz/' in url or 'pay' in url.lower() or 'product' in url.lower():
                try:
                    body = await response.text()
                    self._all_responses.append({
                        'time': datetime.now().isoformat(),
                        'url': url,
                        'status': status,
                        'headers': dict(response.headers),
                        'body': body[:5000]  # 限制大小
                    })

                    # 实时记录重要响应
                    if 'batch-preview' in url or 'createPreOrder' in url or 'pay' in url:
                        self.recorder.info(f"[API] {status} {url[:80]}")
                except:
                    pass

        self._page.on('request', on_request)
        self._page.on('response', on_response)

    def _get_product_display_name(self, product_id: str, product_data: Dict = None) -> str:
        """获取产品的显示名称"""
        # 先从预定义映射查找
        if product_id in PRODUCT_INFO:
            return PRODUCT_INFO[product_id]["name"]

        # 从动态获取的数据查找
        if product_id in self._product_map:
            info = self._product_map[product_id]
            plan = info.get('plan', 'unknown')
            duration = info.get('duration', 'unknown')
            return f"{plan.upper()} {self._duration_to_chinese(duration)}"

        # 从API返回的数据推断
        if product_data:
            name = product_data.get('productName', '')
            if name:
                return name

        return product_id

    def _duration_to_chinese(self, duration: str) -> str:
        """将时长转换为中文"""
        mapping = {
            'monthly': '包月',
            'quarterly': '包季',
            'yearly': '包年'
        }
        return mapping.get(duration, duration)

    def _analyze_product_list(self, products: List[Dict]) -> Dict[str, Any]:
        """分析产品列表，返回库存状态和推荐购买"""
        analysis = {
            'all_products': [],
            'available': [],
            'sold_out': [],
            'recommendation': None
        }

        # 套餐优先级 (Max > Pro > Lite)
        plan_priority = {'max': 3, 'pro': 2, 'lite': 1}
        # 时长优先级 (包年 > 包季 > 包月) - 包年通常库存更多
        duration_priority = {'yearly': 3, 'quarterly': 2, 'monthly': 1}

        for p in products:
            product_id = p.get('productId', '')
            sold_out = p.get('soldOut', True)
            pay_amount = p.get('payAmount', 0)
            original_price = p.get('originalPrice', 0)
            product_name = p.get('productName', '')

            # 尝试识别产品类型
            plan = 'unknown'
            duration = 'unknown'

            # 从产品名推断
            name_lower = product_name.lower()
            if 'max' in name_lower:
                plan = 'max'
            elif 'pro' in name_lower:
                plan = 'pro'
            elif 'lite' in name_lower:
                plan = 'lite'

            if '年' in product_name or 'yearly' in name_lower:
                duration = 'yearly'
            elif '季' in product_name or 'quarterly' in name_lower:
                duration = 'quarterly'
            elif '月' in product_name or 'monthly' in name_lower:
                duration = 'monthly'

            # 保存到动态映射
            self._product_map[product_id] = {
                'plan': plan,
                'duration': duration,
                'name': product_name,
                'payAmount': pay_amount
            }

            display_name = self._get_product_display_name(product_id, p)

            product_info = {
                'id': product_id,
                'name': display_name,
                'plan': plan,
                'duration': duration,
                'price': pay_amount,
                'original_price': original_price,
                'sold_out': sold_out
            }

            analysis['all_products'].append(product_info)

            if sold_out:
                analysis['sold_out'].append(product_info)
            else:
                analysis['available'].append(product_info)

        # 对可用产品排序，选择最优
        if analysis['available']:
            # 按套餐优先级和时长优先级排序
            analysis['available'].sort(
                key=lambda x: (
                    plan_priority.get(x['plan'], 0),
                    duration_priority.get(x['duration'], 0),
                    -x['price']  # 价格高的可能更值得
                ),
                reverse=True
            )
            analysis['recommendation'] = analysis['available'][0]

        return analysis

    async def _purchase_loop(self):
        """抢购循环 - 监控所有套餐库存"""
        end_time = time.time() + 300  # 5分钟
        attempt = 0
        last_status_log = 0

        while time.time() < end_time and not self._purchase_success:
            attempt += 1

            try:
                # 检查产品状态
                result = await self._page.evaluate('''async () => {
                    const resp = await fetch('/api/biz/pay/batch-preview', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({invitationCode: ''})
                    });
                    return await resp.json();
                }''')

                if result.get('success'):
                    products = result.get('data', {}).get('productList', [])

                    # 分析所有产品
                    analysis = self._analyze_product_list(products)

                    # 每5秒输出一次完整状态
                    current_time = time.time()
                    if current_time - last_status_log >= 5:
                        self._log_inventory_status(analysis)
                        last_status_log = current_time

                    # 如果有库存，尝试购买
                    if analysis['available']:
                        # 选择推荐产品
                        recommended = analysis['recommendation']
                        self.recorder.info(f"🎯 推荐购买: {recommended['name']} (ID: {recommended['id']}, 价格: {recommended['price']})")

                        # 找到对应的原始产品数据
                        for p in products:
                            if p.get('productId') == recommended['id']:
                                self._product_found = True
                                success = await self._try_buy_product(p)
                                if success:
                                    self._purchase_success = True
                                    return
                                break
                else:
                    if attempt % 20 == 0:
                        self.recorder.info(f"请求 #{attempt}: API返回失败 - {result.get('msg', 'unknown')}")

            except Exception as e:
                self.recorder.error(f"请求异常: {e}")

            await asyncio.sleep(0.1)

    def _log_inventory_status(self, analysis: Dict):
        """输出库存状态日志"""
        self.recorder.info("=" * 50)
        self.recorder.info("📦 库存状态监控:")

        # 按套餐分组显示
        plans = {'lite': [], 'pro': [], 'max': [], 'unknown': []}
        for p in analysis['all_products']:
            plan = p.get('plan', 'unknown')
            if plan in plans:
                plans[plan].append(p)
            else:
                plans['unknown'].append(p)

        # 显示各套餐库存
        for plan_name in ['lite', 'pro', 'max']:
            plan_products = plans[plan_name]
            if plan_products:
                self.recorder.info(f"  [{plan_name.upper()}]")
                for p in plan_products:
                    status = "✅ 有库存" if not p['sold_out'] else "❌ 售罄"
                    self.recorder.info(f"    {p['name']}: {status} (¥{p['price']})")

        # 汇总
        total = len(analysis['all_products'])
        available = len(analysis['available'])
        self.recorder.info(f"  总计: {total}个产品, {available}个有库存")

        if analysis['recommendation']:
            r = analysis['recommendation']
            self.recorder.info(f"  💡 推荐: {r['name']} (¥{r['price']})")
        self.recorder.info("=" * 50)

    async def _try_buy_product(self, product: dict) -> bool:
        """尝试购买产品"""
        product_id = product['productId']
        pay_amount = product.get('payAmount', 0)

        self.recorder.info(f"尝试购买: {product_id}, 金额: {pay_amount}")

        # 使用页面内fetch保持Cookie
        result = await self._page.evaluate('''async (data) => {
            const {productId, payAmount} = data;

            // 创建订单
            const orderResp = await fetch('/api/biz/product/createPreOrder', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    productId: productId,
                    payPrice: payAmount,
                    num: 1,
                    isMobile: false,
                    channelCode: 'WEB'
                })
            });
            const orderResult = await orderResp.json();

            return orderResult;
        }''', {'productId': product_id, 'payAmount': pay_amount})

        self.recorder.info(f"订单响应: {json.dumps(result, ensure_ascii=False)[:300]}")

        if result.get('success'):
            biz_id = result.get('data', {}).get('bizId')
            if biz_id:
                self.recorder.info(f"订单创建成功! bizId: {biz_id}")
                # 尝试支付
                pay_success = await self._pay_order(biz_id, pay_amount)
                if pay_success:
                    return True

        return False

    async def _pay_order(self, biz_id: str, amount: float) -> bool:
        """支付订单"""
        self.recorder.info(f"尝试支付订单: {biz_id}")

        result = await self._page.evaluate('''async (data) => {
            const {bizId, amount} = data;

            // 支付预览
            const payResp = await fetch('/api/biz/pay/preview', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    productId: bizId,
                    payMethod: 'BALANCE'
                })
            });
            return await payResp.json();
        }''', {'bizId': biz_id, 'amount': amount})

        self.recorder.info(f"支付响应: {json.dumps(result, ensure_ascii=False)[:300]}")

        if result.get('success'):
            self.recorder.info("🎉 支付成功！")
            return True
        else:
            self.recorder.error(f"支付失败: {result.get('msg', 'unknown')}")

        return False

    def _save_capture_data(self):
        """保存抓包数据"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # 保存请求数据
        requests_file = Path(f"logs/requests_{timestamp}.json")
        with open(requests_file, "w") as f:
            json.dump({
                'total': len(self._all_requests),
                'requests': self._all_requests
            }, f, indent=2, ensure_ascii=False)
        self.recorder.info(f"请求日志已保存: {requests_file}")

        # 保存响应数据
        responses_file = Path(f"logs/responses_{timestamp}.json")
        with open(responses_file, "w") as f:
            json.dump({
                'total': len(self._all_responses),
                'responses': self._all_responses
            }, f, indent=2, ensure_ascii=False)
        self.recorder.info(f"响应日志已保存: {responses_file}")


# 独立运行入口
if __name__ == "__main__":
    from config import get_config

    config = get_config()
    sniffer = PurchaseSniffer(config)
    asyncio.run(sniffer.run())
