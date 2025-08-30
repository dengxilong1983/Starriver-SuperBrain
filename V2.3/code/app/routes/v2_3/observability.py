from __future__ import annotations
from collections import deque
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any, Deque, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field, ConfigDict

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
        # Clamp since_seconds to avoid datetime underflow during fuzzing
        MAX_RANGE_SECONDS = 365 * 24 * 3600  # 1 year window is enough for in-memory buffer
        safe_seconds: Optional[int] = None
        if since_seconds:
            try:
                safe_seconds = max(1, min(int(since_seconds), MAX_RANGE_SECONDS))
            except Exception:
                safe_seconds = 3600
        # Compute since_dt safely
        since_dt: Optional[datetime] = None
        if safe_seconds is not None:
            try:
                since_dt = now - timedelta(seconds=safe_seconds)
            except OverflowError:
                # Fallback to the minimal representable datetime with UTC tz
                since_dt = datetime.min.replace(tzinfo=timezone.utc)
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


@router.get(
    "/metrics",
    summary="导出内存指标（Prometheus 文本格式）",
    description="返回应用内存中的 gauges/counters/timings 快照，便于监控采集（纯文本）。",
)
async def metrics_export():
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

# --- New: C1 Context signals endpoint ---
class ContextResponse(BaseModel):
    state: str
    labels: Dict[str, str]
    gauges: Dict[str, float]
    counters: Dict[str, int]
    timings: Dict[str, Dict[str, float]]
    trace_id: str
    updated_at: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "state": "awake",
                "labels": {"env": "dev", "version": "v2.3"},
                "gauges": {"http_active_requests": 1},
                "counters": {"http_requests_total": 123},
                "timings": {"http_request_ms": {"count": 10, "avg_ms": 12.3, "p95_ms": 25.6, "min_ms": 3.4, "max_ms": 120.8}},
                "trace_id": "11111111-2222-3333-4444-555555555555",
                "updated_at": "2025-01-01T00:00:00+00:00",
            }
        }
    )

@router.get("/context", response_model=ContextResponse, summary="情境感知快照（C1）", description="返回当前 state、labels、gauges/counters/timings 摘要，并贯穿 trace_id。")
async def get_context(request: Request):
    # lazy import to avoid circular dependency
    from .consciousness import get_current_state
    trace_id = request.headers.get("x-trace-id") or str(uuid4())
    state = get_current_state()
    try:
        metrics.inc("context_fetch_total", 1)
        logs.add("INFO", "context fetched", module="observability", tags=[trace_id], extra={"trace_id": trace_id, "state": state})
    except Exception:
        pass
    snap = metrics.snapshot()
    return ContextResponse(
        state=state,
        labels=snap.get("labels", {}),
        gauges=snap.get("gauges", {}),
        counters=snap.get("counters", {}),
        timings=snap.get("timings", {}),
        trace_id=trace_id,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )

# --- New: C6 Minimal traces endpoint ---
class TraceResponse(BaseModel):
    trace_id: str
    count: int
    items: List[Dict[str, Any]]
    updated_at: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "trace_id": "11111111-2222-3333-4444-555555555555",
                "count": 2,
                "items": [
                    {"ts": "2025-01-01T00:00:00+00:00", "level": "INFO", "message": "memory synced", "module": "memory", "tags": ["sync", "11111111-2222-3333-4444-555555555555"], "extra": {"count": 3, "trace_id": "11111111-2222-3333-4444-555555555555"}},
                    {"ts": "2025-01-01T00:00:01+00:00", "level": "INFO", "message": "memory committed", "module": "memory", "tags": ["commit", "11111111-2222-3333-4444-555555555555"], "extra": {"added": 3, "trace_id": "11111111-2222-3333-4444-555555555555"}}
                ],
                "updated_at": "2025-01-01T00:00:02+00:00"
            }
        }
    )

