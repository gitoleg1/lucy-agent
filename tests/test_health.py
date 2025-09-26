from starlette.testclient import TestClient

from lucy_agent.main import app


def test_health_endpoint_ok():
    """
    טסט בסיסי שמוודא שה־/health מחזיר 200 וגוף JSON עם {"status": "ok"}.
    """
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert data.get("status") == "ok"
