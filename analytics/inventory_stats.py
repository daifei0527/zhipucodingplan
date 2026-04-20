"""库存统计分析模块 - 记录套餐库存时长，分析抢购成功率"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import threading


@dataclass
class InventoryRecord:
    """单次库存记录"""
    timestamp: str
    product_id: str
    product_name: str
    plan: str  # pro, max, lite
    duration: str  # monthly, quarterly, yearly
    available: bool  # 是否有库存
    price: float


@dataclass
class InventorySession:
    """一次抢购会话的库存统计"""
    session_id: str
    start_time: str
    end_time: str
    records: List[Dict]
    # 各套餐的库存出现总时长(秒)
    inventory_duration: Dict[str, float]
    # 各套餐的库存出现次数
    inventory_count: Dict[str, int]


class InventoryStatsManager:
    """库存统计管理器"""

    # 套餐组合键
    PLAN_KEYS = [
        "max_monthly", "max_quarterly", "max_yearly",
        "pro_monthly", "pro_quarterly", "pro_yearly",
        "lite_monthly", "lite_quarterly", "lite_yearly"
    ]

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.data_file = Path("logs/inventory_stats.json")
        self.data_file.parent.mkdir(parents=True, exist_ok=True)

        # 当前会话数据
        self._current_session: Optional[InventorySession] = None
        self._session_start: Optional[datetime] = None
        # 记录每个套餐上次有库存的时间点
        self._last_available_time: Dict[str, datetime] = {}

    def start_session(self):
        """开始一次抢购会话记录"""
        self._session_start = datetime.now()
        self._current_session = InventorySession(
            session_id=self._session_start.strftime("%Y%m%d_%H%M%S"),
            start_time=self._session_start.isoformat(),
            end_time="",
            records=[],
            inventory_duration={k: 0.0 for k in self.PLAN_KEYS},
            inventory_count={k: 0 for k in self.PLAN_KEYS}
        )
        self._last_available_time = {}

    def record_inventory(self, products: List[Dict]):
        """记录当前库存状态

        Args:
            products: 产品列表，每个包含 productId, productName, soldOut, payAmount 等
        """
        if not self._current_session:
            return

        now = datetime.now()
        timestamp = now.isoformat()

        for p in products:
            product_id = p.get('productId', '')
            product_name = p.get('productName', '')
            sold_out = p.get('soldOut', True)
            pay_amount = p.get('payAmount', 0)

            # 解析套餐类型和时长
            plan, duration = self._parse_product_info(product_name, product_id)
            plan_key = f"{plan}_{duration}"

            if plan_key not in self.PLAN_KEYS:
                continue

            available = not sold_out

            # 记录状态变化
            record = {
                "timestamp": timestamp,
                "product_id": product_id,
                "product_name": product_name,
                "plan": plan,
                "duration": duration,
                "available": available,
                "price": pay_amount
            }
            self._current_session.records.append(record)

            # 计算库存持续时长
            if available:
                # 有库存
                if plan_key not in self._last_available_time:
                    # 首次出现库存
                    self._last_available_time[plan_key] = now
                    self._current_session.inventory_count[plan_key] += 1
                # 否则持续有库存，时长会在end_session时计算
            else:
                # 无库存，结算之前的持续时长
                if plan_key in self._last_available_time:
                    duration_seconds = (now - self._last_available_time[plan_key]).total_seconds()
                    self._current_session.inventory_duration[plan_key] += duration_seconds
                    del self._last_available_time[plan_key]

    def end_session(self):
        """结束当前会话，保存数据"""
        if not self._current_session:
            return

        now = datetime.now()
        self._current_session.end_time = now.isoformat()

        # 结算所有仍有库存的套餐时长
        for plan_key, last_time in self._last_available_time.items():
            duration_seconds = (now - last_time).total_seconds()
            self._current_session.inventory_duration[plan_key] += duration_seconds

        self._last_available_time = {}

        # 保存到文件
        self._save_session(self._current_session)

        self._current_session = None
        self._session_start = None

    def _parse_product_info(self, product_name: str, product_id: str) -> tuple:
        """解析产品信息，返回 (plan, duration)"""
        name_lower = product_name.lower()

        # 解析套餐类型
        if 'max' in name_lower:
            plan = 'max'
        elif 'pro' in name_lower:
            plan = 'pro'
        elif 'lite' in name_lower:
            plan = 'lite'
        else:
            plan = 'unknown'

        # 解析时长
        if '年' in product_name or 'yearly' in name_lower:
            duration = 'yearly'
        elif '季' in product_name or 'quarterly' in name_lower:
            duration = 'quarterly'
        elif '月' in product_name or 'monthly' in name_lower:
            duration = 'monthly'
        else:
            duration = 'unknown'

        return plan, duration

    def _save_session(self, session: InventorySession):
        """保存会话数据到文件"""
        # 读取现有数据
        all_sessions = []
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    all_sessions = json.load(f)
            except:
                all_sessions = []

        # 添加新会话
        all_sessions.append(asdict(session))

        # 只保留最近100次会话
        if len(all_sessions) > 100:
            all_sessions = all_sessions[-100:]

        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(all_sessions, f, ensure_ascii=False, indent=2)

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计分析数据

        Returns:
            {
                "has_data": bool,
                "total_sessions": int,
                "plans": {
                    "max_monthly": {
                        "avg_duration": float,  # 平均库存持续时长(秒)
                        "appearance_rate": float,  # 库存出现率(0-1)
                        "total_appearances": int,  # 总出现次数
                        "success_score": float  # 成功率评分(0-100)
                    },
                    ...
                },
                "ranking": [("max_yearly", 95.5), ...]  # 按成功率排序
            }
        """
        if not self.data_file.exists():
            return {"has_data": False}

        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                all_sessions = json.load(f)
        except:
            return {"has_data": False}

        if not all_sessions:
            return {"has_data": False}

        # 统计各套餐数据
        plan_stats = {k: {
            "total_duration": 0.0,
            "appearance_count": 0,
            "session_count": 0  # 有库存出现的会话数
        } for k in self.PLAN_KEYS}

        total_sessions = len(all_sessions)

        for session in all_sessions:
            inventory_duration = session.get('inventory_duration', {})
            inventory_count = session.get('inventory_count', {})

            for plan_key in self.PLAN_KEYS:
                duration = inventory_duration.get(plan_key, 0)
                count = inventory_count.get(plan_key, 0)

                if duration > 0:
                    plan_stats[plan_key]["total_duration"] += duration
                    plan_stats[plan_key]["session_count"] += 1

                plan_stats[plan_key]["appearance_count"] += count

        # 计算成功率评分
        result_plans = {}
        for plan_key in self.PLAN_KEYS:
            stats = plan_stats[plan_key]

            if stats["session_count"] == 0:
                continue

            # 平均库存持续时长
            avg_duration = stats["total_duration"] / max(1, stats["session_count"])

            # 库存出现率
            appearance_rate = stats["session_count"] / total_sessions

            # 成功率评分 (综合考虑出现率和持续时长)
            # 时长权重：60秒以上得满分，否则按比例
            duration_score = min(100, avg_duration / 60 * 100)
            # 出现率权重：直接转为百分比
            appearance_score = appearance_rate * 100

            # 综合评分：出现率占40%，时长占60%
            success_score = appearance_score * 0.4 + duration_score * 0.6

            result_plans[plan_key] = {
                "avg_duration": round(avg_duration, 1),
                "appearance_rate": round(appearance_rate, 3),
                "total_appearances": stats["appearance_count"],
                "success_score": round(success_score, 1)
            }

        # 按成功率排序
        ranking = sorted(
            result_plans.items(),
            key=lambda x: x[1]["success_score"],
            reverse=True
        )

        return {
            "has_data": True,
            "total_sessions": total_sessions,
            "plans": result_plans,
            "ranking": ranking
        }


# 全局单例
_stats_manager: Optional[InventoryStatsManager] = None


def get_inventory_stats() -> InventoryStatsManager:
    """获取库存统计管理器"""
    global _stats_manager
    if _stats_manager is None:
        _stats_manager = InventoryStatsManager()
    return _stats_manager
