#!/usr/bin/env python3
"""API探索脚本 - 分析智谱Coding套餐购买API"""
import asyncio
import json
import aiohttp
from pathlib import Path

async def explore_api():
    """探索API结构"""

    # 加载Cookie
    cookie_file = Path("cookies/acc_d7532a0a.json")  # daifei0527
    if not cookie_file.exists():
        cookie_file = Path("cookies/acc_ddb67ad5.json")  # daifei

    if not cookie_file.exists():
        print("❌ 找不到Cookie文件")
        return

    with open(cookie_file, 'r') as f:
        cookie_data = json.load(f)

    # 转换为aiohttp格式
    cookies_list = cookie_data.get('cookies', cookie_data) if isinstance(cookie_data, dict) else cookie_data

    cookies = {}
    token = None
    for c in cookies_list:
        cookies[c['name']] = c['value']
        if c['name'] == 'bigmodel_token_production':
            token = c['value']

    if not token:
        print("❌ 找不到token")
        return

    print(f"✅ Token: {token[:20]}...")

    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Origin": "https://open.bigmodel.cn",
        "Referer": "https://open.bigmodel.cn/glm-coding",
    }

    results = {}

    async with aiohttp.ClientSession(cookies=cookies, headers=headers) as session:

        # 1. 获取产品列表
        print("\n=== 1. 获取产品列表 ===")
        async with session.post(
            "https://open.bigmodel.cn/api/biz/pay/batch-preview",
            json={"invitationCode": ""}
        ) as resp:
            data = await resp.json()
            results['batch_preview'] = data
            if data.get('success'):
                products = data.get('data', {}).get('productList', [])
                print(f"找到 {len(products)} 个产品")
                # 保存完整响应
                with open('logs/api_batch_preview.json', 'w') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

        # 2. 尝试获取用户账户信息
        print("\n=== 2. 获取用户信息 ===")
        user_apis = [
            ("GET", "/api/paas/user/info"),
            ("GET", "/api/paas/user/detail"),
            ("POST", "/api/biz/user/info"),
            ("GET", "/api/openai/user/info"),
        ]

        for method, api in user_apis:
            url = f"https://open.bigmodel.cn{api}"
            try:
                if method == "GET":
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            print(f"✅ {api}: {json.dumps(data, ensure_ascii=False)[:200]}")
                            results[f'user_{api.replace("/", "_")}'] = data
            except Exception as e:
                print(f"❌ {api}: {e}")

        # 3. 尝试获取产品详情（单个产品）
        print("\n=== 3. 获取产品详情 ===")
        product_ids = ["product-b8ea38", "product-2fc421", "product-fef82f"]

        for pid in product_ids:
            try:
                async with session.post(
                    "https://open.bigmodel.cn/api/biz/product/detail",
                    json={"productId": pid}
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"✅ 产品详情 {pid}: {json.dumps(data, ensure_ascii=False)[:300]}")
            except:
                pass

        # 4. 检查购买资格
        print("\n=== 4. 检查购买资格 ===")
        check_apis = [
            ("/api/biz/product/checkPurchase", {"productId": "product-b8ea38"}),
            ("/api/biz/pay/preCheck", {"productId": "product-b8ea38"}),
            ("/api/biz/order/preCreate", {"productId": "product-b8ea38"}),
        ]

        for api, body in check_apis:
            url = f"https://open.bigmodel.cn{api}"
            try:
                async with session.post(url, json=body) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        print(f"✅ {api}: {json.dumps(data, ensure_ascii=False)[:300]}")
            except:
                pass

        # 5. 保存所有结果
        with open('logs/api_explore_results.json', 'w') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print("\n✅ 探索结果已保存到 logs/api_explore_results.json")

if __name__ == "__main__":
    asyncio.run(explore_api())
