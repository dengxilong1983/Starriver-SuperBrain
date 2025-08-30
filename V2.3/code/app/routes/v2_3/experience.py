from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from threading import Lock
from uuid import uuid4, UUID
import hashlib

from fastapi import APIRouter, HTTPException, Query, Request, Body
from pydantic import BaseModel, Field

from .observability import metrics as obs_metrics, logs as obs_logs


router = APIRouter(prefix="/api/v2.3-preview/experience", tags=["experience"])


# ---- Models ----
class ExperienceRule(BaseModel):
    id: Optional[str] = None
    title: str
    content: str
    category: Optional[str] = Field(default="general", description="rule category")
    tags: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    version: str = "v1"
    confidence: float = 0.7
    weight: float = 1.0
    status: str = Field(default="active", description="active|deprecated|draft")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    fingerprint: Optional[str] = None

    def ensure_ids(self) -> None:
        if not self.id:
            self.id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
        if not self.fingerprint:
            self.fingerprint = ExperienceStore.make_fingerprint(self.title, self.content)

    def to_compact(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "t": self.title,
            "c": self.content,
            "ctg": self.category,
            "tags": self.tags,
            "src": self.sources,
            "v": self.version,
            "cf": self.confidence,
            "w": self.weight,
            "s": self.status,
            "ca": self.created_at,
            "ua": self.updated_at,
            "fp": self.fingerprint,
        }

    @staticmethod
    def from_compact(d: Dict[str, Any]) -> "ExperienceRule":
        return ExperienceRule(
            id=d.get("id"),
            title=d.get("t") or "",
            content=d.get("c") or "",
            category=d.get("ctg") or "general",
            tags=list(d.get("tags") or []),
            sources=list(d.get("src") or []),
            version=d.get("v") or "v1",
            confidence=float(d.get("cf") or 0.7),
            weight=float(d.get("w") or 1.0),
            status=d.get("s") or "active",
            created_at=d.get("ca"),
            updated_at=d.get("ua"),
            fingerprint=d.get("fp"),
        )


class SearchResponse(BaseModel):
    count: int
    returned: int
    items: List[ExperienceRule]
    updated_at: str


class ImportRequest(BaseModel):
    items: Optional[List[ExperienceRule]] = None
    items_compact: Optional[List[Dict[str, Any]]] = None
    upsert: bool = True
    dedup: bool = True


