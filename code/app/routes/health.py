from datetime import datetime, timezone
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["health"]) 
async def health():
    return {
        "status": "ok",
        "ts": datetime.now(timezone.utc).isoformat(),
        "service": "v2.3-api",
    }