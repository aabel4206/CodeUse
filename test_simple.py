"""
Simple test to debug fixture issues
"""
import pytest
from fastapi.testclient import TestClient
from main import app

@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)

def test_simple_endpoint(client):
    """Test a simple endpoint"""
    response = client.post("/runs", json={})
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert data["status"] == "completed"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