# ---- In-memory Store (thread-safe) ----
class ExperienceStore:
    def __init__(self) -> None:
        self._by_id: Dict[str, ExperienceRule] = {}
        self._id_by_fp: Dict[str, str] = {}
        self._lock = Lock()

    @staticmethod
    def make_fingerprint(title: str, content: str) -> str:
        base = (title or "").strip().lower() + "\n" + (content or "").strip().lower()
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def stats(self) -> Tuple[int, int]:
        with self._lock:
            return len(self._by_id), len(self._id_by_fp)

    def add(self, rule: ExperienceRule, *, dedup: bool = True, upsert: bool = False) -> ExperienceRule:
        with self._lock:
            rule.ensure_ids()
            fp = rule.fingerprint or self.make_fingerprint(rule.title, rule.content)
            if dedup and fp in self._id_by_fp:
                # return existing
                ex_id = self._id_by_fp[fp]
                return self._by_id[ex_id]
            if upsert and rule.id in self._by_id:
                # update existing by id
                old = self._by_id[rule.id]
                rule.created_at = old.created_at or rule.created_at
            self._by_id[rule.id] = rule
            self._id_by_fp[fp] = rule.id
            return rule

    def get(self, id: str) -> Optional[ExperienceRule]:
        with self._lock:
            return self._by_id.get(id)

    def update(self, id: str, patch: Dict[str, Any]) -> ExperienceRule:
        with self._lock:
            cur = self._by_id.get(id)
            if not cur:
                raise KeyError("not_found")
            data = cur.model_dump()
            data.update({k: v for k, v in patch.items() if v is not None})
            upd = ExperienceRule(**data)
            upd.updated_at = datetime.now(timezone.utc).isoformat()
            upd.fingerprint = self.make_fingerprint(upd.title, upd.content)
            self._by_id[id] = upd
            self._id_by_fp[upd.fingerprint] = id
            return upd

    def delete(self, id: str) -> bool:
        with self._lock:
            cur = self._by_id.pop(id, None)
            if not cur:
                return False
            # best-effort remove fp index
            try:
                fp = cur.fingerprint or self.make_fingerprint(cur.title, cur.content)
                if self._id_by_fp.get(fp) == id:
                    self._id_by_fp.pop(fp, None)
            except Exception:
                pass
            return True

    def list_all(self) -> List[ExperienceRule]:
        with self._lock:
            return list(self._by_id.values())

    def search(
        self,
        *,
        q: Optional[str] = None,
        tag: Optional[str] = None,
        category: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[ExperienceRule]:
        ql = (q or "").strip().lower()
        tagl = (tag or "").strip().lower()
        catl = (category or "").strip().lower()
        stl = (status or "").strip().lower()
        res: List[Tuple[float, ExperienceRule]] = []
        with self._lock:
            for r in self._by_id.values():
                if catl and (r.category or "").lower() != catl:
                    continue
                if stl and (r.status or "").lower() != stl:
                    continue
                if tagl and tagl not in ",".join([t.lower() for t in (r.tags or [])]):
                    continue
                score = 0.0
                if ql:
                    in_title = ql in (r.title or "").lower()
                    in_content = ql in (r.content or "").lower()
                    if not (in_title or in_content):
                        continue
                    score += 2.0 if in_title else 0.0
                    score += 1.0 if in_content else 0.0
                score += (r.confidence or 0.0) * 0.5 + (r.weight or 0.0) * 0.5
                res.append((score, r))
        res.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in res[: max(1, min(limit, 200))]]

    def import_items(self, items: List[ExperienceRule], *, upsert: bool = True, dedup: bool = True) -> Tuple[int, int]:
        ok = 0
        dup = 0
        for it in items:
            before_cnt, _ = self.stats()
            existed = False
            try:
                added = self.add(it, dedup=dedup, upsert=upsert)
                after_cnt, _ = self.stats()
                existed = before_cnt == after_cnt and added.id not in (it.id or "")
                ok += 1
            except Exception:
                dup += 1
        return ok, dup


store = ExperienceStore()


# ---- Routes ----
@router.post("/rules", response_model=ExperienceRule)
async def add_rule(
    request: Request,
    payload: Dict[str, Any] = Body(default_factory=dict),
    dedup: bool = Query(default=True),
    upsert: bool = Query(default=False),
):
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id") or str(uuid4())
    try:
        # Compatibility mapping: allow legacy payloads with name/condition/action keys
        data = payload or {}
        title = str((data.get("title") or data.get("name") or "").strip())
        # Build content from provided fields if not explicitly set
        content = data.get("content")
        if not content:
            parts: List[str] = []
            if data.get("condition"):
                parts.append(f"condition: {data.get('condition')}")
            if data.get("pattern"):
                parts.append(f"pattern: {data.get('pattern')}")
            if data.get("action"):
                parts.append(f"action: {data.get('action')}")
            content = "\n".join(parts) if parts else ""
        # Fallbacks for minimal input
        if not title and content:
            title = (content[:30] + "...") if len(content) > 33 else content
        if not title:
            title = "untitled"
        status = str(data.get("status") or "active")
        category = str(data.get("category") or "general")
        tags = list(data.get("tags") or [])
        sources = list(data.get("sources") or [])

        rule = ExperienceRule(
            title=title,
            content=content or "",
            category=category,
            tags=tags,
            sources=sources,
            status=status,
        )
        added = store.add(rule, dedup=dedup, upsert=upsert)
        cnt, _ = store.stats()
        obs_metrics.inc("experience_rule_added_total", 1)
        obs_metrics.set_gauge("experience_rules_total", float(cnt))
        obs_logs.add("INFO", f"rule added {added.id}", module="experience", tags=["add", trace_id], extra={"trace_id": trace_id, "rule_id": added.id})
        return added
    except Exception as e:
        obs_logs.add("ERROR", f"add rule failed: {e}", module="experience", tags=["exception", trace_id], extra={"trace_id": trace_id})
        raise HTTPException(status_code=500, detail={"message": "add_failed"})