@router.get("/traces/{trace_id}", response_model=TraceResponse, summary="按 trace_id 聚合日志（C6）", description="基于日志缓冲区，按 extra.trace_id 或 tag 命中聚合为最小 trace 视图。")
async def get_trace_by_id(trace_id: str, since_seconds: Optional[int] = Query(default=3600, ge=1), limit: int = Query(default=50, ge=1, le=200)):
    now = datetime.now(timezone.utc)
    since_dt = None
    if since_seconds:
        try:
            since_dt = now - timedelta(seconds=int(since_seconds))
        except Exception:
            since_dt = now - timedelta(seconds=3600)
    matched: List[Dict[str, Any]] = []
    # iterate newest first
    for item in reversed(logs._buf):
        try:
            its = datetime.fromisoformat(item.get("ts"))
        except Exception:
            its = now
        if since_dt and its < since_dt:
            continue
        extra = item.get("extra") or {}
        tags = item.get("tags") or []
        message = item.get("message") or ""
        if (extra.get("trace_id") == trace_id) or (trace_id in tags) or (trace_id in message):
            matched.append(item)
            if len(matched) >= limit:
                break
    try:
        logs.add("INFO", "trace fetched", module="observability", tags=[trace_id], extra={"trace_id": trace_id, "found": len(matched)})
    except Exception:
        pass
    return TraceResponse(trace_id=trace_id, count=len(matched), items=matched, updated_at=datetime.now(timezone.utc).isoformat())


# ---- D4｜资产盘点 ----
class AssetInventoryResponse(BaseModel):
    modules: List[str]
    gauges: Dict[str, float]
    counters: Dict[str, int]
    timings: Dict[str, Dict[str, float]]
    experience_rules_total: int
    experience_candidates_total: int
    recent_logs: int
    updated_at: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "modules": ["observability", "experience", "memory", "agents"],
                "gauges": {
                    "experience_rules_total": 12,
                    "experience_candidates_total": 5,
                    "http_active_requests": 1,
                },
                "counters": {
                    "http_requests_total": 1245,
                    "migration_execute_total": 2,
                },
                "timings": {
                    "http_request_ms": {"count": 128, "avg_ms": 12.3, "p50_ms": 9.1, "p95_ms": 25.6, "min_ms": 3.4, "max_ms": 120.8}
                },
                "experience_rules_total": 12,
                "experience_candidates_total": 5,
                "recent_logs": 37,
                "updated_at": "2025-01-01T00:00:00+00:00",
            }
        }
    )

@router.get("/assets", response_model=AssetInventoryResponse, summary="资产盘点（D4）", description="返回当前内存中的模块、指标（gauges/counters/timings）与经验引擎摘要。since_seconds 控制 recent_logs 统计窗口（默认10分钟）。")
async def get_asset_inventory(since_seconds: int = Query(default=600, ge=1)):
    snap = metrics.snapshot()
    # 尝试从gauge中读取由experience路由维护的统计数据，若不存在则回退为0
    rules_total = int(snap.get("gauges", {}).get("experience_rules_total", 0.0))
    candidates_total = int(snap.get("gauges", {}).get("experience_candidates_total", 0.0))
    recent = logs.search(since_seconds=since_seconds, limit=200)
    return AssetInventoryResponse(
        modules=["observability", "experience", "memory", "agents"],
        gauges=snap.get("gauges", {}),
        counters=snap.get("counters", {}),
        timings=snap.get("timings", {}),
        experience_rules_total=rules_total,
        experience_candidates_total=candidates_total,
        recent_logs=len(recent),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---- D5｜数据迁移 PoC ----
class MigrationPlanStep(BaseModel):
    name: str
    description: str
    estimated_ms: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"name": "export_memory", "description": "Export memory snapshot for backup", "estimated_ms": 300}
        }
    )


class MigrationPlanRequest(BaseModel):
    source_version: str = "v2.2"
    target_version: str = "v2.3"
    dry_run: bool = True
    scope: List[str] = []  # e.g., ["experience", "memory"]


class MigrationPlanResponse(BaseModel):
    steps: List[MigrationPlanStep]
    total_estimated_ms: int
    risks: List[str]
    can_rollback: bool
    updated_at: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "steps": [
                    {"name": "export_memory", "description": "Export memory snapshot for backup", "estimated_ms": 300},
                    {"name": "export_experience", "description": "Export experience rules snapshot", "estimated_ms": 300},
                    {"name": "reindex_metrics", "description": "Rebuild gauges and counters after deploy", "estimated_ms": 200},
                    {"name": "health_verify", "description": "Verify health endpoints and key routes", "estimated_ms": 200},
                ],
                "total_estimated_ms": 1000,
                "risks": [
                    "in-memory-only store, data lost on restart without snapshot",
                    "schema drift between versions may require manual review",
                ],
                "can_rollback": True,
                "updated_at": "2025-01-01T00:00:00+00:00",
            }
        }
    )

@router.post("/migration/plan", response_model=MigrationPlanResponse)
async def plan_migration(req: MigrationPlanRequest):
    # naive planning: each scope adds two steps
    steps: List[MigrationPlanStep] = []
    base = [
        ("export_memory", "Export memory snapshot for backup", 300),
        ("export_experience", "Export experience rules snapshot", 300),
    ]
    for name, desc, est in base:
        if not req.scope or (name.split("_")[-1] in ",".join(req.scope)):
            steps.append(MigrationPlanStep(name=name, description=desc, estimated_ms=est))
    # always include health verification
    steps.append(MigrationPlanStep(name="reindex_metrics", description="Rebuild gauges and counters after deploy", estimated_ms=200))
    steps.append(MigrationPlanStep(name="health_verify", description="Verify health endpoints and key routes", estimated_ms=200))

    total = sum(s.estimated_ms for s in steps)
    risks = [
        "in-memory-only store, data lost on restart without snapshot",
        "schema drift between versions may require manual review",
    ]
    return MigrationPlanResponse(steps=steps, total_estimated_ms=total, risks=risks, can_rollback=True, updated_at=datetime.now(timezone.utc).isoformat())


@router.post("/migration/execute", response_model=MigrationPlanResponse)
async def execute_migration(req: MigrationPlanRequest):
    metrics.inc("migration_execute_total", 1)
    plan = await plan_migration(req)
    # simulate execution timings observation
    metrics.observe("migration_execute_ms", 250.0)
    logs.add("INFO", "migration executed", module="observability", tags=["migration"], extra={"source": req.source_version, "target": req.target_version})
    return plan


class DashboardOverview(BaseModel):
    tiles: List[Dict[str, Any]]
    updated_at: str


@router.get(
    "/dashboard/overview",
    response_model=DashboardOverview,
    summary="Dashboard 概要（D6）",
    description=(
        "返回瓷砖化概要数据，用于快速展示系统健康度与经验引擎概况。\n"
        "包含以下瓷砖：\n"
        "- rules：当前经验规则数 (int)\n"
        "- candidates：当前候选规则数 (int)\n"
        "- http_p95_ms：HTTP 请求 p95 延迟（毫秒，float）\n"
        "- logs：近10分钟内的日志条数 (int)\n"
        "- auto_candidate_last_created：最近一次自动收割创建的候选条数 (int)\n"
        "- auto_candidate_trend：最近最多20次自动收割的创建数趋势（array<int>，最早在前）\n"
        "- auto_candidate_sources_top：最近一次收割的来源分布 TopN（array<object>，元素包含 source(str)、count(int)）\n"
    ),
)
async def dashboard_overview():
    snap = metrics.snapshot()
    # 基础瓷砖
    http_p95 = snap.get("timings", {}).get("http_request_ms", {}).get("p95_ms", 0.0)
    tiles: List[Dict[str, Any]] = [
        {"key": "rules", "title": "经验规则数", "value": int(snap.get("gauges", {}).get("experience_rules_total", 0.0))},
        {"key": "candidates", "title": "候选规则数", "value": int(snap.get("gauges", {}).get("experience_candidates_total", 0.0))},
        {"key": "http_p95_ms", "title": "HTTP p95 延迟(ms)", "value": float(http_p95)},
        {"key": "logs", "title": "近10分钟日志数", "value": len(logs.search(since_seconds=600, limit=1000))},
    ]

    # 自动收割相关瓷砖示例（若无则回退）
    last_created = 0
    trend: List[int] = []
    sources_top: List[Dict[str, Any]] = []

    recent_logs = logs.search(since_seconds=7 * 24 * 3600, limit=1000)
    # 识别两种消息格式
    harvest_events = [
        it for it in recent_logs if (it.get("message") in ("auto_candidate_harvest", "auto candidate harvested"))
    ]
    if harvest_events:
        # 最近一次
        latest = harvest_events[0]
        extra = latest.get("extra") or {}
        # created 可能为字符串
        try:
            last_created = int(extra.get("created", 0))
        except Exception:
            last_created = 0
        # 趋势：取最多20条，按时间顺序（最早在前）
        trend_vals: List[int] = []
        for ev in reversed(harvest_events[-20:]):
            ex = ev.get("extra") or {}
            try:
                trend_vals.append(int(ex.get("created", 0)))
            except Exception:
                trend_vals.append(0)
        trend = trend_vals
        # 来源分布：兼容 breakdown 与 sources 两种字段
        breakdown = extra.get("breakdown") or []
        sources_field = extra.get("sources") or []
        pairs: List[Tuple[str, int]] = []
        if breakdown:
            for d in breakdown:
                src = d.get("source")
                cnt = d.get("count", 0)
                src_str = str(src)
                try:
                    cnt_int = int(cnt)
                except Exception:
                    cnt_int = 0
                pairs.append((src_str, cnt_int))
        elif sources_field:
            for s in sources_field:
                src = s.get("source") or "unknown"
                cnt = s.get("count", 0)
                try:
                    cnt_int = int(cnt)
                except Exception:
                    cnt_int = 0
                pairs.append((str(src), cnt_int))
        # 汇总并取Top5
        agg: Dict[str, int] = {}
        for k, v in pairs:
            agg[k] = agg.get(k, 0) + v
        sources_top = [
            {"source": k, "count": v}
            for k, v in sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:5]
        ]

    tiles.extend(
        [
            {"key": "auto_candidate_last_created", "title": "最近自动收割创建数", "value": last_created},
            {"key": "auto_candidate_trend", "title": "自动收割趋势", "value": trend},
            {"key": "auto_candidate_sources_top", "title": "收割来源Top", "value": sources_top},
        ]
    )

    return DashboardOverview(tiles=tiles, updated_at=datetime.now(timezone.utc).isoformat())


