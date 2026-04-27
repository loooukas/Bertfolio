from __future__ import annotations

from fastapi.testclient import TestClient

from finbert_site import main
from finbert_site.main import app


def test_create_analyze_job_endpoint(monkeypatch):
    monkeypatch.setattr(
        main.job_manager,
        "create_job",
        lambda **kwargs: {
            "job_id": "job_123",
            "ticker": kwargs.get("ticker"),
            "status": "queued",
            "progress": {"percent": 0.0, "stages": []},
            "created_at": "2026-04-20T00:00:00Z",
            "updated_at": "2026-04-20T00:00:00Z",
            "error": None,
        },
    )

    client = TestClient(app)
    response = client.post("/api/analyze/jobs", json={"ticker": "aapl"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == "job_123"
    assert payload["ticker"] == "AAPL"
    assert payload["status"] == "queued"


def test_get_analyze_job_not_found(monkeypatch):
    monkeypatch.setattr(main.job_manager, "get_job", lambda *args, **kwargs: None)

    client = TestClient(app)
    response = client.get("/api/analyze/jobs/missing")

    assert response.status_code == 404


def test_get_analyze_result_endpoint(monkeypatch):
    monkeypatch.setattr(
        main.job_manager,
        "get_job",
        lambda *args, **kwargs: {
            "job_id": "job_123",
            "status": "completed",
            "result": {"ticker": "AAPL"},
        },
    )

    client = TestClient(app)
    response = client.get("/api/analyze/jobs/job_123/result")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["result"]["ticker"] == "AAPL"
