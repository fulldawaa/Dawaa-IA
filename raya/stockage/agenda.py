"""Agenda : rendez-vous et rappels, stockés dans SQLite à côté de l'historique."""
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from raya import config
from raya.dates import prochaine
from raya.stockage.memoire import normaliser, ressemblance

# Un rappel en retard de plus de 10 minutes a été manqué (Raya ou l'ordinateur était éteint)
RETARD_MANQUE = timedelta(minutes=10)
GARDER_PASSES = timedelta(days=30)


class Agenda:
    def __init__(self, chemin: Path | None = None):
        chemin = chemin or config.FICHIER_HISTORIQUE
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self._verrou = threading.Lock()
        self._db = sqlite3.connect(chemin, check_same_thread=False)
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS rendez_vous (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titre TEXT NOT NULL,
                debut REAL NOT NULL,          -- première date (sert de base aux répétitions)
                quand REAL NOT NULL,          -- prochaine date
                repetition TEXT NOT NULL DEFAULT '',  -- '', jour, semaine, mois, an
                avance INTEGER NOT NULL DEFAULT 0,    -- minutes de rappel avant le rendez-vous
                fait INTEGER NOT NULL DEFAULT 0,      -- rendez-vous unique déjà rappelé
                cree REAL NOT NULL);
        """)
        self._db.commit()

    @staticmethod
    def _ligne(r) -> dict:
        id_, titre, debut, quand, repetition, avance, fait = r
        return {"id": id_, "titre": titre, "debut": datetime.fromtimestamp(debut),
                "quand": datetime.fromtimestamp(quand), "repetition": repetition, "avance": avance, "fait": bool(fait)}

    def _tous(self, condition: str = "1", parametres: tuple = ()) -> list[dict]:
        with self._verrou:
            lignes = self._db.execute(
                f"SELECT id, titre, debut, quand, repetition, avance, fait FROM rendez_vous WHERE {condition} "
                "ORDER BY quand", parametres).fetchall()
        return [self._ligne(r) for r in lignes]

    def ajouter(self, titre: str, quand: datetime, repetition: str = "", avance: int = 0) -> dict:
        with self._verrou:
            cur = self._db.execute(
                "INSERT INTO rendez_vous (titre, debut, quand, repetition, avance, cree) VALUES (?, ?, ?, ?, ?, ?)",
                (titre.strip(), quand.timestamp(), quand.timestamp(), repetition, max(0, int(avance)), time.time()))
            self._db.commit()
        return self._tous("id = ?", (cur.lastrowid,))[0]

    def a_venir(self, depuis: datetime | None = None, jusqua: datetime | None = None) -> list[dict]:
        depuis = depuis or datetime.now()
        # « fait » dit seulement que le rappel a sonné : un rendez-vous rappelé 1 h avant reste à venir
        resultat = self._tous("quand >= ?", (depuis.timestamp(),))
        return [r for r in resultat if jusqua is None or r["quand"] < jusqua]

    def trouver(self, description: str) -> dict | None:
        """Le rendez-vous à venir dont le titre ressemble le plus à la description."""
        cle = normaliser(description)
        candidats = self.a_venir()
        if r := next((r for r in candidats if normaliser(r["titre"]) == cle), None):
            return r
        if r := next((r for r in candidats if cle and (cle in normaliser(r["titre"]) or normaliser(r["titre"]) in cle)), None):
            return r
        score, meilleur = max(((ressemblance(r["titre"], description), r) for r in candidats),
                              key=lambda c: c[0], default=(0, None))
        return meilleur if score >= 0.5 else None

    def supprimer(self, id_: int) -> None:
        with self._verrou:
            self._db.execute("DELETE FROM rendez_vous WHERE id = ?", (id_,))
            self._db.commit()

    def rappels_dus(self, maintenant: datetime | None = None) -> list[dict]:
        """Rendez-vous dont c'est l'heure du rappel. Chacun porte « manque » s'il aurait dû sonner bien avant."""
        maintenant = maintenant or datetime.now()
        dus = []
        for r in self._tous("fait = 0"):
            heure_rappel = r["quand"] - timedelta(minutes=r["avance"])
            if heure_rappel <= maintenant:
                dus.append({**r, "manque": maintenant - heure_rappel > RETARD_MANQUE})
        return dus

    def marquer_rappele(self, rendez_vous: dict, maintenant: datetime | None = None) -> None:
        """Après un rappel : un rendez-vous répété passe à sa prochaine date, un rendez-vous unique est terminé."""
        maintenant = maintenant or datetime.now()
        with self._verrou:
            if rendez_vous["repetition"]:
                # Prochaine date dont le rappel est encore à venir (les répétitions manquées sont sautées)
                apres = max(maintenant + timedelta(minutes=rendez_vous["avance"]), rendez_vous["quand"])
                suivant = prochaine(rendez_vous["debut"], rendez_vous["repetition"], apres)
                self._db.execute("UPDATE rendez_vous SET quand = ? WHERE id = ?", (suivant.timestamp(), rendez_vous["id"]))
            else:
                self._db.execute("UPDATE rendez_vous SET fait = 1 WHERE id = ?", (rendez_vous["id"],))
            self._db.execute("DELETE FROM rendez_vous WHERE fait = 1 AND quand < ?",
                             ((maintenant - GARDER_PASSES).timestamp(),))
            self._db.commit()