class ReflectionSuggestion(BaseModel):
    title: str
    content: str
    category: str = "observability"
    tags: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    status: str = "draft"
    confidence: float = 0.6
    weight: float = 1.0


class ReflectionResponse(BaseModel):
    count: int
    suggestions: List[ReflectionSuggestion]
    updated_at: str


@router.get("/reflection/suggestions", response_model=ReflectionResponse)
async def reflection_suggestions(since_seconds: int = Query(default=900, ge=1), limit: int = Query(default=5, ge=1, le=20)):
    # 从最近日志中提取 WARN/ERROR，并按 (module, level) 聚合
    recent = logs.search(since_seconds=since_seconds, limit=500)
    freq: Dict[str, int] = {}
    examples: Dict[str, str] = {}
    for it in recent:
        level = (it.get("level") or "").upper()
        if level not in ("WARN", "ERROR"):
            continue
        module = it.get("module") or "unknown"
        key = f"{module}:{level}"
        freq[key] = freq.get(key, 0) + 1
        if key not in examples:
            examples[key] = it.get("message") or ""

    # 生成候选建议（按频次排序）
    ordered = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)[: (limit or 5)]
    suggestions: List[ReflectionSuggestion] = []
    for key, count in ordered:
        module, level = key.split(":", 1)
        ex_msg = examples.get(key, "")
        title = f"Reduce {level} in {module}"
        content = (
            f"Observed {count} {level} logs in module '{module}' within last {since_seconds}s.\n"
            f"Example: {ex_msg}\n"
            "Proposed action: introduce/adjust experience rule(s) to prevent or auto-handle this scenario, "
            "add guard conditions, or enhance retries with backoff; monitor effect via gauges."
        )
        suggestions.append(
            ReflectionSuggestion(
                title=title,
                content=content,
                category="stability" if level == "ERROR" else "quality",
                tags=[module, level, "reflection"],
                sources=["observability.logs"],
                status="draft",
                confidence=0.6 if level == "WARN" else 0.7,
                weight=1.0,
            )
        )

    return ReflectionResponse(count=len(suggestions), suggestions=suggestions, updated_at=datetime.now(timezone.utc).isoformat())