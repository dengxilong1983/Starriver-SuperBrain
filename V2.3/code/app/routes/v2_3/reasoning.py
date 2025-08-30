from typing import List
from uuid import uuid4
from pydantic import BaseModel
from fastapi import APIRouter

router = APIRouter(prefix="/api/v2.3-preview/reasoning", tags=["reasoning"])


class PlanRequest(BaseModel):
    goal: str
    constraints: List[str] = []
    max_steps: int = 5


class PlanStep(BaseModel):
    index: int
    action: str
    expected_outcome: str


class PlanResponse(BaseModel):
    plan_id: str
    steps: List[PlanStep]


@router.post("/plan", response_model=PlanResponse)
async def create_plan(req: PlanRequest):
    steps = [
        PlanStep(index=i + 1, action=f"step-{i+1}", expected_outcome=f"outcome-{i+1}")
        for i in range(max(1, min(req.max_steps, 10)))
    ]
    return PlanResponse(plan_id=str(uuid4()), steps=steps)