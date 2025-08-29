from __future__ import annotations
from collections import deque
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any, Deque, Dict, List, Optional, Tuple

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/v2.3-preview/observability", tags=["observability"])


# ---- Minimal Observability Core (v0) ----
class Metrics:
    def __init__(self, max_timings: int = 200) -> None:
        self.counters: Dict[str, int] = {}
        self.timings: Dict[str, List[float]] = {}
        self.gauges: Dict[str, float] = {}
        self.labels: Dict[str, str] = {}
        self._max_timings = max_timings

    def inc(self, name: str, value: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + value

    def observe(self, name: str, ms: float) -> None:
        arr = self.timings.get(name)
        if arr is None:
            arr = []
            self.timings[name] = arr
        arr.append(ms)
        if len(arr) > self._max_timings:
            # keep recent window
            del arr[: len(arr) - self._max_timings]

    # new gauge setter
    def set_gauge(self, name: str, value: float) -> None:
        self.gauges[name] = float(value)

    # new label setter
    def set_label(self, name: str, value: str) -> None:
        self.labels[name] = str(value)

    def snapshot(self) -> Dict[str, Any]:
        def percentiles(values: List[float], p: float) -> float:
            if not values:
                return 0.0
            values_sorted = sorted(values)
            k = int(round((len(values_sorted) - 1) * p))
            return float(values_sorted[k])

        timings_summary: Dict[str, Dict[str, float]] = {}
        for k, vals in self.timings.items():
            if not vals:
                timings_summary[k] = {"count": 0, "avg_ms": 0.0, "p95_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}
                continue
            timings_summary[k] = {
                "count": float(len(vals)),
                "avg_ms": float(mean(vals)),
                "p95_ms": float(percentiles(vals, 0.95)),
                "min_ms": float(min(vals)),
                "max_ms": float(max(vals)),
            }
        return {
            "counters": dict(self.counters),
            "timings": timings_summary,
            "gauges": dict(self.gauges),
            "labels": dict(self.labels),
            "window": self._max_timings,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


class LogBuffer:
    def __init__(self, maxlen: int = 1000) -> None:
        self._buf: Deque[Dict[str, Any]] = deque(maxlen=maxlen)

    def add(self, level: str, message: str, *, module: str, tags: Optional[List[str]] = None, extra: Optional[Dict[str, Any]] = None) -> None:
        self._buf.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": level.upper(),
                "message": message,
                "module": module,
                "tags": tags or [],
                "extra": extra or {},
            }
        )

    def search(
        self,
        *,
        q: Optional[str] = None,
        level: Optional[str] = None,
        since_seconds: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        results: List[Dict[str, Any]] = []
        level_u = level.upper() if level else None
        since_dt = now - timedelta(seconds=since_seconds) if since_seconds else None
        for item in reversed(self._buf):  # newest first
            if level_u and item.get("level") != level_u:
                continue
            if q and (q not in item.get("message", "")):
                # also match tags
                if q not in ",".join(item.get("tags", [])):
                    continue
            if since_dt:
                try:
                    its = datetime.fromisoformat(item.get("ts"))
                except Exception:
                    its = now
                if its < since_dt:
                    continue
            results.append(item)
            if len(results) >= max(1, min(limit, 200)):
                break
        return results


# Global singletons for easy import in other routers
metrics = Metrics()
logs = LogBuffer(maxlen=2000)


@router.get("/metrics")
async def get_metrics():
    return metrics.snapshot()


class LogSearchRequest(BaseModel):
    # Accept both 'q' and 'query' for compatibility with tests
    q: Optional[str] = None
    query: Optional[str] = None
    level: Optional[str] = None
    limit: int = 50
    since_seconds: Optional[int] = 3600

@router.get("/logs/search")
async def search_logs(
    q: Optional[str] = Query(default=None, description="text or tag contains"),
    level: Optional[str] = Query(default=None, description="INFO/WARN/ERROR"),
    limit: int = Query(default=50, ge=1, le=200),
    since_seconds: Optional[int] = Query(default=3600, ge=1),
):
    items = logs.search(q=q, level=level, since_seconds=since_seconds, limit=limit)
    return {
        "count": len(items),
        "returned": len(items),
        "items": items,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

# New: POST variant for compatibility with tests expecting POST
@router.post("/logs/search")
async def search_logs_post(payload: LogSearchRequest):
    # normalize q from either 'q' or 'query'
    q = payload.q or payload.query
    # validate and clamp limit range similar to GET endpoint
    limit = max(1, min((payload.limit or 50), 200))
    items = logs.search(
        q=q,
        level=payload.level,
        since_seconds=payload.since_seconds,
        limit=limit,
    )
    return {
        "count": len(items),
        "returned": len(items),
        "items": items,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }