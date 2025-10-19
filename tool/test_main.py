"""
Comprehensive test suite for main.py FastAPI application
"""
import pytest
import json
import asyncio
import os
from pathlib import Path
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from httpx import AsyncClient
import tempfile
import shutil
import uuid

# Import the app and models
from main import (
    app, 
    TaskRequest, 
    RunStatus, 
    RunResult,
    fake_openrouter_parse,
    fake_gemini_probe,
    fake_suggestion_llm,
    RUNS_DIR
)


class TestModels:
    """Test Pydantic models validation"""
    
    def test_task_request_defaults(self):
        """Test TaskRequest with default values"""
        request = TaskRequest()
        assert request.instruction == "probe around the website to find errors or suggest improvements"
        # Note: target_url now uses environment variable with fallback
        assert request.target_url in ["http://localhost:5173", os.getenv("DEFAULT_TARGET_URL", "http://localhost:5173")]
    
    def test_task_request_custom_values(self):
        """Test TaskRequest with custom values"""
        request = TaskRequest(
            instruction="test custom instruction",
            target_url="https://example.com"
        )
        assert request.instruction == "test custom instruction"
        assert request.target_url == "https://example.com"
    
    def test_run_status_defaults(self):
        """Test RunStatus with default values"""
        status = RunStatus(run_id="test-id", status="running")
        assert status.run_id == "test-id"
        assert status.status == "running"
        assert status.step == 0
        assert status.message == "starting..."
        assert status.errors == []
    
    def test_run_status_custom_values(self):
        """Test RunStatus with custom values"""
        status = RunStatus(
            run_id="test-id",
            status="completed",
            step=5,
            message="test message",
            errors=["error1", "error2"]
        )
        assert status.run_id == "test-id"
        assert status.status == "completed"
        assert status.step == 5
        assert status.message == "test message"
        assert status.errors == ["error1", "error2"]
    
    def test_run_result_creation(self):
        """Test RunResult creation"""
        result = RunResult(
            run_id="test-id",
            success=True,
            observations=[{"step": 1, "action": "navigate"}],
            suggestions=[{"title": "Fix bug", "why": "Important", "how": "Do this"}],
            screenshots=["screenshot1.png"]
        )
        assert result.run_id == "test-id"
        assert result.success is True
        assert len(result.observations) == 1
        assert len(result.suggestions) == 1
        assert len(result.screenshots) == 1


class TestHelperFunctions:
    """Test helper functions"""
    
    @pytest.mark.asyncio
    async def test_fake_openrouter_parse(self):
        """Test fake_openrouter_parse function"""
        result = await fake_openrouter_parse("test instruction")
        
        assert isinstance(result, dict)
        assert "target_url" in result
        assert "goals" in result
        assert "max_steps" in result
        assert result["target_url"] == "http://localhost:5173"
        assert isinstance(result["goals"], list)
        assert isinstance(result["max_steps"], int)
        assert result["max_steps"] == 3
    
    @pytest.mark.asyncio
    async def test_fake_gemini_probe(self):
        """Test fake_gemini_probe function"""
        run_id = "test-run-id"
        spec = {
            "target_url": "http://localhost:5173",
            "goals": ["test goal"],
            "max_steps": 2
        }
        
        results = await fake_gemini_probe(run_id, spec)
        
        assert isinstance(results, list)
        assert len(results) == 2
        
        for i, obs in enumerate(results):
            assert obs["step"] == i + 1
            assert "actions" in obs
            assert "screenshot" in obs
            assert "issues_found" in obs
            assert obs["screenshot"] == f"step-{i + 1}.png"
            assert isinstance(obs["issues_found"], list)
    
    @pytest.mark.asyncio
    async def test_fake_suggestion_llm(self):
        """Test fake_suggestion_llm function"""
        observations = [
            {"step": 1, "issues_found": [{"type": "broken_link"}]},
            {"step": 2, "issues_found": [{"type": "missing_alt"}]}
        ]
        
        suggestions = await fake_suggestion_llm(observations)
        
        assert isinstance(suggestions, list)
        assert len(suggestions) == 2
        
        for suggestion in suggestions:
            assert "title" in suggestion
            assert "why" in suggestion
            assert "how" in suggestion


class TestFastAPIEndpoints:
    """Test FastAPI endpoints"""
    
    @pytest.fixture
    def client(self):
        """Create test client"""
        return TestClient(app)
    
    @pytest.fixture
    def temp_runs_dir(self, tmp_path):
        """Create temporary runs directory"""
        original_runs_dir = RUNS_DIR
        temp_dir = tmp_path / "runs"
        temp_dir.mkdir()
        
        # Patch the RUNS_DIR
        with patch('main.RUNS_DIR', temp_dir):
            yield temp_dir
        
        # Cleanup
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
    
    def test_start_run_default_request(self, client, temp_runs_dir):
        """Test starting a run with default request"""
        response = client.post("/runs", json={})
        
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "completed"
        
        # Verify run directory was created
        run_id = data["run_id"]
        run_dir = temp_runs_dir / run_id
        assert run_dir.exists()
        assert (run_dir / "status.json").exists()
        assert (run_dir / "result.json").exists()
    
    def test_start_run_custom_request(self, client, temp_runs_dir):
        """Test starting a run with custom request"""
        request_data = {
            "instruction": "Find all broken links on the homepage",
            "target_url": "https://example.com"
        }
        
        response = client.post("/runs", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "completed"
    
    def test_start_run_invalid_json(self, client):
        """Test starting a run with invalid JSON"""
        response = client.post("/runs", json={"invalid_field": "value"})
        
        # Should still work due to default values
        assert response.status_code == 200
    
    def test_get_status_existing_run(self, client, temp_runs_dir):
        """Test getting status of existing run"""
        # First create a run
        response = client.post("/runs", json={})
        run_id = response.json()["run_id"]
        
        # Then get its status
        status_response = client.get(f"/runs/{run_id}/status")
        
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["run_id"] == run_id
        assert status_data["status"] == "completed"
    
    def test_get_status_nonexistent_run(self, client):
        """Test getting status of non-existent run"""
        fake_run_id = str(uuid.uuid4())
        response = client.get(f"/runs/{fake_run_id}/status")
        
        assert response.status_code == 404
        assert "Run not found" in response.json()["detail"]
    
    def test_get_result_existing_run(self, client, temp_runs_dir):
        """Test getting result of existing run"""
        # First create a run
        response = client.post("/runs", json={})
        run_id = response.json()["run_id"]
        
        # Then get its result
        result_response = client.get(f"/runs/{run_id}/result")
        
        assert result_response.status_code == 200
        result_data = result_response.json()
        assert result_data["run_id"] == run_id
        assert result_data["success"] is True
        assert "observations" in result_data
        assert "suggestions" in result_data
        assert "screenshots" in result_data
    
    def test_get_result_nonexistent_run(self, client):
        """Test getting result of non-existent run"""
        fake_run_id = str(uuid.uuid4())
        response = client.get(f"/runs/{fake_run_id}/result")
        
        assert response.status_code == 404
        assert "Run result not found" in response.json()["detail"]


class TestAsyncOperations:
    """Test async operations and concurrency"""
    
    @pytest.mark.asyncio
    async def test_concurrent_runs(self, temp_runs_dir):
        """Test multiple concurrent runs"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Start multiple runs concurrently
            tasks = []
            for i in range(3):
                task = ac.post("/runs", json={"instruction": f"test {i}"})
                tasks.append(task)
            
            responses = await asyncio.gather(*tasks)
            
            # All should succeed
            for response in responses:
                assert response.status_code == 200
                data = response.json()
                assert "run_id" in data
                assert data["status"] == "completed"
    
    @pytest.mark.asyncio
    async def test_async_helper_functions_timing(self):
        """Test that async helper functions have proper timing"""
        import time
        
        start_time = time.time()
        await fake_openrouter_parse("test")
        openrouter_time = time.time() - start_time
        
        # Should take at least 0.5 seconds due to asyncio.sleep(0.5)
        assert openrouter_time >= 0.5
        
        start_time = time.time()
        await fake_suggestion_llm([])
        suggestion_time = time.time() - start_time
        
        # Should take at least 0.5 seconds due to asyncio.sleep(0.5)
        assert suggestion_time >= 0.5


class TestErrorHandling:
    """Test error handling and edge cases"""
    
    def test_invalid_run_id_format(self, client):
        """Test with invalid run ID format"""
        response = client.get("/runs/invalid-id/status")
        assert response.status_code == 404
    
    def test_empty_instruction(self, client, temp_runs_dir):
        """Test with empty instruction"""
        response = client.post("/runs", json={"instruction": ""})
        assert response.status_code == 200  # Should still work with defaults
    
    def test_malformed_json(self, client):
        """Test with malformed JSON"""
        response = client.post("/runs", data="invalid json", 
                             headers={"Content-Type": "application/json"})
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.asyncio
    async def test_helper_function_error_handling(self):
        """Test helper functions with edge cases"""
        # Test with empty instruction
        result = await fake_openrouter_parse("")
        assert isinstance(result, dict)
        
        # Test with None spec
        with pytest.raises((KeyError, TypeError)):
            await fake_gemini_probe("test", None)
        
        # Test with empty observations
        suggestions = await fake_suggestion_llm([])
        assert isinstance(suggestions, list)


class TestFileOperations:
    """Test file operations and persistence"""
    
    def test_run_directory_creation(self, client, temp_runs_dir):
        """Test that run directories are created properly"""
        response = client.post("/runs", json={})
        run_id = response.json()["run_id"]
        
        run_dir = temp_runs_dir / run_id
        assert run_dir.exists()
        assert run_dir.is_dir()
    
    def test_status_file_creation(self, client, temp_runs_dir):
        """Test that status files are created and updated"""
        response = client.post("/runs", json={})
        run_id = response.json()["run_id"]
        
        run_dir = temp_runs_dir / run_id
        status_file = run_dir / "status.json"
        
        assert status_file.exists()
        status_data = json.loads(status_file.read_text())
        assert status_data["run_id"] == run_id
        assert status_data["status"] == "completed"
    
    def test_result_file_creation(self, client, temp_runs_dir):
        """Test that result files are created properly"""
        response = client.post("/runs", json={})
        run_id = response.json()["run_id"]
        
        run_dir = temp_runs_dir / run_id
        result_file = run_dir / "result.json"
        
        assert result_file.exists()
        result_data = json.loads(result_file.read_text())
        assert result_data["run_id"] == run_id
        assert result_data["success"] is True
        assert "observations" in result_data
        assert "suggestions" in result_data
        assert "screenshots" in result_data


class TestIntegration:
    """Integration tests"""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self, temp_runs_dir):
        """Test complete workflow from start to finish"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Start a run
            response = await ac.post("/runs", json={
                "instruction": "Find all accessibility issues",
                "target_url": "https://example.com"
            })
            
            assert response.status_code == 200
            run_id = response.json()["run_id"]
            
            # Check status
            status_response = await ac.get(f"/runs/{run_id}/status")
            assert status_response.status_code == 200
            assert status_response.json()["status"] == "completed"
            
            # Get result
            result_response = await ac.get(f"/runs/{run_id}/result")
            assert result_response.status_code == 200
            result_data = result_response.json()
            
            # Verify result structure
            assert result_data["run_id"] == run_id
            assert result_data["success"] is True
            assert len(result_data["observations"]) > 0
            assert len(result_data["suggestions"]) > 0
            assert len(result_data["screenshots"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
