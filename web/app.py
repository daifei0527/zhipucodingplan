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
