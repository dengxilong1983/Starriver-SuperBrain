import os
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import (
    get_swagger_ui_html,
    get_redoc_html,
    get_swagger_ui_oauth2_redirect_html,
)
from fastapi.responses import HTMLResponse
from fastapi.openapi.utils import get_openapi

from .routes.health import router as health_router
from .routes.v2_3.consciousness import router as consciousness_router
from .routes.v2_3.memory import router as memory_router
from .routes.v2_3.reasoning import router as reasoning_router
from .routes.v2_3.execution import router as execution_router
from .routes.v2_3.cloud import router as cloud_router
from .routes.v2_3.observability import (
    router as observability_router,
    metrics as obs_metrics,
    logs as obs_logs,
)
from .routes.v2_3.experience import router as experience_router
from .routes.v2_3.experience import store as exp_store, ExperienceRule
from .routes.v2_3.agents import router as agents_router

from uuid import uuid4

from .errors import register_exception_handlers  # NEW


SERVICE_NAME = "starriver-superbrain-v2.3"
API_VERSION = "v2.3-preview"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    path = getattr(app.state, "experience_snapshot_path", "data/experience.snapshot.json")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            items_compact = data.get("items_compact") or []
            items_full = data.get("items") or []
            items = [ExperienceRule.from_compact(d) for d in items_compact] if items_compact else [ExperienceRule(**d) for d in items_full]
            ok, dup = exp_store.import_items(items, upsert=True, dedup=True)
            cnt, _ = exp_store.stats()
            try:
                obs_metrics.inc("experience_snapshot_load_total", 1)
                obs_metrics.set_gauge("experience_rules_total", float(cnt))
                # also refresh candidate (draft) gauge after load
                cand_cnt = sum(1 for r in exp_store.list_all() if (r.status or "").lower() == "draft")
                obs_metrics.set_gauge("experience_candidates_total", float(cand_cnt))
            except Exception:
                pass
            try:
                obs_logs.add(
                    "INFO",
                    f"experience snapshot loaded ok={ok} dup={dup} cnt={cnt}",
                    module="experience",
                    tags=["snapshot", "load"],
                    extra={"path": path},
                )
            except Exception:
                pass
        else:
            try:
                obs_logs.add(
                    "INFO",
                    "experience snapshot not found; skip load",
                    module="experience",
                    tags=["snapshot", "load_skip"],
                    extra={"path": path},
                )
            except Exception:
                pass
    except Exception as e:
        try:
            obs_logs.add(
                "ERROR",
                f"experience snapshot load failed: {e}",
                module="experience",
                tags=["snapshot", "load_error"],
                extra={"path": path},
            )
        except Exception:
            pass
    
    yield
    
    # Shutdown
    try:
        items = exp_store.list_all()
        payload = {
            "items_compact": [r.to_compact() for r in items],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "version": API_VERSION,
        }
        # ensure directory
        try:
            dirn = os.path.dirname(path)
            if dirn:
                os.makedirs(dirn, exist_ok=True)
        except Exception:
            pass
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
        try:
            obs_metrics.inc("experience_snapshot_save_total", 1)
            obs_metrics.set_gauge("experience_snapshot_items", float(len(items)))
        except Exception:
            pass
        try:
            obs_logs.add(
                "INFO",
                f"experience snapshot saved items={len(items)}",
                module="experience",
                tags=["snapshot", "save"],
                extra={"path": path},
            )
        except Exception:
            pass
    except Exception as e:
        try:
            obs_logs.add(
                "ERROR",
                f"experience snapshot save failed: {e}",
                module="experience",
                tags=["snapshot", "save_error"],
                extra={"path": path},
            )
        except Exception:
            pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="Starriver SuperBrain API",
        version=API_VERSION,
        description="Minimal runnable V2.3 API skeleton",
        lifespan=lifespan,
        docs_url=None,   # disable default Swagger UI
        redoc_url=None,  # disable default ReDoc
        openapi_version="3.0.3",
    )

    # Ensure OpenAPI schema version is 3.0.3 for better tooling compatibility (e.g., Schemathesis)
    def custom_openapi():
        if getattr(app, "openapi_schema", None):
            return app.openapi_schema
        openapi_schema = get_openapi(
            title=app.title,
            version=API_VERSION,
            description=app.description,
            routes=app.routes,
        )
        openapi_schema["openapi"] = "3.0.3"
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi
    # Register global error handlers (unified errors)
    register_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Meta & health
    app.include_router(health_router)

    # V2.3 Preview APIs
    app.include_router(consciousness_router)
    app.include_router(memory_router)
    app.include_router(reasoning_router)
    app.include_router(execution_router)
    app.include_router(cloud_router)
    app.include_router(experience_router)
    app.include_router(observability_router)
    app.include_router(agents_router)

    # ---- Experience snapshot auto load/save (P0) ----
    app.state.experience_snapshot_path = os.getenv("EXPERIENCE_SNAPSHOT_PATH", "data/experience.snapshot.json")

    # ---- Observability middleware (v0) ----
    import time

    @app.middleware("http")
    async def observability_middleware(request, call_next):
        start = time.perf_counter()
        method = request.method
        path = request.url.path
        status = 500
        # trace id propagation
        trace_id = request.headers.get("x-trace-id") or str(uuid4())
        setattr(request.state, "trace_id", trace_id)
        try:
            response = await call_next(request)
            status = getattr(response, "status_code", 200)
            # set trace id header
            try:
                response.headers["x-trace-id"] = trace_id
            except Exception:
                pass
            return response
        except Exception as e:  # record error and re-raise
            try:
                obs_logs.add(
                    "ERROR",
                    f"Unhandled error: {e}",
                    module="http",
                    tags=["exception", method, path, trace_id],
                    extra={"trace_id": trace_id},
                )
            except Exception:
                pass
            raise
        finally:
            dur_ms = (time.perf_counter() - start) * 1000.0
            try:
                obs_metrics.inc(f"http_requests_total|{method}|{path}|{status}", 1)
                obs_metrics.observe(f"http_request_duration_ms|{method}|{path}", dur_ms)
                level = "INFO" if status < 400 else ("WARN" if status < 500 else "ERROR")
                obs_logs.add(
                    level,
                    f"{method} {path} -> {status} in {dur_ms:.2f}ms",
                    module="http",
                    tags=[method, path, str(status), trace_id],
                    extra={"duration_ms": round(dur_ms, 2), "trace_id": trace_id},
                )
            except Exception:
                # best-effort; never block request on metrics/logging
                pass

    @app.get("/", tags=["meta"]) 
    def root():
        return {"service": SERVICE_NAME, "version": API_VERSION, "status": "ok"}

    # ---- Custom Docs (use unpkg CDN as fallback to jsDelivr) ----
    @app.get("/docs", include_in_schema=False)
    def custom_swagger_ui():
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=app.title + " - Swagger UI",
            oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
            swagger_js_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js",
            swagger_css_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css",
        )

    @app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
    def swagger_ui_redirect():
        return get_swagger_ui_oauth2_redirect_html()

    @app.get("/redoc", include_in_schema=False)
    def redoc_html():
        return get_redoc_html(
            openapi_url=app.openapi_url,
            title=app.title + " - ReDoc",
            redoc_js_url="https://unpkg.com/redoc@next/bundles/redoc.standalone.js",
        )

    # ---- Docs Lite (Offline-friendly) ----
    @app.get("/docs-lite", include_in_schema=False)
    def docs_lite() -> HTMLResponse:
        try:
            schema = app.openapi()
        except Exception as e:
            schema = {"error": f"failed to generate openapi: {e}"}
        paths_len = len((schema.get("paths") or {})) if isinstance(schema, dict) else 0
        tags_list = ", ".join([str(t.get("name", "")) for t in (schema.get("tags") or [])]) if isinstance(schema, dict) else ""
        info = schema.get("info", {}) if isinstance(schema, dict) else {}
        title_val = info.get("title", "")
        version_val = info.get("version", "")
        meta_text = f"title: {title_val}\nversion: {version_val}\npaths: {paths_len}\ntags: {tags_list}"
        try:
            raw_json = json.dumps(schema, ensure_ascii=False, indent=2)
        except Exception:
            raw_json = str(schema)
        if len(raw_json) > 4000:
            raw_json = raw_json[:4000] + "\n..."
        html = (
            "<!doctype html>\n"
            "<html lang=\"zh-CN\">\n"
            "<head>\n"
            "<meta charset=\"utf-8\" />\n"
            "<title>" + app.title + " - Docs Lite</title>\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
            "<style>\n"
            "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', 'PingFang SC', 'Microsoft YaHei', sans-serif; margin: 0; padding: 0; background: #0b1020; color: #e6e9ef; }\n"
            "header { padding: 16px 20px; border-bottom: 1px solid #1f2a44; background: #0e1530; position: sticky; top: 0; z-index: 1; }\n"
            "header h1 { font-size: 18px; margin: 0; }\n"
            "main { padding: 16px 20px; }\n"
            ".card { background: #0e1428; border: 1px solid #1d2744; border-radius: 10px; padding: 16px; margin-bottom: 16px; }\n"
            "small, code, pre { color: #b8c1ec; }\n"
            "pre { white-space: pre-wrap; word-wrap: break-word; background: #0b1224; padding: 12px; border-radius: 8px; border: 1px solid #182143; max-height: 50vh; overflow: auto; }\n"
            "a { color: #80caff; }\n"
            ".badge { display: inline-block; padding: 2px 8px; border-radius: 999px; border: 1px solid #324164; color: #8fb0ff; font-size: 12px; }\n"
            ".kv span { display: inline-block; min-width: 120px; color: #9fb1d1; }\n"
            ".footer { opacity: .7; font-size: 12px; margin-top: 20px; }\n"
            "</style>\n"
            "</head>\n"
            "<body>\n"
            "<header>\n"
            "  <h1>" + app.title + " <span class=\"badge\">" + API_VERSION + "</span></h1>\n"
            "</header>\n"
            "<main>\n"
            "  <div class=\"card\">\n"
            "    <div class=\"kv\"><span>OpenAPI:</span> <a href=\"" + app.openapi_url + "\">" + app.openapi_url + "</a></div>\n"
            "    <div class=\"kv\"><span>Swagger UI:</span> <a href=\"/docs\">/docs</a>（如网络受限可能显示空白）</div>\n"
            "    <div class=\"kv\"><span>ReDoc:</span> <a href=\"/redoc\">/redoc</a>（如网络受限可能显示空白）</div>\n"
            "  </div>\n"
            "  <div class=\"card\">\n"
            "    <div style=\"margin-bottom:8px\"><strong>OpenAPI 摘要</strong></div>\n"
            "    <pre id=\"meta\">" + meta_text + "</pre>\n"
            "  </div>\n"
            "  <div class=\"card\">\n"
            "    <div style=\"margin-bottom:8px\"><strong>原始 JSON 片段</strong></div>\n"
            "    <pre id=\"raw\">" + raw_json + "</pre>\n"
            "  </div>\n"
            "  <div class=\"footer\">离线模式无需外部CDN。若需完整交互式文档，请在可联网环境访问 /docs 或 /redoc。</div>\n"
            "</main>\n"
            "</body>\n"
            "</html>\n"
        )
        return HTMLResponse(content=html)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8230")),
        reload=os.getenv("RELOAD", "true").lower() == "true",
    )