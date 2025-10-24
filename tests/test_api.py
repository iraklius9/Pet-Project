from typing import Any
from fastapi.testclient import TestClient

def create(client: TestClient, identifier: str, smiles: str) -> dict[str, Any]:
    r = client.post("/molecules/", json={"identifier": identifier, "smiles": smiles})
    assert r.status_code == 201, r.text
    return r.json()


def test_crud_and_list(client: TestClient):
    m1 = create(client, "mol1", "CCO")
    m2 = create(client, "mol2", "c1ccccc1")

    # Get by id
    r = client.get(f"/molecules/{m1['id']}")
    assert r.status_code == 200
    assert r.json()["identifier"] == "mol1"

    # Get by identifier
    r = client.get("/molecules/mol2")
    assert r.status_code == 200
    assert r.json()["smiles"] == "c1ccccc1"

    # Update
    r = client.put(f"/molecules/{m1['id']}", json={"smiles": "CCN"})
    assert r.status_code == 200
    assert r.json()["smiles"] == "CCN"

    # List limit
    r = client.get("/molecules/?limit=1")
    assert r.status_code == 200
    assert len(r.json()) == 1

    # Delete
    r = client.delete(f"/molecules/{m2['id']}")
    assert r.status_code == 204


def test_substructure_search_endpoint(client: TestClient):
    create(client, "m1", "CCO")
    create(client, "m2", "c1ccccc1")
    create(client, "m3", "CC(=O)Oc1ccccc1C(=O)O")

    r1 = client.get("/substructure-search/?substructure=c1ccccc1")
    assert r1.status_code == 200
    data1 = r1.json()
    assert set(data1) == {"c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O"}

    # Second call should hit cache and return same result
    r2 = client.get("/substructure-search/?substructure=c1ccccc1")
    assert r2.status_code == 200
    assert set(r2.json()) == set(data1)

