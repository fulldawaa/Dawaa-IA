import pytest

from raya import config, outils
from raya.outils import fichiers, navigation


@pytest.fixture(autouse=True)
def dossier_temporaire(tmp_path, monkeypatch):
    """Chaque test écrit dans un dossier temporaire, n'ouvre aucun fichier et ne fouille pas les vrais dossiers."""
    monkeypatch.setattr(config, "DOSSIER_DOCUMENTS", tmp_path / "Documents" / "Raya")
    monkeypatch.setattr(fichiers, "OUVRIR_AUTOMATIQUEMENT", False)
    personnels = {cle: tmp_path / "profil" / anglais for cle, (_, anglais, _) in fichiers.DOSSIERS_WINDOWS.items()}
    for d in personnels.values():
        d.mkdir(parents=True)
    monkeypatch.setattr(fichiers, "dossiers_personnels", lambda: personnels)
    monkeypatch.setattr(navigation.contexte, "derniere_demande", "")
    monkeypatch.setattr(outils, "journal", [])
    return tmp_path
