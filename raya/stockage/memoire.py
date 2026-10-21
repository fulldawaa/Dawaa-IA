"""Mémoire à long terme (souvenirs sur l'utilisateur), sites favoris et raccourcis, stockés dans SQLite."""
import json
import re
import sqlite3
import threading
import time
import unicodedata
from pathlib import Path

from raya import config

MAX_SOUVENIRS_PROMPT = 50
MAX_CARACTERES_SOUVENIRS = 2500


def normaliser(texte: str) -> str:
    """Minuscules, sans accents ni ponctuation : pour comparer des phrases ou des noms."""
    texte = unicodedata.normalize("NFD", texte.lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", texte).strip()


def _mots(texte: str) -> set[str]:
    return {m for m in normaliser(texte).split() if len(m) > 2}


def ressemblance(a: str, b: str) -> float:
    ma, mb = _mots(a), _mots(b)
    if not ma or not mb:
        return 0.0
    return len(ma & mb) / min(len(ma), len(mb))


class Memoire:
    def __init__(self, chemin: Path | None = None):
        chemin = chemin or config.FICHIER_HISTORIQUE
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self._verrou = threading.Lock()
        self._db = sqlite3.connect(chemin, check_same_thread=False)
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS souvenirs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, texte TEXT NOT NULL, cree REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS favoris (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, url TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS raccourcis (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, actions TEXT NOT NULL, cree REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, email TEXT NOT NULL);
        """)
        # Carnets créés avant l'arrivée des numéros de téléphone
        if "telephone" not in {c[1] for c in self._db.execute("PRAGMA table_info(contacts)")}:
            self._db.execute("ALTER TABLE contacts ADD COLUMN telephone TEXT NOT NULL DEFAULT ''")
        self._db.commit()

    # ---------- souvenirs ----------

    def souvenirs(self) -> list[dict]:
        with self._verrou:
            lignes = self._db.execute("SELECT id, texte, cree FROM souvenirs ORDER BY cree DESC").fetchall()
        return [{"id": i, "texte": t, "cree": c} for i, t, c in lignes]

    def retenir(self, texte: str) -> tuple[int, bool]:
        """Ajoute un souvenir ; s'il en existe un très proche, il est remplacé. Renvoie (id, remplacé)."""
        texte = texte.strip().rstrip(".") + "."
        proche = max(self.souvenirs(), key=lambda s: ressemblance(s["texte"], texte), default=None)
        with self._verrou:
            if proche and ressemblance(proche["texte"], texte) >= 0.8:
                self._db.execute("UPDATE souvenirs SET texte = ?, cree = ? WHERE id = ?", (texte, time.time(), proche["id"]))
                self._db.commit()
                return proche["id"], True
            cur = self._db.execute("INSERT INTO souvenirs (texte, cree) VALUES (?, ?)", (texte, time.time()))
            self._db.commit()
            return cur.lastrowid, False

    def oublier(self, description: str) -> str | None:
        """Supprime le souvenir qui correspond le mieux à la description ; renvoie son texte."""
        candidats = [(ressemblance(s["texte"], description), s) for s in self.souvenirs()]
        score, meilleur = max(candidats, key=lambda c: c[0], default=(0, None))
        if not meilleur or score < 0.5:
            return None
        self.supprimer_souvenir(meilleur["id"])
        return meilleur["texte"]

    def supprimer_souvenir(self, id_: int) -> None:
        with self._verrou:
            self._db.execute("DELETE FROM souvenirs WHERE id = ?", (id_,))
            self._db.commit()

    def tout_oublier(self) -> None:
        with self._verrou:
            self._db.execute("DELETE FROM souvenirs")
            self._db.commit()

    def pour_prompt(self) -> str:
        """Les souvenirs les plus récents, en liste, dans la limite de taille du prompt."""
        lignes, taille = [], 0
        for s in self.souvenirs()[:MAX_SOUVENIRS_PROMPT]:
            taille += len(s["texte"])
            if taille > MAX_CARACTERES_SOUVENIRS:
                break
            lignes.append(f"- {s['texte']}")
        return "\n".join(reversed(lignes))

    # ---------- favoris ----------

    def favoris(self) -> list[dict]:
        with self._verrou:
            lignes = self._db.execute("SELECT id, nom, url FROM favoris ORDER BY nom COLLATE NOCASE").fetchall()
        return [{"id": i, "nom": n, "url": u} for i, n, u in lignes]

    def ajouter_favori(self, nom: str, url: str) -> int:
        nom, url = nom.strip(), url.strip()
        if not nom:
            raise ValueError("Donnez un nom au site.")
        if not re.match(r"^https?://", url, re.I):
            url = "https://" + url
        if not re.match(r"^https?://[\w.-]+\.[a-z]{2,}(/\S*)?$", url, re.I):
            raise ValueError("Cette adresse ne semble pas correcte (exemple : www.ameli.fr).")
        with self._verrou:
            cur = self._db.execute("INSERT INTO favoris (nom, url) VALUES (?, ?)", (nom, url))
            self._db.commit()
            return cur.lastrowid

    def supprimer_favori(self, id_: int) -> None:
        with self._verrou:
            self._db.execute("DELETE FROM favoris WHERE id = ?", (id_,))
            self._db.commit()

    def trouver_favori(self, nom: str) -> dict | None:
        cle = normaliser(nom)
        cle = re.sub(r"^(mon|ma|mes|le|la|les) (site )?(de |du |des )?", "", cle)
        for f in self.favoris():
            n = normaliser(f["nom"])
            if cle and (cle == n or cle in n or n in cle):
                return f
        return None

    # ---------- raccourcis (suites d'actions enregistrées) ----------

    def raccourcis(self) -> list[dict]:
        with self._verrou:
            lignes = self._db.execute("SELECT id, nom, actions FROM raccourcis ORDER BY nom COLLATE NOCASE").fetchall()
        return [{"id": i, "nom": n, "actions": json.loads(a)} for i, n, a in lignes]

    def enregistrer_raccourci(self, nom: str, actions: list[dict]) -> tuple[int, bool]:
        """Enregistre un raccourci ; un raccourci du même nom est remplacé. Renvoie (id, remplacé)."""
        nom = nom.strip().rstrip(".")
        existant = next((r for r in self.raccourcis() if cle_raccourci(r["nom"]) == cle_raccourci(nom)), None)
        donnees = json.dumps(actions, ensure_ascii=False)
        with self._verrou:
            if existant:
                self._db.execute("UPDATE raccourcis SET nom = ?, actions = ?, cree = ? WHERE id = ?",
                                 (nom, donnees, time.time(), existant["id"]))
                self._db.commit()
                return existant["id"], True
            cur = self._db.execute("INSERT INTO raccourcis (nom, actions, cree) VALUES (?, ?, ?)", (nom, donnees, time.time()))
            self._db.commit()
            return cur.lastrowid, False

    def trouver_raccourci(self, nom: str, exact: bool = False) -> dict | None:
        """« fais ma routine du matin » trouve le raccourci « Routine du matin »."""
        cle = cle_raccourci(nom)
        tous = self.raccourcis()
        if not cle:
            return None
        if r := next((r for r in tous if cle_raccourci(r["nom"]) == cle), None):
            return r
        if exact:
            return None
        if r := next((r for r in tous if cle_raccourci(r["nom"]) in cle or cle in cle_raccourci(r["nom"])), None):
            return r
        score, meilleur = max(((ressemblance(r["nom"], nom), r) for r in tous), key=lambda c: c[0], default=(0, None))
        return meilleur if score >= 0.6 else None

    def supprimer_raccourci(self, id_: int) -> None:
        with self._verrou:
            self._db.execute("DELETE FROM raccourcis WHERE id = ?", (id_,))
            self._db.commit()

    # ---------- carnet de contacts ----------

    def contacts(self) -> list[dict]:
        with self._verrou:
            lignes = self._db.execute(
                "SELECT id, nom, email, telephone FROM contacts ORDER BY nom COLLATE NOCASE").fetchall()
        return [{"id": i, "nom": n, "email": e, "telephone": t} for i, n, e, t in lignes]

    def ajouter_contact(self, nom: str, email: str = "", telephone: str = "") -> tuple[int, bool]:
        """Ajoute un contact ; un contact du même nom est complété (l'e-mail ou le numéro donné remplace l'ancien,
        l'autre est gardé). Renvoie (id, remplacé)."""
        nom, email, telephone = nom.strip(), (email or "").strip().lower(), (telephone or "").strip()
        if not nom:
            raise ValueError("Donnez le nom de la personne.")
        if not email and not telephone:
            raise ValueError("Donnez une adresse e-mail ou un numéro de téléphone.")
        if email and not ADRESSE_EMAIL.fullmatch(email):
            raise ValueError("Cette adresse e-mail ne semble pas correcte (exemple : nicole.martin@gmail.com).")
        if telephone and not (telephone := numero_telephone(telephone)):
            raise ValueError("Ce numéro de téléphone ne semble pas correct (exemple : 06 12 34 56 78).")
        existant = next((c for c in self.contacts() if normaliser(c["nom"]) == normaliser(nom)), None)
        with self._verrou:
            if existant:
                self._db.execute("UPDATE contacts SET nom = ?, email = ?, telephone = ? WHERE id = ?",
                                 (nom, email or existant["email"], telephone or existant["telephone"], existant["id"]))
                self._db.commit()
                return existant["id"], True
            cur = self._db.execute("INSERT INTO contacts (nom, email, telephone) VALUES (?, ?, ?)",
                                   (nom, email, telephone))
            self._db.commit()
            return cur.lastrowid, False

    def trouver_contacts(self, nom: str) -> list[dict]:
        """« Nicole » trouve « Nicole Martin » ; « ma fille » ne trouve rien (pas de devinette)."""
        cle = normaliser(re.sub(r"^\s*(a|à)\s+", "", nom))
        tous = self.contacts()
        if exacts := [c for c in tous if normaliser(c["nom"]) == cle]:
            return exacts
        mots = set(cle.split())
        return [c for c in tous if mots and mots <= set(normaliser(c["nom"]).split())]

    def supprimer_contact(self, id_: int) -> None:
        with self._verrou:
            self._db.execute("DELETE FROM contacts WHERE id = ?", (id_,))
            self._db.commit()


ADRESSE_EMAIL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}", re.I)
NUMERO_ECRIT = re.compile(r"(?<!\d)(?:\+\s?\d|0)(?:[\s.\-()]{0,2}\d){8,13}(?!\d)")


def numero_telephone(texte: str) -> str | None:
    """Premier numéro de téléphone du texte, au format lu correctement par la voix : « 06 12 34 56 78 ».

    « 06.12.34.56.78 », « 0612345678 » et « +33 6 12 34 56 78 » donnent « 06 12 34 56 78 » ;
    un numéro étranger (« +44 20 7946 0958 ») est gardé tel quel."""
    if not (m := NUMERO_ECRIT.search(texte or "")):
        return None
    chiffres = re.sub(r"\D", "", m.group())
    if m.group().startswith("+"):
        if chiffres.startswith("33") and len(chiffres) in (11, 12):
            chiffres = "0" + chiffres[-9:]  # +33 (0)6… → 06…
        else:
            return "+" + re.sub(r"\s+", " ", m.group()[1:].strip())
    if len(chiffres) != 10:
        return None
    return " ".join(chiffres[i:i + 2] for i in range(0, 10, 2))


def cle_raccourci(nom: str) -> str:
    """Nom comparable : sans articles ni « raccourci » / « routine » en tête."""
    cle = normaliser(nom)
    cle = re.sub(r"^(fais|lance|refais|execute|demarre)( moi)? ", "", cle)
    cle = re.sub(r"^((mon|ma|mes|le|la|les|l) )?((raccourci|routine) )?", "", cle)
    return cle.strip()
