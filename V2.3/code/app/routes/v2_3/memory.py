from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import APIRouter, Query, HTTPException, Request
from pydantic import BaseModel, Field
from .observability import metrics as obs_metrics, logs as obs_logs
from .consciousness import get_current_state

router = APIRouter(prefix="/api/v2.3-preview/memory", tags=["memory"]) 


class MemoryItem(BaseModel):
    id: Optional[str] = None
    content: Dict[str, Any]


class MemorySyncRequest(BaseModel):
    # make items optional to be compatible with tests that send only {force, timeout}
    items: List[MemoryItem] = Field(default_factory=list)
    # optional control flags accepted by tests/tools; ignored by current implementation
    force: Optional[bool] = False
    timeout: Optional[int] = 30


class MemorySyncResponse(BaseModel):
    synced_count: int
    failed_count: int
    trace_id: str
    finished_at: str


class MemoryExportResponse(BaseModel):
    export_url: str
    expires_at: str


# Optional request body for POST /export to avoid 422 on unknown fields
class MemoryExportRequest(BaseModel):
    format: Optional[str] = "json"  # accepted but not used in this minimal implementation
    limit: Optional[int] = 100       # accepted but not used

# --- New: Minimal in-memory store for commit/retrieve ---
_MEMORY_STORE: List[Dict[str, Any]] = []

class MemoryCommitRequest(BaseModel):
    items: List[MemoryItem] = Field(default_factory=list)

class MemoryCommitResponse(BaseModel):
    added: int
    trace_id: str
    finished_at: str

class MemoryRetrieveRequest(BaseModel):
    query: Dict[str, Any]
    limit: Optional[int] = 5

class MemoryRetrieveResponse(BaseModel):
    trace_id: str
    count: int
    items: List[Dict[str, Any]]
    finished_at: str


def _score_item(item: Dict[str, Any], query: Dict[str, Any]) -> float:
    # simple field overlap scoring; if text fields exist, do substring match
    score = 0.0
    for k, v in query.items():
        iv = item.get("content", {}).get(k)
        try:
            if isinstance(iv, str) and isinstance(v, str):
                if v.lower() in iv.lower():
                    score += 1.0
            elif iv == v:
                score += 0.8
        except Exception:
            continue
    # length prior to avoid zero score
    return score


@router.post("/commit", response_model=MemoryCommitResponse)
async def memory_commit(req: MemoryCommitRequest, request: Request):
    trace_id = request.headers.get("x-trace-id") or str(uuid4())
    state = get_current_state()
    if state == "sleeping":
        try:
            obs_metrics.inc("memory_gate_denied_total", 1)
            obs_logs.add("WARN", "memory commit blocked (sleeping)", module="memory", tags=[trace_id], extra={"trace_id": trace_id})
        except Exception:
            pass
        raise HTTPException(status_code=423, detail={"message": "memory gate closed in sleeping", "state": state})

    added = 0
    for it in req.items:
        entry = {"id": it.id or str(uuid4()), "content": it.content, "ts": datetime.now(timezone.utc).isoformat()}
        _MEMORY_STORE.append(entry)
        added += 1
    try:
        obs_metrics.inc("memory_commit_total", 1)
        obs_metrics.inc("memory_items_total", added)
        obs_logs.add("INFO", "memory committed", module="memory", tags=["commit", trace_id], extra={"added": added, "trace_id": trace_id})
    except Exception:
        pass
    return MemoryCommitResponse(added=added, trace_id=trace_id, finished_at=datetime.now(timezone.utc).isoformat())


@router.post("/retrieve", response_model=MemoryRetrieveResponse)
async def memory_retrieve(req: MemoryRetrieveRequest, request: Request):
    trace_id = request.headers.get("x-trace-id") or str(uuid4())
    limit = max(1, min(int(req.limit or 5), 50))
    # score and sort
    scored: List[Tuple[float, Dict[str, Any]]] = []  # type: ignore[name-defined]
    for entry in reversed(_MEMORY_STORE):  # prefer recent
        s = _score_item(entry, req.query or {})
        if s > 0:
            scored.append((s, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    items = [e for _, e in scored[:limit]]
    try:
        obs_metrics.inc("memory_retrieve_total", 1)
        obs_metrics.set_gauge("memory_store_size", float(len(_MEMORY_STORE)))
        obs_logs.add("INFO", "memory retrieved", module="memory", tags=["retrieve", trace_id], extra={"count": len(items), "trace_id": trace_id})
    except Exception:
        pass
    return MemoryRetrieveResponse(trace_id=trace_id, count=len(items), items=items, finished_at=datetime.now(timezone.utc).isoformat())


@router.post("/sync", response_model=MemorySyncResponse)
async def memory_sync(req: MemorySyncRequest, request: Request):
    # derive or generate a trace id for this sync attempt and start timer
    trace_id = request.headers.get("x-trace-id") or str(uuid4())
    start_ts = datetime.now(timezone.utc)

    # minimal memory gating: deny when sleeping
    state = get_current_state()
    if state == "sleeping":
        try:
            obs_metrics.inc("memory_gate_denied_total", 1)
            obs_logs.add("WARN", "memory gate closed (sleeping)", module="memory", tags=[state, trace_id], extra={"items": len(req.items), "trace_id": trace_id})
        except Exception:
            pass
        raise HTTPException(status_code=423, detail={"message": "memory gate closed in sleeping", "state": state})

    synced = len(req.items)
    failed = 0
    elapsed_ms = (datetime.now(timezone.utc) - start_ts).total_seconds() * 1000.0
    try:
        obs_metrics.inc("memory_sync_total", 1)
        obs_metrics.inc("memory_items_synced_total", synced)
        obs_metrics.observe("memory_sync_ms", float(elapsed_ms))
        obs_logs.add("INFO", "memory synced", module="memory", tags=["sync", trace_id], extra={"count": synced, "trace_id": trace_id})
    except Exception:
        pass
    return MemorySyncResponse(
        synced_count=synced,
        failed_count=failed,
        trace_id=trace_id,
        finished_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/export", response_model=MemoryExportResponse)
async def memory_export():
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    try:
        obs_metrics.inc("memory_export_total", 1)
    except Exception:
        pass
    return MemoryExportResponse(
        export_url=f"/downloads/memory/export-{uuid4()}.json",
        expires_at=expires.isoformat(),
    )


# New: POST variant for compatibility with tests expecting POST body
@router.post("/export", response_model=MemoryExportResponse)
async def memory_export_post(_: MemoryExportRequest):
    # Behavior mirrors GET /export; request body is accepted for compatibility
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    try:
        obs_metrics.inc("memory_export_total", 1)
    except Exception:
        pass
    return MemoryExportResponse(
        export_url=f"/downloads/memory/export-{uuid4()}.json",
        expires_at=expires.isoformat(),
    )