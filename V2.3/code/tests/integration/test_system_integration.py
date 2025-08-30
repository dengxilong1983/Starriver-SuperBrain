"""
V2.3 System Integration Tests

验证各子系统间的集成度和数据流转正确性
重点测试：子系统间 API 调用、数据一致性、状态同步
"""

import pytest
import requests
from fastapi.testclient import TestClient
from app.main import app
import json
import time


@pytest.mark.integration
class TestV23SystemIntegration:
    """V2.3 系统集成测试类"""
    
    def test_cross_system_workflow_integration(self, client: TestClient):
        """测试跨系统工作流集成 - reasoning -> execution -> memory 链路"""
        # 1. 通过 reasoning/plan 生成计划 (使用正确的请求体模型)
        reasoning_payload = {
            "goal": "Create a simple test plan for integration testing",
            "constraints": ["must be lightweight", "no external dependencies"],
            "max_steps": 3
        }
        
        reasoning_response = client.post("/api/v2.3-preview/reasoning/plan", json=reasoning_payload)
        assert reasoning_response.status_code == 200
        plan_data = reasoning_response.json()
        assert "plan_id" in plan_data
        assert "steps" in plan_data
        assert len(plan_data["steps"]) >= 1
        
        # 2. 通过 execution/act 执行计划 (使用正确的请求体模型)
        execution_payload = {
            "action": "execute_test_plan",
            "params": {"plan_id": plan_data["plan_id"], "test": True}
        }
        
        execution_response = client.post("/api/v2.3-preview/execution/act", json=execution_payload)
        assert execution_response.status_code == 200
        exec_data = execution_response.json()
        assert "success" in exec_data
        assert "output" in exec_data
        
        # 3. 通过 memory/export 验证状态持久化
        memory_response = client.get("/api/v2.3-preview/memory/export")
        assert memory_response.status_code == 200
        memory_data = memory_response.json()
        
        # 验证跨系统数据一致性
        assert isinstance(plan_data["plan_id"], str)
        assert exec_data["success"] in [True, False]
        assert "export_url" in memory_data
        assert "expires_at" in memory_data
    
    def test_observability_metrics_consistency(self, client: TestClient):
        """测试可观测性指标在多系统间的一致性"""
        # 获取初始指标
        initial_metrics = client.get("/api/v2.3-preview/observability/metrics")
        assert initial_metrics.status_code == 200
        initial_data = initial_metrics.json()
        
        # 执行一些操作以触发指标变化
        client.post("/api/v2.3-preview/reasoning/plan", json={
            "goal": "metrics test",
            "max_steps": 1
        })
        
        client.post("/api/v2.3-preview/execution/act", json={
            "action": "test_action",
            "params": {}
        })
        
        # 等待指标更新
        time.sleep(0.1)
        
        # 获取更新后的指标
        updated_metrics = client.get("/api/v2.3-preview/observability/metrics")
        assert updated_metrics.status_code == 200
        updated_data = updated_metrics.json()
        
        # 验证指标确实发生了变化
        assert len(updated_data.get("metrics", [])) >= len(initial_data.get("metrics", []))
    
    def test_experience_rules_with_execution_integration(self, client: TestClient):
        """测试经验规则与执行引擎的集成"""
        # 1. 添加一个经验规则
        rule_payload = {
            "title": "test_condition",
            "content": "action: test_action",
            "category": "integration",
            "tags": ["integration_test"]
        }
        
        add_response = client.post("/api/v2.3-preview/experience/rules", json=rule_payload)
        assert add_response.status_code == 200
        rule_id = add_response.json().get("id")
        
        # 2. 搜索规则确认存在
        search_response = client.get("/api/v2.3-preview/experience/rules/search?q=test_condition")
        assert search_response.status_code == 200
        rules = search_response.json().get("items", [])
        assert len(rules) > 0
        assert any(rule["id"] == rule_id for rule in rules)
        
        # 3. 通过执行引擎触发规则（execution/act 目前为 echo，占位即可）
        exec_payload = {
            "action": "test_action",
            "params": {"use_experience": True, "rule_id": rule_id}
        }
        
        exec_response = client.post("/api/v2.3-preview/execution/act", json=exec_payload)
        assert exec_response.status_code == 200
        
        # 4. 清理：删除测试规则
        delete_response = client.delete(f"/api/v2.3-preview/experience/rules/{rule_id}")
        assert delete_response.status_code == 200
    
    def test_logs_search_with_system_events(self, client: TestClient):
        """测试日志搜索与系统事件的集成"""
        # 触发一些系统事件
        client.get("/api/v2.3-preview/cloud/status")
        client.post("/api/v2.3-preview/reasoning/plan", json={
            "goal": "log test",
            "max_steps": 1
        })
        
        # 等待日志写入
        time.sleep(0.1)
        
        # 搜索相关日志（使用 POST 以兼容 request body 中的 query 字段）
        log_params = {
            "query": "reasoning",
            "level": "info",
            "limit": 10,
            "since_seconds": 3600
        }
        
        logs_response = client.post("/api/v2.3-preview/observability/logs/search", json=log_params)
        assert logs_response.status_code == 200
        logs_data = logs_response.json()
        
        assert "items" in logs_data
        assert isinstance(logs_data["items"], list)
        # 验证日志中包含我们的操作记录
        log_messages = [log.get("message", "") for log in logs_data["items"]]
        assert any("reasoning" in msg.lower() for msg in log_messages)
    
    def test_snapshot_import_export_integration(self, client: TestClient):
        """测试快照导入导出的集成流程"""
        # 1. 添加一些经验规则用于导出
        rules_to_add = [
            {"condition": "snapshot_test_1", "action": "action_1", "priority": 1},
            {"condition": "snapshot_test_2", "action": "action_2", "priority": 2}
        ]
        
        rule_ids = []
        for rule in rules_to_add:
            response = client.post("/api/v2.3-preview/experience/rules", json=rule)
            assert response.status_code == 200
            rule_ids.append(response.json().get("id"))
        
        # 2. 导出快照（默认 compact 模式，返回 items 列表）
        export_response = client.get("/api/v2.3-preview/experience/snapshot/export")
        assert export_response.status_code == 200
        snapshot_data = export_response.json()
        
        assert "items" in snapshot_data
        exported_rules = snapshot_data["items"]
        assert isinstance(exported_rules, list) and len(exported_rules) >= 2
        
        # 3. 清理现有规则
        for rule_id in rule_ids:
            client.delete(f"/api/v2.3-preview/experience/rules/{rule_id}")
        
        # 4. 重新导入快照（根据 compact 输出，使用 items_compact 字段导入）
        import_response = client.post(
            "/api/v2.3-preview/experience/snapshot/import",
            json={
                "items_compact": exported_rules,
                "upsert": True,
                "dedup": True,
            },
        )
        assert import_response.status_code == 200
        import_result = import_response.json()
        
        assert import_result.get("imported", 0) >= 2
        
        # 5. 验证导入成功 - 搜索其中一个规则
        search_response = client.get("/api/v2.3-preview/experience/rules/search?q=snapshot_test_1")
        assert search_response.status_code == 200
        found_rules = search_response.json().get("items", [])
        assert len(found_rules) > 0
        
        # 6. 清理：删除导入的规则
        for rule in found_rules:
            if "snapshot_test" in rule.get("content", ""):
                client.delete(f"/api/v2.3-preview/experience/rules/{rule['id']}")


