import os
from fastapi.testclient import TestClient


def test_celery_task_endpoints(client: TestClient):
    os.environ["CELERY_TASK_ALWAYS_EAGER"] = "1"

    client.post("/molecules/", json={"smiles": "CCO"})
    client.post("/molecules/", json={"smiles": "c1ccccc1"})

    r = client.post("/tasks/substructure", json={"substructure": "c1ccccc1"})
    assert r.status_code == 200
    task = r.json()
    assert "task_id" in task

    r2 = client.get(f"/tasks/{task['task_id']}")
    assert r2.status_code == 200
    data = r2.json()
    assert data["status"] in ("SUCCESS", "PENDING")