@router.get("/rules/{rule_id:uuid}", response_model=ExperienceRule, responses={
    404: {
        "description": "Not Found",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "id": {"type": "string", "format": "uuid"}
                    },
                    "required": ["message"]
                }
            }
        }
    }
})
async def get_rule(rule_id: UUID, request: Request):
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id") or str(uuid4())
    r = store.get(str(rule_id))
    if not r:
        obs_logs.add("WARN", "rule not found", module="experience", tags=[str(rule_id), trace_id], extra={"trace_id": trace_id})
        raise HTTPException(status_code=404, detail={"message": "not_found", "id": str(rule_id)})
    try:
        obs_metrics.inc("experience_rule_get_total", 1)
    except Exception:
        pass
    return r


@router.put("/rules/{rule_id:uuid}", response_model=ExperienceRule, responses={
    404: {
        "description": "Not Found",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "id": {"type": "string", "format": "uuid"}
                    },
                    "required": ["message"]
                }
            }
        }
    }
})
async def update_rule(rule_id: UUID, patch: Dict[str, Any], request: Request):
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id") or str(uuid4())
    try:
        upd = store.update(str(rule_id), patch)
        obs_metrics.inc("experience_rule_updated_total", 1)
        obs_logs.add("INFO", f"rule updated {rule_id}", module="experience", tags=["update", trace_id], extra={"trace_id": trace_id})
        return upd
    except KeyError:
        obs_logs.add("WARN", "rule not found for update", module="experience", tags=[str(rule_id), trace_id], extra={"trace_id": trace_id})
        raise HTTPException(status_code=404, detail={"message": "not_found", "id": str(rule_id)})
    except Exception as e:
        obs_logs.add("ERROR", f"update rule failed: {e}", module="experience", tags=["exception", trace_id], extra={"trace_id": trace_id})
        raise HTTPException(status_code=500, detail={"message": "update_failed"})


@router.delete("/rules/{rule_id:uuid}", responses={
    404: {
        "description": "Not Found",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "id": {"type": "string", "format": "uuid"}
                    },
                    "required": ["message"]
                }
            }
        }
    }
})
async def delete_rule(rule_id: UUID, request: Request):
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id") or str(uuid4())
    ok = store.delete(str(rule_id))
    if not ok:
        obs_logs.add("WARN", "rule not found for delete", module="experience", tags=[str(rule_id), trace_id], extra={"trace_id": trace_id})
        raise HTTPException(status_code=404, detail={"message": "not_found", "id": str(rule_id)})
    cnt, _ = store.stats()
    # refresh candidate (draft) gauge after deletion
    cand_cnt = sum(1 for r in store.list_all() if (r.status or "").lower() == "draft")
    try:
        obs_metrics.inc("experience_rule_deleted_total", 1)
        obs_metrics.set_gauge("experience_rules_total", float(cnt))
    except Exception:
        pass
    try:
        obs_metrics.set_gauge("experience_candidates_total", float(cand_cnt))
    except Exception:
        pass
    obs_logs.add("INFO", f"rule deleted {rule_id}", module="experience", tags=["delete", trace_id], extra={"trace_id": trace_id})
    return {"status": "deleted", "id": str(rule_id)}


# ---- Candidate queue + human review (P1 minimal loop) ----
@router.post("/candidates", response_model=ExperienceRule)
async def add_candidate(req: ExperienceRule, request: Request, dedup: bool = Query(default=False), upsert: bool = Query(default=False)):
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id") or str(uuid4())
    try:
        # force candidate status to draft for human review
        req.status = "draft"
        added = store.add(req, dedup=dedup, upsert=upsert)
        # compute candidate count (draft)
        cand_cnt = sum(1 for r in store.list_all() if (r.status or "").lower() == "draft")
        obs_metrics.inc("experience_candidate_added_total", 1)
        try:
            obs_metrics.set_gauge("experience_candidates_total", float(cand_cnt))
        except Exception:
            pass
        obs_logs.add(
            "INFO",
            f"candidate added {added.id}",
            module="experience",
            tags=["candidate_add", trace_id],
            extra={"trace_id": trace_id, "rule_id": added.id},
        )
        return added
    except Exception as e:
        obs_logs.add("ERROR", f"add candidate failed: {e}", module="experience", tags=["exception", trace_id], extra={"trace_id": trace_id})
        raise HTTPException(status_code=500, detail={"message": "candidate_add_failed"})


