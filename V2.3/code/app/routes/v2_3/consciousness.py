from datetime import datetime, timezone
from typing import Optional, Dict, List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from .observability import metrics as obs_metrics, logs as obs_logs
from uuid import uuid4


router = APIRouter(prefix="/api/v2.3-preview/consciousness", tags=["consciousness"])


# ---- Minimal Consciousness Core (v0) ----
# Allowed states and transitions for preview version
_ALLOWED_STATES = {"idle", "focusing", "reasoning", "executing", "sleeping"}
_ALLOWED_TRANSITIONS: Dict[str, set] = {
    "idle": {"focusing", "sleeping"},
    "focusing": {"reasoning", "sleeping", "idle"},
    "reasoning": {"executing", "sleeping", "focusing"},
    "executing": {"focusing", "sleeping"},
    "sleeping": {"idle"},
}

# State -> numeric code gauge mapping
_STATE_CODE_MAP: Dict[str, float] = {
    "idle": 0.0,
    "focusing": 1.0,
    "reasoning": 2.0,
    "executing": 3.0,
    "sleeping": 4.0,
}

# Global runtime state
_CURRENT_STATE: str = "idle"
_GOAL_STACK: List[str] = []
_LAST_UPDATED: datetime = datetime.now(timezone.utc)


def _allowed_next(state: str) -> List[str]:
    return sorted(list(_ALLOWED_TRANSITIONS.get(state, set())))


def get_current_state() -> str:
    return _CURRENT_STATE


# ---- Observability bootstrap ----
try:
    obs_metrics.set_label("consciousness_state_label", _CURRENT_STATE)
    obs_metrics.set_gauge("consciousness_state", _STATE_CODE_MAP[_CURRENT_STATE])
    obs_metrics.set_gauge("attention_stack_size", float(len(_GOAL_STACK)))
except Exception:
    pass


# ---- Models ----
class StateRequest(BaseModel):
    state: str
    goal: Optional[str] = None
    force: bool = False


class StateResponse(BaseModel):
    state: str
    updated_at: str
    current_goal: Optional[str]
    goal_stack: List[str]
    allowed_next_states: List[str]


class AttentionRequest(BaseModel):
    target: Optional[str] = None
    mode: Optional[str] = "push"  # push|replace|clear


class AttentionResponse(BaseModel):
    current: Optional[str]
    stack: List[str]
    stack_size: int
    updated_at: str


# ---- Routes ----
@router.get("/attention", response_model=AttentionResponse)
async def get_attention(request: Request):
    try:
        obs_metrics.inc("attention_get_total", 1)
        obs_metrics.set_gauge("attention_stack_size", float(len(_GOAL_STACK)))
    except Exception:
        pass
    return AttentionResponse(
        current=_GOAL_STACK[-1] if _GOAL_STACK else None,
        stack=list(_GOAL_STACK),
        stack_size=len(_GOAL_STACK),
        updated_at=_LAST_UPDATED.isoformat(),
    )


@router.post("/attention", response_model=AttentionResponse)
async def set_attention(req: AttentionRequest, request: Request):
    global _GOAL_STACK, _LAST_UPDATED
    mode = (req.mode or "push").lower()
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id") or str(uuid4())
    if mode not in {"push", "replace", "clear"}:
        try:
            obs_metrics.inc("attention_invalid_mode_total", 1)
            obs_logs.add("WARN", f"invalid attention mode: {mode}", module="consciousness", tags=[mode, trace_id], extra={"trace_id": trace_id})
        except Exception:
            pass
        raise HTTPException(status_code=400, detail={"message": "invalid mode", "mode": mode})

    if mode == "clear":
        _GOAL_STACK.clear()
    elif mode == "replace":
        _GOAL_STACK = [req.target] if req.target else []
    else:  # push
        if req.target:
            _GOAL_STACK.append(req.target)

    _LAST_UPDATED = datetime.now(timezone.utc)
    try:
        obs_metrics.inc("attention_set_total", 1)
        obs_metrics.set_gauge("attention_stack_size", float(len(_GOAL_STACK)))
        obs_logs.add("INFO", f"attention {mode}", module="consciousness", tags=[mode, trace_id], extra={"target": req.target or None, "trace_id": trace_id})
    except Exception:
        pass

    return AttentionResponse(
        current=_GOAL_STACK[-1] if _GOAL_STACK else None,
        stack=list(_GOAL_STACK),
        stack_size=len(_GOAL_STACK),
        updated_at=_LAST_UPDATED.isoformat(),
    )


@router.get("/state", response_model=StateResponse)
async def get_state(request: Request):
    try:
        obs_metrics.inc("consciousness_get_state_total", 1)
    except Exception:
        pass
    return StateResponse(
        state=_CURRENT_STATE,
        updated_at=_LAST_UPDATED.isoformat(),
        current_goal=_GOAL_STACK[-1] if _GOAL_STACK else None,
        goal_stack=list(_GOAL_STACK),
        allowed_next_states=_allowed_next(_CURRENT_STATE),
    )


@router.post("/state", response_model=StateResponse)
async def set_state(req: StateRequest, request: Request):
    global _CURRENT_STATE, _LAST_UPDATED, _GOAL_STACK

    new_state = req.state
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id") or str(uuid4())
    if new_state not in _ALLOWED_STATES:
        try:
            obs_metrics.inc("consciousness_invalid_state_total", 1)
            obs_logs.add("WARN", "invalid state", module="consciousness", tags=[new_state, trace_id], extra={"trace_id": trace_id})
        except Exception:
            pass
        raise HTTPException(status_code=400, detail={
            "message": "invalid state",
            "state": new_state,
            "allowed_states": sorted(list(_ALLOWED_STATES)),
        })

    if not req.force and new_state not in _ALLOWED_TRANSITIONS.get(_CURRENT_STATE, set()):
        try:
            obs_metrics.inc("consciousness_illegal_transition_total", 1)
            obs_logs.add("WARN", "illegal transition", module="consciousness", tags=[_CURRENT_STATE, new_state, trace_id], extra={"trace_id": trace_id})
        except Exception:
            pass
        raise HTTPException(status_code=409, detail={
            "message": "illegal transition",
            "from": _CURRENT_STATE,
            "to": new_state,
            "allowed_next_states": _allowed_next(_CURRENT_STATE),
        })

    # State transition
    _CURRENT_STATE = new_state
    _LAST_UPDATED = datetime.now(timezone.utc)

    # Optional goal update
    if req.goal is not None:
        if req.goal == "":
            _GOAL_STACK.clear()
        else:
            _GOAL_STACK.append(req.goal)

    # Update gauges/labels
    try:
        obs_metrics.inc("consciousness_set_state_total", 1)
        obs_metrics.set_label("consciousness_state_label", _CURRENT_STATE)
        obs_metrics.set_gauge("consciousness_state", _STATE_CODE_MAP[_CURRENT_STATE])
        obs_metrics.set_gauge("attention_stack_size", float(len(_GOAL_STACK)))
        obs_logs.add("INFO", f"state set to {new_state}", module="consciousness", tags=[new_state, trace_id], extra={"goal": req.goal or None, "trace_id": trace_id})
    except Exception:
        pass

    return StateResponse(
        state=_CURRENT_STATE,
        updated_at=_LAST_UPDATED.isoformat(),
        current_goal=_GOAL_STACK[-1] if _GOAL_STACK else None,
        goal_stack=list(_GOAL_STACK),
        allowed_next_states=_allowed_next(_CURRENT_STATE),
    )