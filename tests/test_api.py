from fastapi.testclient import TestClient


def create(client: TestClient, smiles: str):
    r = client.post("/molecules/", json={"smiles": smiles})
    assert r.status_code == 201, r.text
    return r.json()


def test_crud_and_list(client: TestClient):
    m1 = create(client, "CCO")
    m2 = create(client, "c1ccccc1")

    # Get by id
    r = client.get(f"/molecules/{m1['id']}")
    assert r.status_code == 200
    assert r.json()["smiles"] == "CCO"

    # Get by id
    r = client.get(f"/molecules/{m2['id']}")
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
    create(client, "CCO")
    create(client, "c1ccccc1")
    create(client, "CC(=O)Oc1ccccc1C(=O)O")

    r1 = client.get("/substructure-search/?substructure=c1ccccc1")
    assert r1.status_code == 200
    data1 = r1.json()
    assert set(data1) == {"c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O"}

    # Second call should hit cache and return same result
    r2 = client.get("/substructure-search/?substructure=c1ccccc1")
    assert r2.status_code == 200
    assert set(r2.json()) == set(data1)


def test_duplicate_smiles_prevention(client: TestClient):
    r1 = client.post("/molecules/", json={"smiles": "CCO"})
    assert r1.status_code == 201
    mol1 = r1.json()
    assert mol1["smiles"] == "CCO"

    # Try to create duplicate - should fail with 409
    r2 = client.post("/molecules/", json={"smiles": "CCO"})
    assert r2.status_code == 409
    assert "already exists" in r2.json()["detail"]
