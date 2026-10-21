"""Historique des conversations, stocké localement dans SQLite."""
import json
import sqlite3
import threading
import time
from pathlib import Path

from raya import config

MAX_CONVERSATIONS = 5  # au-delà, les plus anciennes sont effacées


class Historique:
    def __init__(self, chemin: Path | None = None):
        chemin = chemin or config.FICHIER_HISTORIQUE
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self._verrou = threading.Lock()
        self._db = sqlite3.connect(chemin, check_same_thread=False)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titre TEXT NOT NULL,
                messages TEXT NOT NULL,
                modifiee REAL NOT NULL
            )""")
        colonnes = {c[1] for c in self._db.execute("PRAGMA table_info(conversations)")}
        if "resume" not in colonnes:  # ajout de la mémoire des conversations (v0.2)
            self._db.execute("ALTER TABLE conversations ADD COLUMN resume TEXT")
            self._db.execute("ALTER TABLE conversations ADD COLUMN resume_maj REAL")
        self._limiter()  # historiques enregistrés avant la limite
        self._db.commit()

    def _limiter(self) -> None:
        """Ne garde que les MAX_CONVERSATIONS conversations les plus récentes (verrou déjà pris ou inutile)."""
        self._db.execute("DELETE FROM conversations WHERE id NOT IN "
                         "(SELECT id FROM conversations ORDER BY modifiee DESC, id DESC LIMIT ?)", (MAX_CONVERSATIONS,))

    def a_resumer(self, sauf: int | None, limite: int = 5) -> list[int]:
        """Conversations récentes dont le résumé est absent ou périmé (hors conversation en cours)."""
        with self._verrou:
            lignes = self._db.execute(
                "SELECT id FROM conversations WHERE (resume_maj IS NULL OR resume_maj < modifiee) AND id != ? "
                "ORDER BY modifiee DESC LIMIT ?", (sauf if sauf is not None else -1, limite)).fetchall()
        return [i for (i,) in lignes]

    def definir_resume(self, id_: int, resume: str) -> None:
        with self._verrou:
            # Le résumé vaut pour la version actuelle : il redevient périmé dès que la conversation change
            self._db.execute("UPDATE conversations SET resume = ?, resume_maj = modifiee WHERE id = ?", (resume, id_))
            self._db.commit()

    def resumes_recents(self, nombre: int = 5) -> list[tuple[float, str]]:
        with self._verrou:
            return self._db.execute(
                "SELECT modifiee, resume FROM conversations WHERE resume IS NOT NULL AND resume != '' "
                "ORDER BY modifiee DESC LIMIT ?", (nombre,)).fetchall()

    def lister(self, limite: int = 50) -> list[dict]:
        with self._verrou:
            lignes = self._db.execute(
                "SELECT id, titre, modifiee FROM conversations ORDER BY modifiee DESC, id DESC LIMIT ?", (limite,)
            ).fetchall()
        return [{"id": i, "titre": t, "modifiee": m} for i, t, m in lignes]

    def charger(self, id_: int) -> list[dict]:
        with self._verrou:
            ligne = self._db.execute("SELECT messages FROM conversations WHERE id = ?", (id_,)).fetchone()
        return json.loads(ligne[0]) if ligne else []

    def enregistrer(self, id_: int | None, messages: list[dict]) -> int:
        """Crée ou met à jour une conversation ; renvoie son identifiant."""
        donnees = json.dumps(messages, ensure_ascii=False)
        with self._verrou:
            if id_ is None:
                premier = next((m["content"] for m in messages if m["role"] == "user"), "Conversation")
                titre = premier.split("\n")[0].replace("[Fichier joint :", "📎").strip()[:60] or "Conversation"
                cur = self._db.execute(
                    "INSERT INTO conversations (titre, messages, modifiee) VALUES (?, ?, ?)",
                    (titre, donnees, time.time()))
                id_ = cur.lastrowid
                self._limiter()
            else:
                self._db.execute(
                    "UPDATE conversations SET messages = ?, modifiee = MAX(?, modifiee + 0.001) WHERE id = ?", (donnees, time.time(), id_))
            self._db.commit()
        return id_

    def supprimer(self, id_: int) -> None:
        with self._verrou:
            self._db.execute("DELETE FROM conversations WHERE id = ?", (id_,))
            self._db.commit()
