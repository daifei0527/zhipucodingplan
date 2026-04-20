"""抢购分析模块 - 记录抢购详情，分析失败原因，生成改进建议"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
import threading


@dataclass
class RequestRecord:
    """单次请求记录"""
    timestamp: str
    attempt: int
    success: bool
    status_code: int = 0
    response_time_ms: float = 0
    error_type: str = ""  # network, rate_limit, captcha, sold_out, auth, other
    error_message: str = ""
    has_inventory: bool = False
    product_id: str = ""


@dataclass
class StageTiming:
    """阶段耗时记录"""
    stage_name: str
    start_time: str
    end_time: str
    duration_ms: float


@dataclass
class PurchaseSessionRecord:
    """一次抢购会话的完整记录"""
    session_id: str
    account_id: str
    account_username: str
    start_time: str
    end_time: str = ""
    success: bool = False

    # 目标套餐
    target_plans: List[Dict] = field(default_factory=list)

    # 最终抢到的套餐
    purchased_plan: str = ""
    purchased_product_id: str = ""

    # 请求统计
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rate_limited_requests: int = 0
    captcha_triggered: int = 0

    # 耗时统计
    total_duration_ms: float = 0
    avg_response_time_ms: float = 0
    min_response_time_ms: float = 0
    max_response_time_ms: float = 0

    # 库存相关
    inventory_appeared: bool = False
    inventory_appear_count: int = 0
    first_inventory_time: str = ""
    inventory_total_duration_sec: float = 0

    # 认证相关
    auth_valid: bool = True
    cookie_expired: bool = False

    # 详细记录
    request_records: List[Dict] = field(default_factory=list)
    stage_timings: List[Dict] = field(default_factory=list)

    # 错误汇总
    error_summary: Dict[str, int] = field(default_factory=dict)


class PurchaseAnalyzer:
    """抢购分析器"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        self.data_file = Path("logs/purchase_analysis.json")
        self.data_file.parent.mkdir(parents=True, exist_ok=True)

        # 当前会话记录
        self._current_session: Optional[PurchaseSessionRecord] = None
        self._start_time: Optional[datetime] = None
        self._response_times: List[float] = []

    def start_session(self, account_id: str, account_username: str, target_plans: List[Dict]):
        """开始一次抢购会话"""
        self._start_time = datetime.now()
        self._current_session = PurchaseSessionRecord(
            session_id=self._start_time.strftime("%Y%m%d_%H%M%S") + f"_{account_id[:8]}",
            account_id=account_id,
            account_username=account_username,
            start_time=self._start_time.isoformat(),
            target_plans=target_plans
        )
        self._response_times = []

    def record_request(self, attempt: int, success: bool, status_code: int = 0,
                       response_time_ms: float = 0, error_type: str = "",
                       error_message: str = "", has_inventory: bool = False,
                       product_id: str = ""):
        """记录一次请求"""
        if not self._current_session:
            return

        record = RequestRecord(
            timestamp=datetime.now().isoformat(),
            attempt=attempt,
            success=success,
            status_code=status_code,
            response_time_ms=response_time_ms,
            error_type=error_type,
            error_message=error_message,
            has_inventory=has_inventory,
            product_id=product_id
        )

        self._current_session.request_records.append(asdict(record))
        self._current_session.total_requests += 1

        if success:
            self._current_session.successful_requests += 1
        else:
            self._current_session.failed_requests += 1

        if error_type == "rate_limit":
            self._current_session.rate_limited_requests += 1
        elif error_type == "captcha":
            self._current_session.captcha_triggered += 1

        if response_time_ms > 0:
            self._response_times.append(response_time_ms)

        # 更新错误汇总
        if error_type:
            self._current_session.error_summary[error_type] = \
                self._current_session.error_summary.get(error_type, 0) + 1

        # 记录库存出现
        if has_inventory:
            if not self._current_session.inventory_appeared:
                self._current_session.inventory_appeared = True
                self._current_session.first_inventory_time = record.timestamp
            self._current_session.inventory_appear_count += 1

    def record_stage(self, stage_name: str, start_time: datetime, end_time: datetime):
        """记录阶段耗时"""
        if not self._current_session:
            return

        timing = StageTiming(
            stage_name=stage_name,
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            duration_ms=(end_time - start_time).total_seconds() * 1000
        )
        self._current_session.stage_timings.append(asdict(timing))

    def set_auth_status(self, valid: bool, cookie_expired: bool = False):
        """设置认证状态"""
        if self._current_session:
            self._current_session.auth_valid = valid
            self._current_session.cookie_expired = cookie_expired

    def set_inventory_duration(self, duration_sec: float):
        """设置库存持续时长"""
        if self._current_session:
            self._current_session.inventory_total_duration_sec = duration_sec

    def end_session(self, success: bool, purchased_plan: str = "", purchased_product_id: str = ""):
        """结束抢购会话"""
        if not self._current_session:
            return

        self._current_session.end_time = datetime.now().isoformat()
        self._current_session.success = success
        self._current_session.purchased_plan = purchased_plan
        self._current_session.purchased_product_id = purchased_product_id

        # 计算总耗时
        if self._start_time:
            self._current_session.total_duration_ms = \
                (datetime.now() - self._start_time).total_seconds() * 1000

        # 计算响应时间统计
        if self._response_times:
            self._current_session.avg_response_time_ms = \
                sum(self._response_times) / len(self._response_times)
            self._current_session.min_response_time_ms = min(self._response_times)
            self._current_session.max_response_time_ms = max(self._response_times)

        # 保存到文件
        self._save_session(self._current_session)

        self._current_session = None
        self._start_time = None

    def _save_session(self, session: PurchaseSessionRecord):
        """保存会话记录"""
        all_sessions = []
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    all_sessions = json.load(f)
            except:
                all_sessions = []

        all_sessions.append(asdict(session))

        # 保留最近50次会话
        if len(all_sessions) > 50:
            all_sessions = all_sessions[-50:]

        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(all_sessions, f, ensure_ascii=False, indent=2)

    def get_analysis(self) -> Dict[str, Any]:
        """获取分析结果和改进建议"""
        if not self.data_file.exists():
            return {"has_data": False, "suggestions": []}

        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                sessions = json.load(f)
        except:
            return {"has_data": False, "suggestions": []}

        if not sessions:
            return {"has_data": False, "suggestions": []}

        # 统计分析
        total = len(sessions)
        success_count = sum(1 for s in sessions if s.get('success'))
        success_rate = success_count / total if total > 0 else 0

        # 错误统计
        error_stats: Dict[str, int] = {}
        for s in sessions:
            for error_type, count in s.get('error_summary', {}).items():
                error_stats[error_type] = error_stats.get(error_type, 0) + count

        # 响应时间统计
        all_response_times = []
        for s in sessions:
            if s.get('avg_response_time_ms', 0) > 0:
                all_response_times.append(s['avg_response_time_ms'])

        avg_response = sum(all_response_times) / len(all_response_times) if all_response_times else 0

        # 库存统计
        inventory_appear_rate = sum(1 for s in sessions if s.get('inventory_appeared')) / total

        # 认证问题统计
        auth_fail_count = sum(1 for s in sessions if not s.get('auth_valid', True))
        cookie_expired_count = sum(1 for s in sessions if s.get('cookie_expired', False))

        # 限流统计
        rate_limited_sessions = sum(1 for s in sessions if s.get('rate_limited_requests', 0) > 0)
        captcha_sessions = sum(1 for s in sessions if s.get('captcha_triggered', 0) > 0)

        # 生成改进建议
        suggestions = self._generate_suggestions(
            success_rate=success_rate,
            error_stats=error_stats,
            avg_response=avg_response,
            inventory_appear_rate=inventory_appear_rate,
            auth_fail_count=auth_fail_count,
            cookie_expired_count=cookie_expired_count,
            rate_limited_sessions=rate_limited_sessions,
            captcha_sessions=captcha_sessions,
            total_sessions=total
        )

        # 最近会话摘要
        recent_sessions = sessions[-10:]

        return {
            "has_data": True,
            "summary": {
                "total_sessions": total,
                "success_count": success_count,
                "success_rate": round(success_rate * 100, 1),
                "avg_response_time_ms": round(avg_response, 0),
                "inventory_appear_rate": round(inventory_appear_rate * 100, 1),
                "auth_fail_count": auth_fail_count,
                "rate_limited_sessions": rate_limited_sessions,
                "captcha_sessions": captcha_sessions
            },
            "error_stats": error_stats,
            "suggestions": suggestions,
            "recent_sessions": [
                {
                    "session_id": s.get('session_id', ''),
                    "username": s.get('account_username', ''),
                    "success": s.get('success', False),
                    "total_requests": s.get('total_requests', 0),
                    "inventory_appeared": s.get('inventory_appeared', False),
                    "start_time": s.get('start_time', '')
                }
                for s in recent_sessions
            ]
        }

    def _generate_suggestions(self, success_rate: float, error_stats: Dict[str, int],
                              avg_response: float, inventory_appear_rate: float,
                              auth_fail_count: int, cookie_expired_count: int,
                              rate_limited_sessions: int, captcha_sessions: int,
                              total_sessions: int) -> List[Dict[str, Any]]:
        """生成改进建议"""
        suggestions = []

        # 认证问题
        if auth_fail_count > 0 or cookie_expired_count > 0:
            suggestions.append({
                "priority": "high",
                "category": "认证",
                "title": "登录状态失效",
                "description": f"检测到 {auth_fail_count} 次认证失败，{cookie_expired_count} 次 Cookie 过期",
                "action": "建议检查预登录脚本是否正常运行，或手动重新登录账号",
                "impact": "高 - 认证失败会导致抢购完全无法进行"
            })

        # 限流问题
        if rate_limited_sessions > total_sessions * 0.3:
            suggestions.append({
                "priority": "high",
                "category": "限流",
                "title": "频繁触发限流",
                "description": f"{rate_limited_sessions}/{total_sessions} 次会话触发了限流",
                "action": "建议降低请求频率，或增加请求间隔随机性，考虑使用多IP策略",
                "impact": "高 - 限流会大幅降低抢购成功率"
            })

        # 验证码问题
        if captcha_sessions > total_sessions * 0.2:
            suggestions.append({
                "priority": "high",
                "category": "验证码",
                "title": "频繁触发验证码",
                "description": f"{captcha_sessions}/{total_sessions} 次会话触发了验证码",
                "action": "建议在Web界面准备好手动处理验证码，或考虑使用验证码识别服务",
                "impact": "高 - 验证码会中断自动抢购流程"
            })

        # 响应时间问题
        if avg_response > 500:
            suggestions.append({
                "priority": "medium",
                "category": "网络",
                "title": "网络延迟较高",
                "description": f"平均响应时间 {avg_response:.0f}ms，较高",
                "action": "建议检查网络连接，考虑使用更稳定的网络或服务器部署",
                "impact": "中 - 延迟过高可能错过抢购时机"
            })

        # 库存问题
        if inventory_appear_rate < 0.3:
            suggestions.append({
                "priority": "medium",
                "category": "库存",
                "title": "库存出现率低",
                "description": f"仅 {inventory_appear_rate*100:.1f}% 的会话检测到库存",
                "action": "建议调整抢购时间，确保在10:00:00准时发起请求，或选择库存更充足的套餐",
                "impact": "中 - 库存不足会直接导致抢购失败"
            })

        # 成功率低
        if success_rate < 0.5 and total_sessions >= 3:
            suggestions.append({
                "priority": "high",
                "category": "综合",
                "title": "整体成功率偏低",
                "description": f"成功率仅 {success_rate*100:.1f}%，需要优化",
                "action": "建议综合检查：登录状态、网络延迟、请求时机、套餐选择策略",
                "impact": "高 - 直接影响抢购效果"
            })

        # 成功率高但有提升空间
        elif success_rate < 0.8 and success_rate >= 0.5 and total_sessions >= 3:
            suggestions.append({
                "priority": "low",
                "category": "优化",
                "title": "成功率有提升空间",
                "description": f"当前成功率 {success_rate*100:.1f}%，可进一步优化",
                "action": "建议分析失败会话的具体原因，针对性改进",
                "impact": "低 - 小幅提升成功率"
            })

        # 网络错误
        if error_stats.get('network', 0) > total_sessions:
            suggestions.append({
                "priority": "medium",
                "category": "网络",
                "title": "网络错误较多",
                "description": f"发生 {error_stats['network']} 次网络错误",
                "action": "建议检查网络稳定性，考虑增加重试机制或备用网络",
                "impact": "中 - 网络不稳定会导致请求失败"
            })

        # 售罄问题
        if error_stats.get('sold_out', 0) > total_sessions * 2:
            suggestions.append({
                "priority": "medium",
                "category": "库存",
                "title": "库存竞争激烈",
                "description": f"检测到 {error_stats['sold_out']} 次售罄状态",
                "action": "建议选择竞争较小的套餐（参考成功率分析），或优化抢购时机",
                "impact": "中 - 库存竞争直接影响成功率"
            })

        # 按优先级排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda x: priority_order.get(x["priority"], 3))

        return suggestions


# 全局单例
_analyzer: Optional[PurchaseAnalyzer] = None


def get_purchase_analyzer() -> PurchaseAnalyzer:
    """获取抢购分析器"""
    global _analyzer
    if _analyzer is None:
        _analyzer = PurchaseAnalyzer()
    return _analyzer
