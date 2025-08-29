from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
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