"""学习和日志记录模块"""
from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, asdict
import asyncio
from aiohttp import ClientResponse


@dataclass
class RequestRecord:
    """单次请求记录"""
    timestamp: str
    url: str
    method: str
    headers: dict
    params: Optional[dict]
    data: Optional[dict]
    status_code: int
    response_text: str  # 限制长度
    response_time_ms: float
    error: Optional[str] = None


class Recorder:
    """请求记录器"""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._current_session: list[RequestRecord] = []
        self._session_start: Optional[datetime] = None

    def start_session(self):
        """开始新的记录会话"""
        self._current_session = []
        self._session_start = datetime.now()
        self.info(f"=== 新会话开始 {self._session_start.isoformat()} ===")

    def _get_log_file(self) -> Path:
        """获取当天的日志文件路径"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"{date_str}.log"

    def info(self, message: str):
        """记录信息日志"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] INFO: {message}\n"
        self._append_log(line)
        print(line.strip())

    def error(self, message: str):
        """记录错误日志"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] ERROR: {message}\n"
        self._append_log(line)
        print(line.strip())

    def _append_log(self, line: str):
        """追加日志行到文件"""
        log_file = self._get_log_file()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)

    async def record_request(
        self,
        url: str,
        method: str,
        headers: dict,
        params: Optional[dict],
        data: Optional[dict],
        response: Optional[ClientResponse],
        response_time_ms: float,
        error: Optional[str] = None
    ) -> RequestRecord:
        """记录一次HTTP请求"""
        status_code = response.status if response else 0
        response_text = ""
        if response:
            try:
                response_text = await response.text()
            except:
                response_text = "[无法读取响应]"

        record = RequestRecord(
            timestamp=datetime.now().isoformat(),
            url=url,
            method=method,
            headers=dict(headers) if headers else {},
            params=params,
            data=data,
            status_code=status_code,
            response_text=response_text[:1000],
            response_time_ms=response_time_ms,
            error=error
        )

        self._current_session.append(record)

        # 记录简要日志
        log_msg = f"请求 {method} {url} -> {status_code} ({response_time_ms:.0f}ms)"
        if error:
            log_msg += f" ERROR: {error}"
        self.info(log_msg)

        return record

    def save_session(self):
        """保存当前会话记录到JSON文件"""
        if not self._current_session:
            return

        session_file = self.log_dir / f"session_{self._session_start.strftime('%Y%m%d_%H%M%S')}.json"
        data = {
            "session_start": self._session_start.isoformat() if self._session_start else None,
            "records": [asdict(r) for r in self._current_session]
        }

        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.info(f"会话记录已保存: {session_file}")

    def get_discoveries(self) -> list[dict]:
        """从历史记录中发现的API接口"""
        discoveries = []
        for record in self._current_session:
            if record.status_code == 200 and "api" in record.url.lower():
                discoveries.append({
                    "url": record.url,
                    "method": record.method,
                    "params": record.params,
                    "data": record.data
                })
        return discoveries


# 全局记录器实例
_recorder: Optional[Recorder] = None


def get_recorder() -> Recorder:
    """获取全局记录器实例"""
    global _recorder
    if _recorder is None:
        _recorder = Recorder()
    return _recorder
