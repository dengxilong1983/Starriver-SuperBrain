from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

router = APIRouter(prefix="/api/v2.3-preview/cloud", tags=["cloud"])


class ConsentRequest(BaseModel):
    user_id: str
    consent: bool = True
    scopes: Optional[List[str]] = []


class ConsentResponse(BaseModel):
    status: str
    consent_id: str
    user_id: str
    granted_scopes: List[str]
    timestamp: str


class StatusResponse(BaseModel):
    status: str
    consent_active: bool
    scopes: List[str]


# In-memory consent store keyed by user_id
_CONSENTS = {}


@router.post("/consent", response_model=ConsentResponse, status_code=201)
async def create_consent(req: ConsentRequest):
    cid = str(uuid4())
    _CONSENTS[req.user_id] = {
        "id": cid,
        "scopes": req.scopes or [],
        "active": bool(req.consent),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    return ConsentResponse(
        status="created",
        consent_id=cid,
        user_id=req.user_id,
        granted_scopes=_CONSENTS[req.user_id]["scopes"],
        timestamp=_CONSENTS[req.user_id]["ts"],
    )


@router.delete("/consent", response_model=StatusResponse)
async def revoke_consent(user_id: str = Query(..., description="User ID to revoke consent for")):
    entry = _CONSENTS.get(user_id)
    if not entry:
        return StatusResponse(status="disconnected", consent_active=False, scopes=[])
    entry["active"] = False
    return StatusResponse(status="disconnected", consent_active=False, scopes=entry.get("scopes", []))


@router.get("/status", response_model=StatusResponse, responses={
    204: {"description": "No Content when user_id is not provided"}
})
async def consent_status(user_id: Optional[str] = Query(default=None, description="User ID to get consent status for")):
    # When user_id is not provided, align with tests to return 204 No Content
    if not user_id:
        return Response(status_code=204)
    entry = _CONSENTS.get(user_id)
    if not entry:
        return StatusResponse(status="disconnected", consent_active=False, scopes=[])
    is_active = bool(entry.get("active"))
    return StatusResponse(
        status="connected" if is_active else "disconnected",
        consent_active=is_active,
        scopes=entry.get("scopes", [])
    )