@router.get("/candidates", response_model=SearchResponse)
async def list_candidates(
    request: Request,
    q: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id") or str(uuid4())
    items = store.search(q=q, tag=tag, category=category, status="draft", limit=limit)
    try:
        obs_metrics.inc("experience_candidate_search_total", 1)
        obs_logs.add(
            "INFO",
            "candidate search",
            module="experience",
            tags=[q or "", tag or "", category or "", trace_id],
            extra={"trace_id": trace_id, "returned": len(items)},
        )
    except Exception:
        pass
    return SearchResponse(
        count=len(items),
        returned=len(items),
        items=items,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/candidates/{rule_id:uuid}/approve", response_model=ExperienceRule, responses={
    404: {
        "description": "Not Found",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "id": {"type": "string", "format": "uuid"}
                    },
                    "required": ["message"]
                }
            }
        }
    }
})
async def approve_candidate(rule_id: UUID, request: Request):
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id") or str(uuid4())
    try:
        upd = store.update(str(rule_id), {"status": "active"})
        # refresh candidate gauge
        cand_cnt = sum(1 for r in store.list_all() if (r.status or "").lower() == "draft")
        obs_metrics.inc("experience_candidate_approved_total", 1)
        try:
            obs_metrics.set_gauge("experience_candidates_total", float(cand_cnt))
        except Exception:
            pass
        obs_logs.add(
            "INFO",
            f"candidate approved {rule_id}",
            module="experience",
            tags=["approve", trace_id],
            extra={"trace_id": trace_id, "rule_id": str(rule_id)},
        )
        return upd
    except KeyError:
        obs_logs.add("WARN", "candidate not found for approve", module="experience", tags=[str(rule_id), trace_id], extra={"trace_id": trace_id})
        raise HTTPException(status_code=404, detail={"message": "not_found", "id": str(rule_id)})
    except Exception as e:
        obs_logs.add("ERROR", f"approve candidate failed: {e}", module="experience", tags=["exception", trace_id], extra={"trace_id": trace_id})
        raise HTTPException(status_code=500, detail={"message": "candidate_approve_failed"})


@router.post("/candidates/{rule_id:uuid}/reject", response_model=ExperienceRule, responses={
    404: {
        "description": "Not Found",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "id": {"type": "string", "format": "uuid"}
                    },
                    "required": ["message"]
                }
            }
        }
    }
})
async def reject_candidate(rule_id: UUID, request: Request, reason: Optional[str] = Query(default=None)):
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id") or str(uuid4())
    try:
        upd = store.update(str(rule_id), {"status": "deprecated"})
        cand_cnt = sum(1 for r in store.list_all() if (r.status or "").lower() == "draft")
        obs_metrics.inc("experience_candidate_rejected_total", 1)
        try:
            obs_metrics.set_gauge("experience_candidates_total", float(cand_cnt))
        except Exception:
            pass
        obs_logs.add(
            "INFO",
            f"candidate rejected {rule_id}",
            module="experience",
            tags=["reject", (reason or ""), trace_id],
            extra={"trace_id": trace_id, "rule_id": str(rule_id), "reason": reason or ""},
        )
        return upd
    except KeyError:
        obs_logs.add("WARN", "candidate not found for reject", module="experience", tags=[str(rule_id), trace_id], extra={"trace_id": trace_id})
        raise HTTPException(status_code=404, detail={"message": "not_found", "id": str(rule_id)})
    except Exception as e:
        obs_logs.add("ERROR", f"reject candidate failed: {e}", module="experience", tags=["exception", trace_id], extra={"trace_id": trace_id})
        raise HTTPException(status_code=500, detail={"message": "candidate_reject_failed"})


