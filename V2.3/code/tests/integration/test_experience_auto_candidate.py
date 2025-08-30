"""
Integration tests for Experience Auto-Candidate (C3 MVP)
- /auto-candidate/config (GET/PUT)
- /auto-candidate/harvest (POST)
- /dashboard/overview tile for auto-harvest created count
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


# Real route prefixes from routers
EXP_PREFIX = "/api/v2.3-preview/experience"
OBS_PREFIX = "/api/v2.3-preview/observability"


@pytest.fixture(scope="module")
def client_module():
    with TestClient(app) as c:
        yield c


def _get_dashboard_tiles(client: TestClient):
    r = client.get(f"{OBS_PREFIX}/dashboard/overview")
    assert r.status_code == 200
    data = r.json()
    assert "tiles" in data and isinstance(data["tiles"], list)
    return data["tiles"], data


def _find_tile(tiles, key: str):
    for t in tiles:
        if t.get("key") == key:
            return t
    return None


def test_auto_candidate_config_get_put(client_module: TestClient):
    # GET default config
    r = client_module.get(f"{EXP_PREFIX}/auto-candidate/config")
    assert r.status_code == 200
    cfg = r.json()
    # Basic schema checks
    for k in [
        "enabled",
        "min_count",
        "include_levels",
        "since_seconds",
        "min_confidence",
        "max_candidates",
    ]:
        assert k in cfg
    assert isinstance(cfg["include_levels"], list)

    # PUT update config
    new_cfg = {
        "enabled": False,
        "min_count": 2,
        "include_levels": ["WARN", "ERROR"],
        "since_seconds": 600,
        "min_confidence": 0.5,
        "max_candidates": 10,
    }
    r2 = client_module.put(f"{EXP_PREFIX}/auto-candidate/config", json=new_cfg)
    assert r2.status_code == 200
    cfg2 = r2.json()
    # Echo checks
    for k, v in new_cfg.items():
        assert cfg2[k] == v


def test_auto_candidate_harvest_disabled(client_module: TestClient):
    # Ensure disabled
    client_module.put(
        f"{EXP_PREFIX}/auto-candidate/config",
        json={
            "enabled": False,
            "min_count": 2,
            "include_levels": ["WARN", "ERROR"],
            "since_seconds": 600,
            "min_confidence": 0.4,
            "max_candidates": 5,
        },
    )

    # Harvest (should be skipped and return zero created)
    resp = client_module.post(f"{EXP_PREFIX}/auto-candidate/harvest")
    assert resp.status_code == 200
    body = resp.json()
    assert "created" in body and isinstance(body["created"], int)
    assert body["created"] == 0
    assert "candidates" in body and isinstance(body["candidates"], list)


def test_dashboard_tile_auto_candidate_last_created_exists(client_module: TestClient):
    # Before: read dashboard
    tiles_before, _ = _get_dashboard_tiles(client_module)
    tile_before = _find_tile(tiles_before, "auto_candidate_last_created")
    # Tile should exist and have integer value (>=0)
    assert tile_before is not None
    assert isinstance(tile_before.get("value"), int)

    # Enable and run harvest once (may produce 0 if no WARN/ERROR logs in buffer)
    client_module.put(
        f"{EXP_PREFIX}/auto-candidate/config",
        json={
            "enabled": True,
            "min_count": 1,
            "include_levels": ["WARN", "ERROR"],
            "since_seconds": 3600,
            "min_confidence": 0.0,
            "max_candidates": 5,
        },
    )
    harvest_resp = client_module.post(f"{EXP_PREFIX}/auto-candidate/harvest")
    assert harvest_resp.status_code == 200
    created_now = harvest_resp.json().get("created", 0)

    # After: dashboard value should reflect last created count
    tiles_after, _ = _get_dashboard_tiles(client_module)
    tile_after = _find_tile(tiles_after, "auto_candidate_last_created")
    assert tile_after is not None
    assert isinstance(tile_after.get("value"), int)
    assert tile_after["value"] == int(created_now)