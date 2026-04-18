"""抢购监控脚本 - 10点自动抓包分析"""
import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List
from playwright.async_api import async_playwright, Page, Browser

from config import Config
from auth.cookies import get_cookie_manager
from learner.recorder import get_recorder


class PurchaseSniffer:
    """购买流程抓包分析器"""

    def __init__(self, config: Config):
        self.config = config
        self.cookie_manager = get_cookie_manager()
        self.recorder = get_recorder()
        self._browser: Browser = None
        self._page: Page = None
        self._all_requests: List[Dict] = []
        self._all_responses: List[Dict] = []
        self._product_found = False
        self._purchase_success = False

    async def run(self):
        """运行监控抢购"""
        self.recorder.info("=== 购买监控脚本启动 ===")
        self.recorder.info(f"目标时间: {self.config.schedule.time}")

        # 计算等待时间
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

    async def _purchase_loop(self):
        """抢购循环"""
        end_time = time.time() + 300  # 5分钟
        attempt = 0

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

                    for p in products:
                        if not p.get('soldOut', True):
                            self.recorder.info(f"发现库存! 产品ID: {p['productId']}")
                            self._product_found = True

                            # 尝试购买
                            success = await self._try_buy_product(p)
                            if success:
                                self._purchase_success = True
                                return

                if attempt % 10 == 0:
                    self.recorder.info(f"请求 #{attempt}: 售罄中...")

            except Exception as e:
                self.recorder.error(f"请求异常: {e}")

            await asyncio.sleep(0.1)

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
                # TODO: 支付流程
                return True

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
