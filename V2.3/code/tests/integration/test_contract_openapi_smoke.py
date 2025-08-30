import warnings
# Suppress known jsonschema deprecation warnings triggered by Schemathesis import
warnings.filterwarnings("ignore", message="jsonschema.RefResolver is deprecated", category=DeprecationWarning)
warnings.filterwarnings("ignore", message="jsonschema.exceptions.RefResolutionError is deprecated", category=DeprecationWarning)

import pytest
import schemathesis
from hypothesis import settings

from app.main import create_app


# Create a single ASGI app instance for the whole module
app = create_app()

# Bind Schemathesis to the in-memory ASGI app using its OpenAPI schema
schema = schemathesis.from_asgi("/openapi.json", app)


@schema.parametrize()
@settings(max_examples=3, deadline=1500)
def test_openapi_contract_get_smoke(case):
    # Only smoke-test GET operations to keep scope minimal
    if case.method != "GET":
        pytest.skip("Only smoke-test GET operations")
    # Perform the request against the ASGI app and validate the response
    case.call_and_validate()


@schema.parametrize()
@settings(max_examples=2, deadline=1500)
def test_openapi_contract_observability_constraints(case):
    # 仅对 observability 两个关键GET端点做结构约束校验
    if case.method != "GET":
        pytest.skip("Only GET operations are constrained here")
    if case.path not in [
        "/api/v2.3-preview/observability/assets",
        "/api/v2.3-preview/observability/dashboard/overview",
    ]:
        pytest.skip("Skip non-observability constraints")
    # 调用并进行内置schema验证
    response = case.call_and_validate()
    assert 200 <= response.status_code < 300
    data = response.json()
    if case.path.endswith("/assets"):
        assert isinstance(data.get("modules"), list)
        assert isinstance(data.get("gauges"), dict)
        assert isinstance(data.get("counters"), dict)
        assert isinstance(data.get("timings"), dict)
        assert isinstance(data.get("experience_rules_total"), int)
        assert isinstance(data.get("experience_candidates_total"), int)
        assert isinstance(data.get("recent_logs"), int)
        assert isinstance(data.get("updated_at"), str)
    else:
        # dashboard overview
        assert isinstance(data.get("tiles"), list)
        tiles_map = {tile.get("key"): tile.get("value") for tile in data.get("tiles", [])}
        for key in ["rules", "candidates", "http_p95_ms", "logs", "auto_candidate_trend", "auto_candidate_sources_top"]:
            assert key in tiles_map
        assert isinstance(data.get("updated_at"), str)