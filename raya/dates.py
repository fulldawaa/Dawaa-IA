"""Dates dites en français : « mardi à 15 h », « demain matin », « dans 20 minutes », « le 3 novembre à 10 h 30 ».

Le modèle recopie l'expression de l'utilisateur ; c'est ce module qui calcule la date, jamais le modèle
(un petit modèle se trompe facilement sur « mardi prochain » ou « dans trois semaines »).
"""
import calendar
import re
import unicodedata
from datetime import date, datetime, time, timedelta

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
MOIS_SIMPLES = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
                "septembre", "octobre", "novembre", "decembre"]
NOMBRES = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
    "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
    "dix-sept": 17, "dix-huit": 18, "dix-neuf": 19, "vingt": 20, "vingt-deux": 22, "vingt-trois": 23,
    "trente": 30, "quarante": 40, "quarante-cinq": 45, "cinquante": 50,
}
NOMBRE = r"(\d+|" + "|".join(sorted(map(re.escape, NOMBRES), key=len, reverse=True)) + r")"

# Heure choisie quand l'utilisateur n'en donne pas, selon le moment de la journée qu'il cite
HEURES_PAR_DEFAUT = {"matin": time(9), "midi": time(12), "apres-midi": time(14), "soir": time(19)}
HEURE_DEFAUT = time(9)

REPETITIONS = {"jour": "chaque jour", "semaine": "chaque semaine", "mois": "chaque mois", "an": "chaque année"}


class DateIncomprise(ValueError):
    """Expression que le programme ne sait pas transformer en date : on demande à l'utilisateur de préciser."""


def _simplifier(texte: str) -> str:
    texte = unicodedata.normalize("NFD", texte.lower().replace("’", "'"))
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    texte = texte.replace("apres midi", "apres-midi").replace("l'apres-midi", "apres-midi")
    return re.sub(r"\s+", " ", texte).strip()


def _nombre(mot: str) -> int:
    return int(mot) if mot.isdigit() else NOMBRES[mot]


def repetition_dans(texte: str) -> str:
    """« tous les jours à 8 h » → « jour » ; « » si l'expression ne parle pas de répétition."""
    s = _simplifier(texte)
    if re.search(r"\b(tous les jours|chaque jour|quotidien(ne)?ment|tous les (matins|soirs))\b", s):
        return "jour"
    if re.search(r"\b(toutes les semaines|chaque semaine|tous les (" + "|".join(JOURS) + r")s?|chaque ("
                 + "|".join(JOURS) + r"))\b", s):
        return "semaine"
    if re.search(r"\b(tous les mois|chaque mois|mensuel(le)?ment)\b", s):
        return "mois"
    if re.search(r"\b(tous les ans|chaque annee|chaque an|annuel(le)?ment)\b", s):
        return "an"
    return ""


def _extraire_heure(s: str) -> tuple[time | None, str, str]:
    """Renvoie (heure, moment de la journée cité, texte sans l'heure)."""
    moment = next((m for m in ("apres-midi", "matin", "soir") if re.search(rf"\b{m}s?\b", s)), "")
    heure = None
    if m := re.search(r"(?<!-)\b(a )?midi( et demie?)?\b", s):
        heure, moment = time(12, 30 if m.group(2) else 0), "midi"
    elif m := re.search(r"\b(a )?minuit\b", s):
        heure = time(0)
    elif m := re.search(rf"\b(?:a |vers )?{NOMBRE} ?(?:heures?|h|:)(?=\d|\s|$)"
                        rf"(?: ?(\d{{2}})\b| (et demie?|et quart|moins le quart))?", s):
        h = _nombre(m.group(1))
        minutes = int(m.group(2)) if m.group(2) else {"et demi": 30, "et demie": 30, "et quart": 15,
                                                     "moins le quart": -15}.get(m.group(3) or "", 0)
        if minutes < 0:
            h, minutes = h - 1, 45
        if moment in ("apres-midi", "soir") and h < 12:
            h += 12
        if not (0 <= h <= 23 and 0 <= minutes <= 59):
            raise DateIncomprise(f"L'heure « {m.group(0).strip()} » n'existe pas.")
        heure = time(h, minutes)
    if m:
        s = (s[:m.start()] + " " + s[m.end():]).strip()
    return heure, moment, s


def _ajouter_mois(d: date, n: int) -> date:
    mois = d.month - 1 + n
    annee, mois = d.year + mois // 12, mois % 12 + 1
    return date(annee, mois, min(d.day, calendar.monthrange(annee, mois)[1]))


MINUTEUR = re.compile(r"\b(minuteurs?|minuteries?|compte a rebours|timer|chrono(metre)?)\b")
_UNITES_DUREE = r"heures?|h|minutes?|mn|min|secondes?|sec|s"
# Un morceau de durée : « 10 minutes », « 1 h 30 », « une demi-heure », « trois quarts d'heure », « 30 secondes »
_MORCEAU_DUREE = re.compile(
    rf"\b(?:{NOMBRE} ?|((?:une )?demi|(?:un )?quart d'?|trois quarts d'?)[- ]?)({_UNITES_DUREE})(?:\b|(?=\d))"
    rf"(?: (et demie?|et quart))?(?: ?(\d{{1,2}})\b(?! ?(?:{_UNITES_DUREE})(?:\b|(?=\d))))?")
# Mots qui peuvent entourer une durée sans en changer le sens (« un minuteur de 10 minutes »)
_AUTOUR_DUREE = re.compile(r"\b(s'il (te|vous) plait|dans|pendant|de|d|un|une|le|la|mets?|lance|minuteurs?|minuteries?|"
                           r"compte a rebours|timer|chrono(metre)?|et|sur)\b|[,.!']")
_FRACTIONS = {"demi": 0.5, "quart d": 0.25, "trois quarts d": 0.75}


def _valeur(m: re.Match) -> timedelta:
    n = _FRACTIONS[re.sub(r"^une? |'$", "", m.group(2))] if m.group(2) else _nombre(m.group(1))
    n += {"et demi": 0.5, "et demie": 0.5, "et quart": 0.25}.get(m.group(4) or "", 0)
    suite = int(m.group(5) or 0)  # « 1 h 30 », « 2 minutes 30 »
    if m.group(3).startswith("h"):
        return timedelta(hours=n, minutes=suite)
    if m.group(3).startswith("m"):
        return timedelta(minutes=n, seconds=suite)
    return timedelta(seconds=n)


def duree(texte: str) -> timedelta | None:
    """« minuteur de 10 minutes », « dans 1 h 30 », « 30 secondes » → durée ; None si l'expression n'en est pas une.

    Sans « dans » ni « minuteur », une heure seule (« 15 h », « 8 heures ») est une heure de la journée."""
    s = _simplifier(texte)
    dans = re.search(r"\bdans ", s)
    zone = s[dans.end():] if dans else s
    total, fin, heures = timedelta(), 0, False
    for m in _MORCEAU_DUREE.finditer(zone):
        if dans and not re.fullmatch(r"\s*(et\s*)?", zone[fin:m.start()]):
            break  # « dans 2 jours à 10 h » : le « 10 h » n'est pas une durée
        total += _valeur(m)
        fin = m.end()
        heures |= m.group(3).startswith("h") and not m.group(2)
    if not total:
        return None
    if not dans and (_AUTOUR_DUREE.sub(" ", _MORCEAU_DUREE.sub(" ", s)).strip() or heures and not MINUTEUR.search(s)):
        return None
    return total


