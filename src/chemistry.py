from rdkit import Chem
from rdkit.Chem import DataStructs
from typing import Optional


def validate_smiles(smiles: str):
    if not smiles or not isinstance(smiles, str):
        return False

    try:
        return Chem.MolFromSmiles(smiles) is not None
    except Exception:
        return False


def substructure_search(molecules: list[str], substructure: str, limit: Optional[int] = None):
    if not substructure:
        return []

    return _substructure_search_rdkit(molecules, substructure, limit)


def _substructure_search_rdkit(molecules: list[str], substructure: str, limit: Optional[int] = None):
    pattern = Chem.MolFromSmarts(substructure)
    is_smarts = pattern is not None
    if not pattern:
        pattern = Chem.MolFromSmiles(substructure)
    if not pattern:
        return []

    pattern_fp = None
    try:
        if is_smarts:
            try:
                Chem.SanitizeMol(pattern)
                pattern_smiles = Chem.MolToSmiles(pattern)
                pattern_for_fp = Chem.MolFromSmiles(pattern_smiles)
            except Exception:
                pattern_for_fp = pattern

            try:
                if pattern_for_fp is not None:
                    pattern_fp = Chem.RDKFingerprint(pattern_for_fp, fpSize=2048)
            except Exception:
                pattern_fp = None
        else:
            pattern_for_fp = pattern

            try:
                pattern_fp = Chem.RDKFingerprint(pattern_for_fp, fpSize=2048)
            except Exception:
                pattern_fp = None
    except Exception:
        pattern_fp = None

    hits = []
    for smiles in molecules:
        try:
            mol = Chem.MolFromSmiles(smiles)
            if not mol:
                continue

            if pattern_fp is not None:
                try:
                    mol_fp = Chem.RDKFingerprint(mol, fpSize=2048)
                    if not DataStructs.AllProbeBitsMatch(pattern_fp, mol_fp):
                        continue
                except Exception:
                    pass

            if mol.HasSubstructMatch(pattern):
                hits.append(smiles)
                if limit is not None and len(hits) >= limit:
                    break
        except Exception:
            continue
    return hits
