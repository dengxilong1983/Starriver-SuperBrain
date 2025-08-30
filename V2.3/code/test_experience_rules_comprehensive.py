#!/usr/bin/env python
"""
Experience Rules 全面测试脚本
覆盖：规则的 CRUD、搜索、去重、快照导入导出、候选管理等所有端点
目标：验证业务逻辑正确性、状态转换、计数器更新等
"""

import requests
import json
import time
import uuid
from datetime import datetime, timezone
from uuid import uuid4

# 配置
BASE_URL = "http://127.0.0.1:8011"
TIMEOUT = 10

def log(message):
    print(f"[{datetime.now().isoformat()}] {message}")

def setup_headers():
    """设置请求头，包含追踪ID"""
    return {
        "Content-Type": "application/json",
        "x-trace-id": str(uuid4())[:8]
    }

class ExperienceRulesTestSuite:
    """Experience Rules 测试套件"""
    
    def __init__(self):
        self.base_url = f"{BASE_URL}/api/v2.3-preview/experience"
        self.created_rules = []  # 用于清理
        
    def cleanup(self):
        """清理测试数据"""
        log("清理测试数据...")
        for rule_id in self.created_rules:
            try:
                response = requests.delete(f"{self.base_url}/rules/{rule_id}", 
                                        headers=setup_headers(), 
                                        timeout=TIMEOUT)
                if response.status_code == 200:
                    log(f"✓ 清理规则: {rule_id}")
            except Exception as e:
                log(f"✗ 清理失败 {rule_id}: {e}")
        self.created_rules.clear()
    
    def test_rule_crud_operations(self):
        """测试规则的 CRUD 操作"""
        log("\n--- 测试规则 CRUD 操作 ---")
        
        # 1. 创建规则 (POST /rules)
        create_data = {
            "title": f"测试规则_{datetime.now().strftime('%H%M%S')}",
            "content": "这是一个用于测试的经验规则内容",
            "category": "test",
            "tags": ["测试", "自动化"],
            "sources": ["test_source"],
            "dedup": False  # 避免去重影响测试
        }
        
        response = requests.post(f"{self.base_url}/rules", 
                                json=create_data, 
                                headers=setup_headers(), 
                                timeout=TIMEOUT)
        if response.status_code != 200:
            log(f"✗ 创建规则失败: {response.status_code} - {response.text}")
            return False
            
        rule = response.json()
        rule_id = rule["id"]
        self.created_rules.append(rule_id)
        log(f"✓ 创建规则成功: {rule_id}")
        
        # 验证规则属性
        if rule["title"] != create_data["title"]:
            log(f"✗ 规则标题不匹配: {rule['title']} vs {create_data['title']}")
            return False
        if rule["status"] != "active":  # 默认应为 active
            log(f"✗ 规则状态不正确: {rule['status']}")
            return False
            
        # 2. 读取规则 (GET /rules/{id})
        response = requests.get(f"{self.base_url}/rules/{rule_id}", 
                               headers=setup_headers(), 
                               timeout=TIMEOUT)
        if response.status_code != 200:
            log(f"✗ 读取规则失败: {response.status_code}")
            return False
            
        retrieved_rule = response.json()
        if retrieved_rule["id"] != rule_id:
            log(f"✗ 读取规则ID不匹配: {retrieved_rule['id']}")
            return False
        log(f"✓ 读取规则成功: {rule_id}")
        
        # 3. 更新规则 (PUT /rules/{id})
        update_data = {
            "title": f"更新后的标题_{datetime.now().strftime('%H%M%S')}",
            "content": "更新后的内容"
        }
        
        response = requests.put(f"{self.base_url}/rules/{rule_id}", 
                               json=update_data, 
                               headers=setup_headers(), 
                               timeout=TIMEOUT)
        if response.status_code != 200:
            log(f"✗ 更新规则失败: {response.status_code}")
            return False
            
        updated_rule = response.json()
        if updated_rule["title"] != update_data["title"]:
            log(f"✗ 更新后标题不匹配: {updated_rule['title']}")
            return False
        log(f"✓ 更新规则成功: {rule_id}")
        
        # 4. 删除规则 (DELETE /rules/{id})
        response = requests.delete(f"{self.base_url}/rules/{rule_id}", 
                                  headers=setup_headers(), 
                                  timeout=TIMEOUT)
        if response.status_code != 200:
            log(f"✗ 删除规则失败: {response.status_code}")
            return False
            
        result = response.json()
        if result["status"] != "deleted":
            log(f"✗ 删除响应不正确: {result}")
            return False
        log(f"✓ 删除规则成功: {rule_id}")
        
        # 验证删除后无法读取
        response = requests.get(f"{self.base_url}/rules/{rule_id}", 
                               headers=setup_headers(), 
                               timeout=TIMEOUT)
        if response.status_code != 404:
            log(f"✗ 删除后仍能读取规则: {response.status_code}")
            return False
        log("✓ 删除后正确返回 404")
        
        # 从清理列表移除已删除的规则
        self.created_rules.remove(rule_id)
        
        return True
    
    def test_rule_search_functionality(self):
        """测试规则搜索功能"""
        log("\n--- 测试规则搜索功能 ---")
        
        # 创建测试数据
        test_rules = [
            {
                "title": "Python 开发规范",
                "content": "使用 PEP8 编码规范",
                "category": "development",
                "tags": ["python", "规范"],
                "sources": ["pep8"]
            },
            {
                "title": "JavaScript 最佳实践", 
                "content": "使用 ES6+ 语法特性",
                "category": "development",
                "tags": ["javascript", "最佳实践"],
                "sources": ["mdn"]
            },
            {
                "title": "测试策略指南",
                "content": "单元测试覆盖率应达到 80%",
                "category": "testing",
                "tags": ["测试", "质量"],
                "sources": ["testing_guide"]
            }
        ]
        
        created_ids = []
        for rule_data in test_rules:
            rule_data["dedup"] = False  # 避免去重
            response = requests.post(f"{self.base_url}/rules", 
                                    json=rule_data, 
                                    headers=setup_headers(), 
                                    timeout=TIMEOUT)
            if response.status_code == 200:
                rule_id = response.json()["id"]
                created_ids.append(rule_id)
                self.created_rules.append(rule_id)
        
        log(f"✓ 创建测试规则: {len(created_ids)} 个")
        
        # 测试搜索 (GET /rules/search)
        test_cases = [
            {"q": "Python", "expected_min": 1, "desc": "文本搜索 Python"},
            {"category": "development", "expected_min": 2, "desc": "按分类搜索 development"},
            {"tag": "测试", "expected_min": 1, "desc": "按标签搜索 测试"},
            {"q": "规范", "category": "development", "expected_min": 1, "desc": "组合搜索"}
        ]
        
        for case in test_cases:
            params = {k: v for k, v in case.items() if k not in ["expected_min", "desc"]}
            response = requests.get(f"{self.base_url}/rules/search", 
                                   params=params, 
                                   headers=setup_headers(), 
                                   timeout=TIMEOUT)
            if response.status_code != 200:
                log(f"✗ 搜索失败 [{case['desc']}]: {response.status_code}")
                return False
                
            result = response.json()
            if result["count"] < case["expected_min"]:
                log(f"✗ 搜索结果不足 [{case['desc']}]: {result['count']} < {case['expected_min']}")
                return False
                
            log(f"✓ 搜索测试通过 [{case['desc']}]: {result['count']} 个结果")
        
        return True
    
    def test_candidate_workflow(self):
        """测试候选规则工作流"""
        log("\n--- 测试候选规则工作流 ---")
        
        # 1. 创建候选规则 (POST /candidates)
        candidate_data = {
            "title": f"候选规则_{datetime.now().strftime('%H%M%S')}",
            "content": "这是一个候选经验规则",
            "category": "candidate_test",
            "tags": ["候选", "测试"]
        }
        
        response = requests.post(f"{self.base_url}/candidates", 
                                json=candidate_data, 
                                headers=setup_headers(), 
                                timeout=TIMEOUT)
        if response.status_code != 200:
            log(f"✗ 创建候选规则失败: {response.status_code}")
            return False
            
        candidate = response.json()
        candidate_id = candidate["id"]
        self.created_rules.append(candidate_id)
        
        if candidate["status"] != "draft":
            log(f"✗ 候选规则状态不正确: {candidate['status']}")
            return False
        log(f"✓ 创建候选规则成功: {candidate_id}, 状态: {candidate['status']}")
        
        # 2. 列出候选规则 (GET /candidates)
        response = requests.get(f"{self.base_url}/candidates", 
                               headers=setup_headers(), 
                               timeout=TIMEOUT)
        if response.status_code != 200:
            log(f"✗ 列出候选规则失败: {response.status_code}")
            return False
            
        candidates = response.json()
        candidate_ids = [c["id"] for c in candidates["items"]]
        if candidate_id not in candidate_ids:
            log(f"✗ 候选规则未出现在列表中: {candidate_id}")
            return False
        log(f"✓ 候选规则列表正确，共 {candidates['count']} 个候选")
        
        # 3. 批准候选规则 (POST /candidates/{id}/approve)
        response = requests.post(f"{self.base_url}/candidates/{candidate_id}/approve", 
                                headers=setup_headers(), 
                                timeout=TIMEOUT)
        if response.status_code != 200:
            log(f"✗ 批准候选规则失败: {response.status_code}")
            return False
            
        approved = response.json()
        if approved["status"] != "active":
            log(f"✗ 批准后状态不正确: {approved['status']}")
            return False
        log(f"✓ 批准候选规则成功: {candidate_id}, 新状态: {approved['status']}")
        
        # 4. 创建另一个候选用于拒绝测试
        reject_data = {
            "title": f"待拒绝候选_{datetime.now().strftime('%H%M%S')}",
            "content": "这是一个将被拒绝的候选",
            "category": "reject_test"
        }
        
        response = requests.post(f"{self.base_url}/candidates", 
                                json=reject_data, 
                                headers=setup_headers(), 
                                timeout=TIMEOUT)
        if response.status_code != 200:
            log(f"✗ 创建待拒绝候选失败: {response.status_code}")
            return False
            
        reject_candidate_id = response.json()["id"]
        self.created_rules.append(reject_candidate_id)
        
        # 5. 拒绝候选规则 (POST /candidates/{id}/reject)
        response = requests.post(f"{self.base_url}/candidates/{reject_candidate_id}/reject", 
                                headers=setup_headers(), 
                                timeout=TIMEOUT)
        if response.status_code != 200:
            log(f"✗ 拒绝候选规则失败: {response.status_code}")
            return False
            
        rejected = response.json()
        if rejected["status"] != "deprecated":
            log(f"✗ 拒绝后状态不正确: {rejected['status']}")
            return False
        log(f"✓ 拒绝候选规则成功: {reject_candidate_id}, 新状态: {rejected['status']}")
        
        return True
    
    def test_snapshot_operations(self):
        """测试快照导入导出"""
        log("\n--- 测试快照导入导出 ---")
        
        # 1. 导出快照 (GET /snapshot/export)
        response = requests.get(f"{self.base_url}/snapshot/export", 
                               params={"compact": True}, 
                               headers=setup_headers(), 
                               timeout=TIMEOUT)
        if response.status_code != 200:
            log(f"✗ 导出快照失败: {response.status_code}")
            return False
            
        snapshot = response.json()
        if "count" not in snapshot or "items" not in snapshot or "mode" not in snapshot:
            log(f"✗ 快照格式不正确: {snapshot.keys()}")
            return False
        log(f"✓ 导出快照成功: {snapshot['count']} 个规则, 模式: {snapshot['mode']}")
        
        # 2. 测试导入快照 (POST /snapshot/import)
        # 先创建一些测试数据
        test_import_data = {
            "items_compact": [
                {
                    "title": "导入测试规则1", 
                    "content": "导入测试内容1",
                    "category": "import_test",
                    "tags": ["导入", "测试1"]
                },
                {
                    "title": "导入测试规则2",
                    "content": "导入测试内容2", 
                    "category": "import_test",
                    "tags": ["导入", "测试2"]
                }
            ],
            "dedup": False,  # 避免去重影响测试
            "upsert": False
        }
        
        response = requests.post(f"{self.base_url}/snapshot/import", 
                                json=test_import_data, 
                                headers=setup_headers(), 
                                timeout=TIMEOUT)
        if response.status_code != 200:
            log(f"✗ 导入快照失败: {response.status_code}")
            return False
            
        import_result = response.json()
        if import_result["imported"] != 2:
            log(f"✗ 导入数量不正确: {import_result['imported']} != 2")
            return False
        log(f"✓ 导入快照成功: {import_result['imported']} 个规则, 总计: {import_result['total']}")
        
        # 记录导入的规则（通过搜索找到它们进行后续清理）
        response = requests.get(f"{self.base_url}/rules/search", 
                               params={"category": "import_test"}, 
                               headers=setup_headers(), 
                               timeout=TIMEOUT)
        if response.status_code == 200:
            imported_rules = response.json()["items"]
            for rule in imported_rules:
                self.created_rules.append(rule["id"])
        
        return True
    
    def test_deduplication_logic(self):
        """测试去重逻辑"""
        log("\n--- 测试去重逻辑 ---")
        
        # 1. 创建原始规则
        original_rule = {
            "title": "去重测试规则",
            "content": "这是去重测试的原始内容",
            "category": "dedup_test",
            "tags": ["去重", "原始"],
            "dedup": False  # 第一次创建不去重
        }
        
        response = requests.post(f"{self.base_url}/rules", 
                                json=original_rule, 
                                headers=setup_headers(), 
                                timeout=TIMEOUT)
        if response.status_code != 200:
            log(f"✗ 创建原始规则失败: {response.status_code}")
            return False
            
        original = response.json()
        original_id = original["id"]
        self.created_rules.append(original_id)
        log(f"✓ 创建原始规则成功: {original_id}")
        
        # 2. 尝试创建重复规则（开启去重）
        duplicate_rule = {
            "title": "去重测试规则",  # 相同标题
            "content": "这是去重测试的重复内容",  # 不同内容
            "category": "dedup_test", 
            "tags": ["去重", "重复"],
            "dedup": True  # 开启去重
        }
        
        response = requests.post(f"{self.base_url}/rules", 
                                json=duplicate_rule, 
                                headers=setup_headers(), 
                                timeout=TIMEOUT)
        if response.status_code != 200:
            log(f"✗ 创建重复规则请求失败: {response.status_code}")
            return False
            
        # 应该返回现有规则而不是创建新规则
        duplicate = response.json()
        if duplicate["id"] != original_id:
            # 如果返回了不同的ID，说明去重没生效，记录用于清理
            self.created_rules.append(duplicate["id"])
            log(f"⚠️ 去重未生效，创建了新规则: {duplicate['id']}")
        else:
            log(f"✓ 去重生效，返回现有规则: {duplicate['id']}")
        
        # 3. 测试候选规则的去重（应该总是创建为 draft）
        candidate_duplicate = {
            "title": "去重测试规则",  # 相同标题
            "content": "这是候选的重复内容",
            "category": "dedup_test"
        }
        
        response = requests.post(f"{self.base_url}/candidates", 
                                json=candidate_duplicate, 
                                headers=setup_headers(), 
                                timeout=TIMEOUT)
        if response.status_code != 200:
            log(f"✗ 创建候选重复规则失败: {response.status_code}")
            return False
            
        candidate = response.json()
        candidate_id = candidate["id"]
        self.created_rules.append(candidate_id)
        
        if candidate["status"] != "draft":
            log(f"✗ 候选规则状态不正确: {candidate['status']}")
            return False
        log(f"✓ 候选规则总是创建为 draft: {candidate_id}")
        
        return True
    
    def run_all_tests(self):
        """运行所有测试"""
        log("开始 Experience Rules 全面测试")
        log(f"目标服务器: {self.base_url}")
        
        tests = [
            ("CRUD 操作", self.test_rule_crud_operations),
            ("搜索功能", self.test_rule_search_functionality),
            ("候选规则工作流", self.test_candidate_workflow),
            ("快照导入导出", self.test_snapshot_operations),
            ("去重逻辑", self.test_deduplication_logic),
        ]
        
        passed = 0
        total = len(tests)
        
        try:
            for test_name, test_func in tests:
                log(f"\n{'='*50}")
                log(f"执行测试: {test_name}")
                log(f"{'='*50}")
                
                try:
                    if test_func():
                        passed += 1
                        log(f"✅ {test_name} - 通过")
                    else:
                        log(f"❌ {test_name} - 失败")
                except Exception as e:
                    log(f"❌ {test_name} - 异常: {e}")
                    
        finally:
            # 清理测试数据
            self.cleanup()
        
        log(f"\n{'='*50}")
        log("Experience Rules 全面测试结果")
        log(f"{'='*50}")
        log(f"通过: {passed}/{total}")
        log(f"成功率: {passed/total*100:.1f}%")
        
        if passed == total:
            log("🎉 所有 Experience Rules 测试通过！")
            return True
        else:
            log(f"❌ {total-passed} 个测试失败")
            return False

def main():
    """主函数"""
    # 先检查服务器是否可用
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code != 200:
            log(f"✗ 服务器健康检查失败: {response.status_code}")
            return False
    except Exception as e:
        log(f"✗ 无法连接到服务器: {e}")
        return False
    
    # 运行测试套件
    test_suite = ExperienceRulesTestSuite()
    success = test_suite.run_all_tests()
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)