from src.chemistry import substructure_search


def test_substructure_search_basic():
    molecules = [
        "CCO",
        "c1ccccc1",
        "CC(=O)O",
        "CC(=O)Oc1ccccc1C(=O)O",
    ]
    hits = substructure_search(molecules, "c1ccccc1")
    assert set(hits) == {"c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O"}


def test_substructure_invalid_input():
    assert substructure_search(["CCO"], "") == []
    assert substructure_search(["CCO"], "invalid$$$") == []