def decrire_duree(d: timedelta) -> str:
    """« 1 heure 30 minutes », « 45 secondes »."""
    secondes = int(d.total_seconds())
    morceaux = [(secondes // 86400, "jour"), (secondes // 3600 % 24, "heure"), (secondes // 60 % 60, "minute"),
                (secondes % 60, "seconde")]
    return " ".join(f"{n} {nom}{'s' if n > 1 else ''}" for n, nom in morceaux if n) or "0 seconde"


def interpreter(texte: str, maintenant: datetime | None = None) -> tuple[datetime, bool]:
    """Calcule la date d'une expression française. Renvoie (date et heure, heure donnée par l'utilisateur ?)."""
    if d := duree(texte):  # minuteur ou « dans 20 minutes » : à la seconde près
        return (maintenant or datetime.now()).replace(microsecond=0) + d, True
    maintenant = (maintenant or datetime.now()).replace(second=0, microsecond=0)
    s = _simplifier(texte)

    # 1. Durée en jours : « dans 3 jours », « dans 2 semaines à 10 h »
    if m := re.search(rf"\bdans (?:{NOMBRE} )?(jours?|semaines?|mois|ans?)\b", s):
        n = _nombre(m.group(1)) if m.group(1) else 1
        unite = m.group(2)
        heure, moment, _ = _extraire_heure((s[:m.start()] + " " + s[m.end():]).strip())
        jour = maintenant.date()
        if unite.startswith("jour"):
            jour += timedelta(days=n)
        elif unite.startswith("semaine"):
            jour += timedelta(weeks=n)
        else:
            jour = _ajouter_mois(jour, n if unite == "mois" else 12 * n)
        return datetime.combine(jour, heure or HEURES_PAR_DEFAUT.get(moment) or HEURE_DEFAUT), heure is not None

    heure, moment, s = _extraire_heure(s)

    # 2. Jour
    aujourd_hui = maintenant.date()
    jour, annee_donnee = None, True
    if re.search(r"\bapres-?demain\b", s):
        jour = aujourd_hui + timedelta(days=2)
    elif re.search(r"\bdemain\b", s):
        jour = aujourd_hui + timedelta(days=1)
    elif re.search(r"\b(aujourd'?hui|ce soir|ce matin|cet apres-midi|ce midi|tout a l'heure|tantot)\b", s):
        jour = aujourd_hui
    elif m := re.search(r"\b(" + "|".join(JOURS) + r")s?\b", s):
        ecart = (JOURS.index(m.group(1)) - aujourd_hui.weekday()) % 7 or 7
        jour = aujourd_hui + timedelta(days=ecart)
    elif m := re.search(r"\b(\d{1,2})(?:er)? (" + "|".join(MOIS_SIMPLES) + r")(?: (\d{4}))?\b", s):
        jour, annee_donnee = _date(int(m.group(1)), MOIS_SIMPLES.index(m.group(2)) + 1, m.group(3), aujourd_hui), bool(m.group(3))
    elif m := re.search(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", s):
        jour, annee_donnee = _date(int(m.group(1)), int(m.group(2)), m.group(3), aujourd_hui), bool(m.group(3))
    elif m := re.search(r"\b(?:le|du) (\d{1,2})(?:er)?\b", s):
        jour = _date(int(m.group(1)), aujourd_hui.month, None, aujourd_hui)
        if jour < aujourd_hui:
            jour = _ajouter_mois(jour, 1)
    elif re.search(r"\b(semaine prochaine|mois prochain|bientot|plus tard)\b", s):
        raise DateIncomprise("Ce moment n'est pas assez précis : demandez le jour exact (par exemple « lundi 3 novembre »).")

    if jour is None and heure is None and not moment:
        if repetition_dans(texte) == "jour":
            jour = aujourd_hui  # « tous les jours » sans heure
        else:
            raise DateIncomprise(f"Je ne comprends pas la date « {texte} ». Demandez à l'utilisateur le jour et l'heure.")

    heure_donnee = heure is not None
    heure = heure or HEURES_PAR_DEFAUT.get(moment) or HEURE_DEFAUT
    if jour is None:  # seulement une heure : aujourd'hui si elle n'est pas passée, sinon demain
        jour = aujourd_hui if datetime.combine(aujourd_hui, heure) > maintenant else aujourd_hui + timedelta(days=1)
    resultat = datetime.combine(jour, heure)
    if resultat <= maintenant and not annee_donnee:  # « le 3 janvier » dit en décembre
        resultat = datetime.combine(_ajouter_mois(resultat.date(), 12), resultat.time())
    if resultat <= maintenant:
        if repetition_dans(texte):
            return prochaine(resultat, repetition_dans(texte), maintenant), heure_donnee
        raise DateIncomprise(f"Cette date est déjà passée ({decrire(resultat, maintenant)}).")
    return resultat, heure_donnee


def _date(jour: int, mois: int, annee: str | None, aujourd_hui: date) -> date:
    an = int(annee) + (2000 if annee and len(annee) == 2 else 0) if annee else aujourd_hui.year
    try:
        d = date(an, mois, jour)
    except ValueError:
        raise DateIncomprise(f"Le {jour}/{mois} n'existe pas.") from None
    return d


def occurrence(debut: datetime, repetition: str, n: int) -> datetime:
    """La n-ième répétition d'un rendez-vous (le 31 de chaque mois tombe le 28 ou le 30 si besoin)."""
    if repetition == "jour":
        return debut + timedelta(days=n)
    if repetition == "semaine":
        return debut + timedelta(weeks=n)
    if repetition in ("mois", "an"):
        return datetime.combine(_ajouter_mois(debut.date(), n * (12 if repetition == "an" else 1)), debut.time())
    return debut


def prochaine(debut: datetime, repetition: str, apres: datetime) -> datetime:
    """Première occurrence strictement après `apres`."""
    if not repetition:
        return debut
    n = 0
    if repetition in ("jour", "semaine") and apres > debut:  # saut direct, sans parcourir chaque jour manqué
        n = (apres - debut) // timedelta(days=1 if repetition == "jour" else 7)
    while (d := occurrence(debut, repetition, n)) <= apres:
        n += 1
    return d


def decrire(d: datetime, maintenant: datetime | None = None) -> str:
    """« mardi 21 octobre à 15 h » (l'année seulement si ce n'est pas l'année en cours)."""
    maintenant = maintenant or datetime.now()
    jour = "1er" if d.day == 1 else str(d.day)
    texte = f"{JOURS[d.weekday()]} {jour} {MOIS[d.month - 1]}"
    if d.year != maintenant.year:
        texte += f" {d.year}"
    if d.date() == maintenant.date():
        texte = f"aujourd'hui ({texte})"
    elif d.date() == maintenant.date() + timedelta(days=1):
        texte = f"demain ({texte})"
    heure = "midi" if (d.hour, d.minute) == (12, 0) else "minuit" if (d.hour, d.minute) == (0, 0) \
        else f"{d.hour} h" + (f" {d.minute:02d}" if d.minute else "")
    return f"{texte} à {heure}"