# 公共实现：规则列表/搜索
def _rules_search_impl(
    request: Request,
    q: Optional[str] = None,
    tag: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> SearchResponse:
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id") or str(uuid4())
    items = store.search(q=q, tag=tag, category=category, status=status, limit=limit)
    try:
        obs_metrics.inc("experience_rules_list_total", 1)
        obs_logs.add(
            "INFO",
            "rules list",
            module="experience",
            tags=[q or "", tag or "", category or "", status or "", trace_id],
            extra={"trace_id": trace_id, "returned": len(items)},
        )
    except Exception:
        pass
    return SearchResponse(
        count=len(items),
        returned=len(items),
        items=items,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/rules", response_model=SearchResponse)
async def list_rules(
    request: Request,
    q: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    return _rules_search_impl(request=request, q=q, tag=tag, category=category, status=status, limit=limit)


@router.get("/rules/search", response_model=SearchResponse)
async def search_rules(
    request: Request,
    q: Optional[str] = Query(default=None),
    tag: Optional[str] = Query(default=None),
    category: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    return _rules_search_impl(request=request, q=q, tag=tag, category=category, status=status, limit=limit)


@router.get("/snapshot/export")
async def export_snapshot(request: Request, compact: bool = Query(default=True)):
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id") or str(uuid4())
    items = store.list_all()
    if compact:
        payload = [it.to_compact() for it in items]
        mode = "compact"
    else:
        payload = [it.model_dump() for it in items]
        mode = "full"
    obs_logs.add("INFO", f"snapshot export {mode}", module="experience", tags=[mode, trace_id], extra={"trace_id": trace_id, "count": len(items)})
    return {
        "count": len(items),
        "mode": mode,
        "items": payload,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/snapshot/import")
async def import_snapshot(req: ImportRequest, request: Request):
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("x-trace-id") or str(uuid4())
    items: List[ExperienceRule] = []
    if req.items_compact:
        for it in req.items_compact:
            items.append(ExperienceRule.from_compact(it))
    if req.items:
        items.extend(req.items)
    if not items:
        raise HTTPException(status_code=400, detail={"message": "no_items"})
    ok, dup = store.import_items(items, upsert=req.upsert, dedup=req.dedup)
    cnt, _ = store.stats()
    # compute current draft candidates after import
    cand_cnt = sum(1 for r in store.list_all() if (r.status or "").lower() == "draft")
    try:
        obs_metrics.inc("experience_import_total", 1)
        obs_metrics.set_gauge("experience_rules_total", float(cnt))
        obs_logs.add("INFO", "snapshot import", module="experience", tags=[str(ok), str(dup), trace_id], extra={"trace_id": trace_id, "ok": ok, "dup": dup})
    except Exception:
        pass
    try:
        obs_metrics.set_gauge("experience_candidates_total", float(cand_cnt))
    except Exception:
        pass
    return {"imported": ok, "duplicates": dup, "total": cnt}


# ---- C3｜经验闭环 MVP：高频反思建议自动入候选（带开关与阈值） ----
class ExperienceAutoCandidateConfig(BaseModel):
    enabled: bool = False
    min_count: int = 3
    include_levels: List[str] = Field(default_factory=lambda: ["ERROR", "WARN"])  # 优先处理高优先级
    since_seconds: int = 900
    min_confidence: float = 0.6
    max_candidates: int = 10
    # 新增：最小日志样本量，低于该样本直接跳过（避免误触发）
    min_samples: int = 20


class HarvestResponse(BaseModel):
    created: int
    candidates: List[ExperienceRule]
    updated_at: str


# 进程内配置（简化版，可后续接入env/config中心）
auto_cfg = ExperienceAutoCandidateConfig()


@router.get("/auto-candidate/config", response_model=ExperienceAutoCandidateConfig)
async def get_auto_candidate_config():
    return auto_cfg


@router.put("/auto-candidate/config", response_model=ExperienceAutoCandidateConfig)
async def update_auto_candidate_config(cfg: ExperienceAutoCandidateConfig):
    # 覆盖式更新（简化），后续可改为局部PATCH
    global auto_cfg
    auto_cfg = cfg
    return auto_cfg


@router.post("/auto-candidate/harvest", response_model=HarvestResponse)
async def harvest_auto_candidates():
    cfg = auto_cfg
    # 开关未启用则不进行任何创建
    if not cfg.enabled:
        try:
            obs_logs.add(
                "INFO",
                "auto_candidate_harvest_skipped",
                module="experience",
                tags=["disabled"],
                extra={"created": 0, "since_seconds": cfg.since_seconds, "min_count": cfg.min_count},
            )
        except Exception:
            pass
        return HarvestResponse(created=0, candidates=[], updated_at=datetime.now(timezone.utc).isoformat())
    # 拉取最近日志，做 (module, level) 频次统计
    recent = obs_logs.search(since_seconds=max(1, int(cfg.since_seconds or 900)), limit=1000)
    # 样本量不足则跳过（但刷新 last_created gauge 为0，便于Dashboard呈现）
    if len(recent) < max(1, int(getattr(cfg, "min_samples", 20))):
        try:
            obs_metrics.set_gauge("experience_auto_candidate_last_created", 0.0)
            obs_logs.add(
                "INFO",
                "auto_candidate_harvest_skipped",
                module="experience",
                tags=["insufficient_samples"],
                extra={
                    "created": 0,
                    "samples": len(recent),
                    "required": int(getattr(cfg, "min_samples", 20)),
                    "since_seconds": cfg.since_seconds,
                    "min_count": cfg.min_count,
                },
            )
        except Exception:
            pass
        return HarvestResponse(created=0, candidates=[], updated_at=datetime.now(timezone.utc).isoformat())

    freq: Dict[str, int] = {}
    examples: Dict[str, str] = {}
    allow_levels = set([lvl.upper() for lvl in (cfg.include_levels or [])])
    for it in recent:
        level = (it.get("level") or "").upper()
        module = it.get("module") or "unknown"
        if level not in allow_levels:
            continue
        key = f"{module}:{level}"
        freq[key] = freq.get(key, 0) + 1
        if key not in examples:
            examples[key] = it.get("message") or ""
    # 生成候选并入库（草稿），满足阈值与数量限制
    ordered = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)
    created = 0
    added_candidates: List[ExperienceRule] = []
    for key, cnt in ordered:
        if created >= int(cfg.max_candidates or 10):
            break
        if cnt < int(cfg.min_count or 1):
            continue
        module, level = key.split(":", 1)
        title = f"{module} high-{level.lower()} frequency reflection"
        content = f"Observed {cnt} {level} logs in {module} within last {cfg.since_seconds}s."
        cand = ExperienceRule(
            id=str(uuid4()),
            title=title,
            content=content,
            status="draft",
            category="reflection",
            tags=[module, level, "auto"],
            fingerprint=hashlib.sha256(f"{module}|{level}|{cnt}|{cfg.since_seconds}".encode()).hexdigest()[:16],
        )
        before_cnt = sum(1 for r in store.list_all() if (r.status or "").lower() == "draft")
        added = store.add(cand, dedup=True, upsert=False)
        after_cnt = sum(1 for r in store.list_all() if (r.status or "").lower() == "draft")
        if after_cnt > before_cnt or added.fingerprint == cand.fingerprint:
            created += 1 if after_cnt > before_cnt else 0
            added_candidates.append(added)
    # 刷新候选数量 gauge
    cand_cnt = sum(1 for r in store.list_all() if (r.status or "").lower() == "draft")
    try:
        obs_metrics.inc("experience_auto_candidate_harvest_total", 1)
        obs_metrics.set_gauge("experience_candidates_total", float(cand_cnt))
        # 记录本次收割产生的候选数量，供 Dashboard 展示
        obs_metrics.set_gauge("experience_auto_candidate_last_created", float(created))
    except Exception:
        pass
    # 记录日志（附带来源分布，便于Dashboard提取）
    try:
        breakdown = [{"source": k, "count": v} for k, v in ordered[:5]]
        obs_logs.add(
            "INFO",
            "auto_candidate_harvest",
            module="experience",
            tags=["enabled", str(created)],
            extra={
                "created": created,
                "since_seconds": cfg.since_seconds,
                "min_count": cfg.min_count,
                "breakdown": breakdown,
            },
        )
    except Exception:
        pass
    return HarvestResponse(created=created, candidates=added_candidates, updated_at=datetime.now(timezone.utc).isoformat())

# Alias endpoints for productized API naming
@router.post("/candidates/auto", response_model=HarvestResponse)
async def candidates_auto_post():
    return await harvest_auto_candidates()

@router.get("/candidates/auto", response_model=HarvestResponse)
async def candidates_auto_get():
    return await harvest_auto_candidates()