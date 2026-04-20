"""Web监控界面 - 支持多账号管理"""
import asyncio
import json
import os
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from pathlib import Path

from config import Config
from learner.recorder import get_recorder
from buyer.purchase import get_buyer
from auth.login import get_login_manager
from account import get_account_manager
from scheduler.scheduler import PurchaseScheduler
from analytics.inventory_stats import get_inventory_stats
from analytics.purchase_analyzer import get_purchase_analyzer

app = Flask(__name__)
config: Config = None

# 全局调度器
_scheduler: PurchaseScheduler = None


def get_scheduler() -> PurchaseScheduler:
    """获取调度器单例"""
    global _scheduler
    if _scheduler is None:
        _scheduler = PurchaseScheduler()
    return _scheduler


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


# === 账号管理 API ===

@app.route("/api/accounts", methods=["GET"])
def list_accounts():
    """获取账号列表"""
    manager = get_account_manager()
    accounts = [
        {
            "id": acc.id,
            "username": acc.username,
            "enabled": acc.enabled,
            "target_plans": [p.to_dict() for p in acc.target_plans],
            "auto_pay": acc.auto_pay,
            "balance": acc.balance,
            "status": acc.status,
            "created_at": acc.created_at,
            "last_run": acc.last_run
        }
        for acc in manager.list_accounts()
    ]
    return jsonify({"accounts": accounts})


@app.route("/api/accounts", methods=["POST"])
def create_account():
    """添加账号"""
    data = request.get_json()

    if not data.get("username") or not data.get("password"):
        return jsonify({"error": "用户名和密码不能为空"}), 400

    manager = get_account_manager()
    account = manager.add_account(
        username=data["username"],
        password=data["password"],
        enabled=data.get("enabled", True),
        target_plans=data.get("target_plans", []),
        auto_pay=data.get("auto_pay", True)
    )

    return jsonify({
        "success": True,
        "account": {
            "id": account.id,
            "username": account.username
        }
    })


@app.route("/api/accounts/<account_id>", methods=["PUT"])
def update_account(account_id):
    """更新账号"""
    data = request.get_json()

    manager = get_account_manager()
    account = manager.update_account(account_id, **data)

    if account:
        return jsonify({
            "success": True,
            "account": {
                "id": account.id,
                "username": account.username
            }
        })
    return jsonify({"error": "账号不存在"}), 404


@app.route("/api/accounts/<account_id>", methods=["DELETE"])
def delete_account(account_id):
    """删除账号"""
    manager = get_account_manager()
    result = manager.delete_account(account_id)

    if result:
        return jsonify({"success": True})
    return jsonify({"error": "账号不存在"}), 404


@app.route("/api/accounts/<account_id>/balance", methods=["GET"])
def get_account_balance(account_id):
    """获取账号余额"""
    manager = get_account_manager()
    account = manager.get_account(account_id)

    if not account:
        return jsonify({"error": "账号不存在"}), 404

    # TODO: 实际查询余额
    return jsonify({
        "account_id": account_id,
        "balance": account.balance
    })


@app.route("/api/accounts/<account_id>/start", methods=["POST"])
def start_account_purchase(account_id):
    """启动单账号抢购"""
    manager = get_account_manager()
    account = manager.get_account(account_id)

    if not account:
        return jsonify({"error": "账号不存在"}), 404

    scheduler = get_scheduler()
    buyer = get_buyer(config, account)

    scheduler.add_buyer(account, buyer)

    # 异步运行
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(scheduler.run_single(account_id))
        return jsonify({"success": result})
    finally:
        loop.close()


@app.route("/api/accounts/<account_id>/stop", methods=["POST"])
def stop_account_purchase(account_id):
    """停止单账号抢购"""
    scheduler = get_scheduler()
    scheduler.remove_buyer(account_id)
    return jsonify({"success": True})


@app.route("/api/purchase/start", methods=["POST"])
def start_all_purchase():
    """启动全部账号抢购"""
    manager = get_account_manager()
    accounts = manager.get_enabled_accounts()

    if not accounts:
        return jsonify({"error": "没有启用的账号"}), 400

    scheduler = get_scheduler()
    scheduler.clear_buyers()

    for account in accounts:
        buyer = get_buyer(config, account)
        scheduler.add_buyer(account, buyer)

    # 异步运行
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(scheduler.run_all())
        return jsonify({
            "success": any(results.values()),
            "results": results
        })
    finally:
        loop.close()


@app.route("/api/purchase/stop", methods=["POST"])
def stop_all_purchase():
    """停止全部抢购"""
    scheduler = get_scheduler()
    scheduler.stop()
    return jsonify({"success": True})


@app.route("/api/purchase/status", methods=["GET"])
def get_purchase_status():
    """获取抢购状态"""
    scheduler = get_scheduler()
    return jsonify({
        "status": scheduler.get_all_status(),
        "results": scheduler.get_results()
    })


@app.route("/api/history", methods=["GET"])
def get_history():
    """获取抢购历史"""
    # 从日志文件读取历史
    log_dir = Path("logs")
    session_files = list(log_dir.glob("session_*.json"))
    session_files.sort(reverse=True)

    history = []
    for f in session_files[:20]:
        try:
            with open(f) as fp:
                data = json.load(fp)
                history.append({
                    "file": f.name,
                    "time": f.stat().st_mtime,
                    "events": data.get("records", [])[:5]  # 前5条记录
                })
        except:
            pass

    return jsonify({"history": history})


# === 待支付订单 API ===

@app.route("/api/pending-orders", methods=["GET"])
def get_pending_orders():
    """获取待支付订单列表"""
    orders_file = Path("logs/pending_orders.json")
    if orders_file.exists():
        try:
            with open(orders_file, 'r', encoding='utf-8') as f:
                orders = json.load(f)
                return jsonify({"orders": orders, "count": len(orders)})
        except:
            pass
    return jsonify({"orders": [], "count": 0})


@app.route("/api/pending-orders/<int:index>", methods=["DELETE"])
def clear_pending_order(index):
    """清除待支付订单"""
    orders_file = Path("logs/pending_orders.json")
    if orders_file.exists():
        try:
            with open(orders_file, 'r', encoding='utf-8') as f:
                orders = json.load(f)
            if 0 <= index < len(orders):
                orders.pop(index)
                with open(orders_file, 'w', encoding='utf-8') as f:
                    json.dump(orders, f, ensure_ascii=False, indent=2)
                return jsonify({"success": True})
        except:
            pass
    return jsonify({"success": False}), 404


@app.route("/api/pending-orders/clear", methods=["POST"])
def clear_all_pending_orders():
    """清除所有待支付订单"""
    orders_file = Path("logs/pending_orders.json")
    if orders_file.exists():
        with open(orders_file, 'w', encoding='utf-8') as f:
            json.dump([], f)
    return jsonify({"success": True})


# === 库存统计分析 API ===

@app.route("/api/inventory-stats", methods=["GET"])
def get_inventory_statistics():
    """获取库存统计分析数据"""
    stats = get_inventory_stats()
    return jsonify(stats.get_statistics())


# === 抢购分析 API ===

@app.route("/api/purchase-analysis", methods=["GET"])
def get_purchase_analysis():
    """获取抢购分析数据和改进建议"""
    analyzer = get_purchase_analyzer()
    return jsonify(analyzer.get_analysis())


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