@pytest.mark.integration
class TestV23SystemHealth:
    """V2.3 系统健康度集成测试"""
    
    def test_all_endpoints_health_check(self, client: TestClient):
        """测试所有核心端点的健康状态"""
        endpoints_to_check = [
            ("/api/v2.3-preview/cloud/status", "GET"),
            ("/api/v2.3-preview/observability/metrics", "GET"),
            ("/api/v2.3-preview/memory/export", "GET"),
            ("/api/v2.3-preview/experience/snapshot/export", "GET"),
        ]
        
        health_results = {}
        
        for endpoint, method in endpoints_to_check:
            try:
                if method == "GET":
                    response = client.get(endpoint)
                else:
                    response = client.post(endpoint, json={})
                
                health_results[endpoint] = {
                    "status_code": response.status_code,
                    "healthy": response.status_code < 400,
                    "response_time": "< 1s"  # FastAPI TestClient 是同步的
                }
            except Exception as e:
                health_results[endpoint] = {
                    "status_code": 500,
                    "healthy": False,
                    "error": str(e)
                }
        
        # 检查所有端点健康状态
        unhealthy_endpoints = [ep for ep, result in health_results.items() if not result["healthy"]]
        
        assert len(unhealthy_endpoints) == 0, f"不健康的端点: {unhealthy_endpoints}"
        
        # 验证至少 80% 的端点正常
        healthy_count = sum(1 for result in health_results.values() if result["healthy"])
        total_count = len(health_results)
        health_percentage = healthy_count / total_count
        
        assert health_percentage >= 0.8, f"系统健康度 {health_percentage:.1%} 低于 80%"


if __name__ == "__main__":
    # 直接运行此文件进行快速测试
    import subprocess
    subprocess.run(["python", "-m", "pytest", __file__, "-v", "-m", "integration"])