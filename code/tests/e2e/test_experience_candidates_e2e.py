"""
Experience Candidates E2E Test Suite
测试候选规则的完整生命周期流程，包括指标验证。
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.mark.e2e
class TestExperienceCandidatesE2E:
    """Experience Candidates End-to-End Test Cases"""
    
    @pytest.fixture
    def client(self):
        """FastAPI test client fixture"""
        with TestClient(app) as client:
            yield client
    
    def get_metrics(self, client: TestClient):
        """Helper: Get observability metrics"""
        response = client.get("/api/v2.3-preview/observability/metrics")
        response.raise_for_status()
        return response.json()
    
    def find_candidate_in_list(self, items, candidate_id):
        """Helper: Check if candidate exists in list"""
        return any(item.get("id") == candidate_id for item in items)
    
    def test_candidate_full_lifecycle(self, client):
        """
        Test complete candidate lifecycle: add → list → approve → verify removal
        Includes metrics validation at each step
        """
        # Baseline metrics snapshot
        metrics_baseline = self.get_metrics(client)
        counters_baseline = metrics_baseline.get("counters", {})
        gauges_baseline = metrics_baseline.get("gauges", {})
        candidates_baseline = float(gauges_baseline.get("experience_candidates_total", 0.0))
        add_count_baseline = int(counters_baseline.get("experience_candidate_added_total", 0))
        approve_count_baseline = int(counters_baseline.get("experience_candidate_approved_total", 0))
        
        # Step 1: Add candidate
        candidate_payload = {
            "title": "E2E Pytest Candidate Test",
            "content": "if user says hello, respond politely with pytest style.",
            "tags": ["e2e", "pytest", "candidate"],
            "category": "testing",
        }
        
        response = client.post("/api/v2.3-preview/experience/candidates", json=candidate_payload)
        assert response.status_code == 200, f"Failed to create candidate: {response.text}"
        
        candidate = response.json()
        candidate_id = candidate.get("id")
        assert candidate_id, "Candidate ID missing in response"
        assert candidate.get("status") == "draft", f"Expected draft status, got {candidate.get('status')}"
        
        # Verify metrics after add
        metrics_after_add = self.get_metrics(client)
        counters_after_add = metrics_after_add.get("counters", {})
        gauges_after_add = metrics_after_add.get("gauges", {})
        candidates_after_add = float(gauges_after_add.get("experience_candidates_total", 0.0))
        add_count_after_add = int(counters_after_add.get("experience_candidate_added_total", 0))
        
        assert add_count_after_add == add_count_baseline + 1, \
            f"Add counter not incremented: {add_count_baseline} -> {add_count_after_add}"
        assert candidates_after_add >= candidates_baseline + 1 - 1e-6, \
            f"Candidates gauge not increased: {candidates_baseline} -> {candidates_after_add}"
        
        # Step 2: List candidates and verify presence
        response = client.get("/api/v2.3-preview/experience/candidates")
        assert response.status_code == 200, f"Failed to list candidates: {response.text}"
        
        data = response.json()
        candidates_list = data.get("items", [])
        assert self.find_candidate_in_list(candidates_list, candidate_id), \
            f"Candidate {candidate_id} not found in list"
        
        # Step 3: Approve candidate
        response = client.post(f"/api/v2.3-preview/experience/candidates/{candidate_id}/approve")
        assert response.status_code == 200, f"Failed to approve candidate: {response.text}"
        
        approved_candidate = response.json()
        assert approved_candidate.get("status") == "active", \
            f"Expected active status after approval, got {approved_candidate.get('status')}"
        
        # Verify metrics after approval
        metrics_after_approve = self.get_metrics(client)
        counters_after_approve = metrics_after_approve.get("counters", {})
        gauges_after_approve = metrics_after_approve.get("gauges", {})
        candidates_after_approve = float(gauges_after_approve.get("experience_candidates_total", 0.0))
        approve_count_after_approve = int(counters_after_approve.get("experience_candidate_approved_total", 0))
        
        assert approve_count_after_approve == approve_count_baseline + 1, \
            f"Approve counter not incremented: {approve_count_baseline} -> {approve_count_after_approve}"
        assert candidates_after_approve <= candidates_after_add + 1e-6 and \
               candidates_after_approve >= candidates_baseline - 1e-6, \
            f"Candidates gauge not decreased after approval: {candidates_after_add} -> {candidates_after_approve}"
        
        # Step 4: Verify candidate removed from list after approval
        response = client.get("/api/v2.3-preview/experience/candidates")
        assert response.status_code == 200, f"Failed to list candidates after approval: {response.text}"
        
        data = response.json()
        final_candidates_list = data.get("items", [])
        assert not self.find_candidate_in_list(final_candidates_list, candidate_id), \
            f"Approved candidate {candidate_id} still in candidate list"
    
    @pytest.mark.parametrize("candidate_data", [
        {
            "title": "Parametrized Test A",
            "content": "Test content A with parametrization",
            "tags": ["param", "test_a"],
            "category": "automation"
        },
        {
            "title": "Parametrized Test B", 
            "content": "Test content B with different parameters",
            "tags": ["param", "test_b"],
            "category": "validation"
        }
    ])
    def test_candidate_creation_variations(self, client, candidate_data):
        """Test candidate creation with different parameter sets"""
        response = client.post("/api/v2.3-preview/experience/candidates", json=candidate_data)
        assert response.status_code == 200, f"Failed to create candidate: {response.text}"
        
        candidate = response.json()
        assert candidate.get("title") == candidate_data["title"]
        assert candidate.get("content") == candidate_data["content"]
        assert candidate.get("status") == "draft"
        
        # Cleanup: approve to remove from candidates list
        candidate_id = candidate.get("id")
        if candidate_id:
            client.post(f"/api/v2.3-preview/experience/candidates/{candidate_id}/approve")
    
    def test_candidate_list_pagination_and_filtering(self, client):
        """Test candidate list endpoint with various parameters"""
        # Test basic list
        response = client.get("/api/v2.3-preview/experience/candidates")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        
        # Test with limit parameter
        response = client.get("/api/v2.3-preview/experience/candidates?limit=1")
        assert response.status_code == 200
        data = response.json()
        items = data.get("items", [])
        assert len(items) <= 1
        
        # Test with offset parameter
        response = client.get("/api/v2.3-preview/experience/candidates?offset=0&limit=5")
        assert response.status_code == 200
    
    def test_candidate_approval_error_cases(self, client):
        """Test candidate approval error handling"""
        # Test approval of non-existent candidate
        non_existent_id = "non-existent-candidate-id"
        response = client.post(f"/api/v2.3-preview/experience/candidates/{non_existent_id}/approve")
        # Should handle gracefully (404 or similar)
        assert response.status_code in [404, 422, 500]  # Accept various error codes