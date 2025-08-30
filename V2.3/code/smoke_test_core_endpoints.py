#!/usr/bin/env python
"""
核心端到端冒烟测试脚本 - V2.3
覆盖：cloud/status, observability/metrics, observability/logs/search, execution/act, reasoning/plan, memory/export
目标：验证接口可用性、返回格式正确、状态码符合预期
"""

import requests
import json
import time
from datetime import datetime

import os
# 配置
BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8230")
TIMEOUT = 10

def log(message):
    print(f"[{datetime.now().isoformat()}] {message}")

def test_cloud_status():
    """测试 /api/v2.3-preview/cloud/status 接口"""
    url = f"{BASE_URL}/api/v2.3-preview/cloud/status"
    log(f"测试 cloud/status - GET {url}")
    
    try:
        # 无用户ID时应返回204 No Content
        response = requests.get(url, timeout=TIMEOUT)
        if response.status_code == 204:
            log("✓ cloud/status (无user_id) - 204 No Content")
        else:
            log(f"✗ cloud/status 预期204，实际{response.status_code}")
            return False
        
        # 带用户ID时应返回状态信息
        response = requests.get(url, params={"user_id": "test_user"}, timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            if "status" in data and "consent_active" in data and "scopes" in data:
                log(f"✓ cloud/status (user_id=test_user) - 200 OK, status={data['status']}")
            else:
                log(f"✗ cloud/status 响应格式不正确: {data}")
                return False
        else:
            log(f"✗ cloud/status 带user_id失败: {response.status_code}")
            return False
        
        return True
    except Exception as e:
        log(f"✗ cloud/status 异常: {e}")
        return False

def test_observability_metrics():
    """测试 /api/v2.3-preview/observability/metrics 接口"""
    url = f"{BASE_URL}/api/v2.3-preview/observability/metrics"
    log(f"测试 observability/metrics - GET {url}")
    
    try:
        response = requests.get(url, timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            required_fields = ["counters", "timings", "gauges", "labels", "updated_at"]
            if all(field in data for field in required_fields):
                log(f"✓ observability/metrics - 200 OK, counters={len(data.get('counters', {}))}")
            else:
                log(f"✗ observability/metrics 响应格式不正确: {data}")
                return False
        else:
            log(f"✗ observability/metrics 失败: {response.status_code}")
            return False
        
        return True
    except Exception as e:
        log(f"✗ observability/metrics 异常: {e}")
        return False

def test_observability_logs_search():
    """测试 /api/v2.3-preview/observability/logs/search 接口"""
    url = f"{BASE_URL}/api/v2.3-preview/observability/logs/search"
    log(f"测试 observability/logs/search - GET {url}")
    
    try:
        # GET 请求
        response = requests.get(url, params={"limit": 10}, timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            if "count" in data and "returned" in data and "items" in data:
                log(f"✓ observability/logs/search (GET) - 200 OK, count={data['count']}")
            else:
                log(f"✗ observability/logs/search GET 响应格式不正确: {data}")
                return False
        else:
            log(f"✗ observability/logs/search GET 失败: {response.status_code}")
            return False
        
        # POST 请求
        post_data = {"query": "INFO", "limit": 5}
        response = requests.post(url, json=post_data, timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            if "count" in data and "items" in data:
                log(f"✓ observability/logs/search (POST) - 200 OK, count={data['count']}")
            else:
                log(f"✗ observability/logs/search POST 响应格式不正确: {data}")
                return False
        else:
            log(f"✗ observability/logs/search POST 失败: {response.status_code}")
            return False
        
        return True
    except Exception as e:
        log(f"✗ observability/logs/search 异常: {e}")
        return False

def test_execution_act():
    """测试 /api/v2.3-preview/execution/act 接口"""
    url = f"{BASE_URL}/api/v2.3-preview/execution/act"
    log(f"测试 execution/act - POST {url}")
    
    try:
        post_data = {
            "action": "test_action",
            "params": {"key": "value", "count": 42}
        }
        response = requests.post(url, json=post_data, timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            if "success" in data and "output" in data:
                log(f"✓ execution/act - 200 OK, success={data['success']}")
            else:
                log(f"✗ execution/act 响应格式不正确: {data}")
                return False
        else:
            log(f"✗ execution/act 失败: {response.status_code}")
            return False
        
        return True
    except Exception as e:
        log(f"✗ execution/act 异常: {e}")
        return False

def test_reasoning_plan():
    """测试 /api/v2.3-preview/reasoning/plan 接口"""
    url = f"{BASE_URL}/api/v2.3-preview/reasoning/plan"
    log(f"测试 reasoning/plan - POST {url}")
    
    try:
        post_data = {
            "goal": "完成一个简单任务",
            "constraints": ["时间限制", "资源限制"],
            "max_steps": 3
        }
        response = requests.post(url, json=post_data, timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            if "plan_id" in data and "steps" in data:
                steps_count = len(data.get("steps", []))
                log(f"✓ reasoning/plan - 200 OK, plan_id={data['plan_id'][:8]}..., steps={steps_count}")
            else:
                log(f"✗ reasoning/plan 响应格式不正确: {data}")
                return False
        else:
            log(f"✗ reasoning/plan 失败: {response.status_code}")
            return False
        
        return True
    except Exception as e:
        log(f"✗ reasoning/plan 异常: {e}")
        return False

def test_memory_export():
    """测试 /api/v2.3-preview/memory/export 接口"""
    url = f"{BASE_URL}/api/v2.3-preview/memory/export"
    log(f"测试 memory/export - GET {url}")
    
    try:
        # GET 请求
        response = requests.get(url, timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            if "export_url" in data and "expires_at" in data:
                log(f"✓ memory/export (GET) - 200 OK, export_url={data['export_url']}")
            else:
                log(f"✗ memory/export GET 响应格式不正确: {data}")
                return False
        else:
            log(f"✗ memory/export GET 失败: {response.status_code}")
            return False
        
        # POST 请求
        post_data = {"format": "json", "limit": 100}
        response = requests.post(url, json=post_data, timeout=TIMEOUT)
        if response.status_code == 200:
            data = response.json()
            if "export_url" in data and "expires_at" in data:
                log(f"✓ memory/export (POST) - 200 OK, export_url={data['export_url']}")
            else:
                log(f"✗ memory/export POST 响应格式不正确: {data}")
                return False
        else:
            log(f"✗ memory/export POST 失败: {response.status_code}")
            return False
        
        return True
    except Exception as e:
        log(f"✗ memory/export 异常: {e}")
        return False

def main():
    """执行所有冒烟测试"""
    log("开始核心端点冒烟测试")
    log(f"目标服务器: {BASE_URL}")
    
    # 先检查健康状态
    try:
        health_response = requests.get(f"{BASE_URL}/health", timeout=5)
        if health_response.status_code == 200:
            log("✓ 健康检查通过")
        else:
            log(f"✗ 健康检查失败: {health_response.status_code}")
            return False
    except Exception as e:
        log(f"✗ 无法连接到服务器: {e}")
        return False
    
    # 执行各项测试
    tests = [
        ("cloud/status", test_cloud_status),
        ("observability/metrics", test_observability_metrics),
        ("observability/logs/search", test_observability_logs_search),
        ("execution/act", test_execution_act),
        ("reasoning/plan", test_reasoning_plan),
        ("memory/export", test_memory_export),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        log(f"\n--- 测试 {test_name} ---")
        try:
            if test_func():
                passed += 1
                log(f"✓ {test_name} 通过")
            else:
                log(f"✗ {test_name} 失败")
        except Exception as e:
            log(f"✗ {test_name} 异常: {e}")
    
    log(f"\n=== 冒烟测试结果 ===")
    log(f"通过: {passed}/{total}")
    log(f"成功率: {passed/total*100:.1f}%")
    
    if passed == total:
        log("🎉 所有核心端点冒烟测试通过！")
        return True
    else:
        log(f"❌ {total-passed} 个测试失败")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)