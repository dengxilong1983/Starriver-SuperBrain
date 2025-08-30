from typing import Any, Dict
from pydantic import BaseModel
from fastapi import APIRouter

router = APIRouter(prefix="/api/v2.3-preview/execution", tags=["execution"])


class ActRequest(BaseModel):
    action: str
    params: Dict[str, Any] = {}


class ActResponse(BaseModel):
    success: bool
    output: Dict[str, Any]


@router.post("/act", response_model=ActResponse)
async def act(req: ActRequest):
    # Echo-style placeholder
    return ActResponse(success=True, output={"action": req.action, "params": req.params})