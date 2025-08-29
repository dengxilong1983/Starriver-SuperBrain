"""
Integration tests for OpenAPI and documentation routes
验证 /openapi.json, /docs, /redoc, /docs-lite 的可用性与基础内容。
"""
import re
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture(scope="module")
def client_module():
    with TestClient(app) as c:
        yield c


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.smoke
def test_openapi_json_available(client_module: TestClient):
    resp = client_module.get("/openapi.json")
    assert resp.status_code == 200
    ct = resp.headers.get("content-type", "").lower()
    assert "application/json" in ct
    data = resp.json()
    # 基础结构断言
    assert "openapi" in data
    assert "paths" in data
    # 采样校验：确认已知端点存在（根据现有路由）
    paths = data.get("paths", {})
    # 这些端点来自现有实现（observability 与 experience）
    assert "/api/v2.3-preview/observability/metrics" in paths
    assert "/api/v2.3-preview/observability/logs/search" in paths


@pytest.mark.integration
@pytest.mark.api
def test_docs_custom_swagger_page(client_module: TestClient):
    resp = client_module.get("/docs")
    assert resp.status_code == 200
    ct = resp.headers.get("content-type", "").lower()
    assert "text/html" in ct or "text/plain" in ct  # 某些服务器会返回 text/plain; 兼容处理
    text = resp.text.lower()
    # 宽松匹配，避免对具体实现细节过于敏感
    assert ("swagger" in text) or ("openapi" in text) or ("ui" in text)


@pytest.mark.integration
@pytest.mark.api
def test_redoc_page(client_module: TestClient):
    resp = client_module.get("/redoc")
    assert resp.status_code == 200
    ct = resp.headers.get("content-type", "").lower()
    assert "text/html" in ct or "text/plain" in ct
    text = resp.text.lower()
    # Redoc 相关关键词
    assert ("redoc" in text) or ("openapi" in text)


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.smoke
def test_docs_lite_page(client_module: TestClient):
    resp = client_module.get("/docs-lite")
    assert resp.status_code == 200
    ct = resp.headers.get("content-type", "").lower()
    assert "text/html" in ct or "text/plain" in ct
    text = resp.text
    # 服务器端渲染的简化页面应包含 OpenAPI 摘要或 openapi 版本字段
    assert ("OpenAPI" in text) or ("openapi" in text)
    # 进一步检查是否包含 paths 或 components 等关键段落字样（非严格）
    assert re.search(r"paths|components|schemas", text, flags=re.IGNORECASE)