"""
Pytest Configuration for V2.3 Tests
提供通用的测试 fixtures 和配置
"""
import pytest
from fastapi.testclient import TestClient

# 确保 'app' 包可被导入（兼容不同工作目录运行 pytest 的情况）
import sys
from pathlib import Path
_CODE_DIR = Path(__file__).resolve().parent.parent
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

from app.main import app


@pytest.fixture(scope="session")
def test_client():
    """Session-scoped test client for FastAPI app"""
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="function")  
def fresh_client():
    """Function-scoped test client (new instance per test)"""
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="function")
def client(fresh_client):
    """Alias for function-scoped FastAPI TestClient to maintain backward compatibility with tests expecting `client` fixture."""
    return fresh_client


def pytest_configure(config):
    """Register custom markers for test categorization"""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")  
    config.addinivalue_line("markers", "e2e: End-to-end tests")
    config.addinivalue_line("markers", "smoke: Smoke tests")
    config.addinivalue_line("markers", "slow: Slow-running tests")
    config.addinivalue_line("markers", "api: API endpoint tests")
    config.addinivalue_line("markers", "metrics: Tests involving observability metrics")