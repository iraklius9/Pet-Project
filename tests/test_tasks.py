import os
from fastapi.testclient import TestClient


def test_celery_task_endpoints(client: TestClient):
    # Ensure eager mode for predictable behavior
    os.environ["CELERY_TASK_ALWAYS_EAGER"] = "1"

    # Seed data
    client.post("/molecules/", json={"identifier": "m1", "smiles": "CCO"})
    client.post("/molecules/", json={"identifier": "m2", "smiles": "c1ccccc1"})

    r = client.post("/tasks/substructure", json={"substructure": "c1ccccc1"})
    assert r.status_code == 200
    task = r.json()
    assert "task_id" in task

    # In eager mode, status is likely SUCCESS and result may be unavailable via GET
    r2 = client.get(f"/tasks/{task['task_id']}")
    assert r2.status_code == 200
    data = r2.json()
    assert data["status"] in ("SUCCESS", "PENDING")

