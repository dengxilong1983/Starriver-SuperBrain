import time
import pytest
from fastapi.testclient import TestClient
from collections import deque
from app.routes.v2_3.observability import logs


@pytest.mark.integration
class TestObservabilityD4ToD7:
    def test_d4_asset_inventory(self, client: TestClient):
        # 调用资产盘点接口
        resp = client.get("/api/v2.3-preview/observability/assets", params={"since_seconds": 600})
        assert resp.status_code == 200
        data = resp.json()

        # 基本结构校验
        assert isinstance(data.get("modules"), list)
        assert isinstance(data.get("gauges"), dict)
        assert isinstance(data.get("counters"), dict)
        assert isinstance(data.get("timings"), dict)
        assert isinstance(data.get("experience_rules_total"), int)
        assert isinstance(data.get("experience_candidates_total"), int)
        assert isinstance(data.get("recent_logs"), int)
        assert isinstance(data.get("updated_at"), str)

    def test_d5_migration_plan_and_execute_poc(self, client: TestClient):
        # 生成迁移计划
        plan_body = {
            "source_version": "v2.2",
            "target_version": "v2.3",
            "dry_run": True,
            "scope": ["experience", "memory"],
        }
        plan_resp = client.post("/api/v2.3-preview/observability/migration/plan", json=plan_body)
        assert plan_resp.status_code == 200
        plan_data = plan_resp.json()
        assert isinstance(plan_data.get("steps"), list) and len(plan_data["steps"]) >= 1
        assert isinstance(plan_data.get("total_estimated_ms"), int)
        assert isinstance(plan_data.get("risks"), list) and len(plan_data["risks"]) >= 1
        assert plan_data.get("can_rollback") is True
        assert isinstance(plan_data.get("updated_at"), str)

        # 执行迁移（PoC：仅记录指标与日志）
        exec_resp = client.post("/api/v2.3-preview/observability/migration/execute", json=plan_body)
        assert exec_resp.status_code == 200
        exec_data = exec_resp.json()
        assert isinstance(exec_data.get("steps"), list) and len(exec_data["steps"]) >= 1

        # 验证迁移执行日志已记录（通过日志搜索 POST 变体）
        time.sleep(0.05)
        logs_resp = client.post(
            "/api/v2.3-preview/observability/logs/search",
            json={"query": "migration executed", "level": "INFO", "since_seconds": 300, "limit": 50},
        )
        assert logs_resp.status_code == 200
        logs_items = logs_resp.json().get("items", [])
        assert any("migration executed" in (it.get("message", "").lower()) for it in logs_items)

    def test_d6_dashboard_overview_tiles(self, client: TestClient):
        # 调用Dashboard概要接口
        resp = client.get("/api/v2.3-preview/observability/dashboard/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data.get("tiles"), list)
        # 构建一个键->value的字典便于断言
        tiles_map = {tile.get("key"): tile.get("value") for tile in data.get("tiles", [])}
        # 关键瓷砖存在
        for key in ["rules", "candidates", "http_p95_ms", "logs"]:
            assert key in tiles_map
        # 值类型合理（数字类型或可转为数字）
        assert isinstance(tiles_map["rules"], (int, float))
        assert isinstance(tiles_map["candidates"], (int, float))
        assert isinstance(tiles_map["http_p95_ms"], (int, float))
        assert isinstance(tiles_map["logs"], (int, float))

        # 新增：自动收割趋势与来源分布瓷砖存在且结构正确
        assert "auto_candidate_trend" in tiles_map
        assert "auto_candidate_sources_top" in tiles_map
        # 趋势为整数列表（允许为空）
        trend = tiles_map["auto_candidate_trend"]
        assert isinstance(trend, list)
        assert all(isinstance(x, int) for x in trend)
        # 来源Top为字典列表，包含 source(str) 与 count(int)
        sources = tiles_map["auto_candidate_sources_top"]
        assert isinstance(sources, list)
        for item in sources:
            assert isinstance(item, dict)
            assert "source" in item and isinstance(item["source"], str)
            assert "count" in item and isinstance(item["count"], int)

        assert isinstance(data.get("updated_at"), str)

    def test_d6_dashboard_sources_top_sanitization(self, client: TestClient):
        # 清空日志缓冲
        maxlen = logs._buf.maxlen
        logs._buf = deque(maxlen=maxlen)
        # 注入一次自动收割事件，包含异常的 breakdown 数据
        logs.add(
            "INFO",
            "auto_candidate_harvest",
            module="experience",
            tags=["harvest"],
            extra={
                "created": "5",
                "breakdown": [
                    {"source": "web", "count": 3},
                    {"source": None},  # 缺失count
                    {"source": "api", "count": "bad"},  # 非整型count
                ],
            },
        )
        # 调用dashboard，校验已被规范化
        resp = client.get("/api/v2.3-preview/observability/dashboard/overview")
        assert resp.status_code == 200
        tiles_map = {tile.get("key"): tile.get("value") for tile in resp.json().get("tiles", [])}
        sources = tiles_map.get("auto_candidate_sources_top", [])
        assert any(item.get("source") == "web" and item.get("count") == 3 for item in sources)
        assert any(item.get("source") == "None" and item.get("count") == 0 for item in sources)
        assert any(item.get("source") == "api" and item.get("count") == 0 for item in sources)

    def test_d7_reflection_suggestions_generated_from_warn_error(self, client: TestClient):
        # 通过制造 WARN/ERROR 级别日志来驱动建议生成：
        # 1) 无效的 attention 模式 -> WARN(400)
        client.post("/api/v2.3-preview/consciousness/attention", json={"mode": "oops", "target": "x"})
        # 2) 非法状态迁移：从 idle 直接到 executing -> WARN(409)
        client.post("/api/v2.3-preview/consciousness/state", json={"state": "executing", "force": False})
        # 再触发一次以提高频次
        client.post("/api/v2.3-preview/consciousness/state", json={"state": "executing", "force": False})

        # 稍等片刻，确保日志入缓冲
        time.sleep(0.05)

        # 获取反思建议
        sugg_resp = client.get(
            "/api/v2.3-preview/observability/reflection/suggestions",
            params={"since_seconds": 900, "limit": 5},
        )
        assert sugg_resp.status_code == 200
        sugg = sugg_resp.json()
        assert isinstance(sugg.get("count"), int)
        assert isinstance(sugg.get("suggestions"), list)

        # 期望至少有一条与 consciousness 模块相关的建议（WARN/ERROR聚合）
        has_consciousness = False
        for s in sugg.get("suggestions", []):
            # 基本结构
            assert "title" in s and isinstance(s["title"], str)
            assert "content" in s and isinstance(s["content"], str)
            assert "tags" in s and isinstance(s["tags"], list)
            assert "status" in s and s["status"] in ["draft"]
            # 识别模块标签
            if "consciousness" in s.get("tags", []):
                has_consciousness = True
        assert has_consciousness, "应至少包含针对 consciousness 模块的建议"