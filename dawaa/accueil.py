"""Accueil du premier lancement : faire connaissance (prénom, e-mail, usages) et présenter ce que Dawaa sait faire."""
import re
from datetime import datetime

from dawaa.dates import JOURS, MOIS
from dawaa.stockage.memoire import ADRESSE_EMAIL, Memoire

# Chaque fonction : présentée dans l'aperçu « Ce que je sais faire », proposée sur l'écran d'accueil si
# l'utilisateur l'a cochée (« suggestion » = texte placé dans la zone de saisie).
FONCTIONS = [
    {"id": "lettres", "emoji": "✉️", "titre": "Écrire et corriger",
     "description": "Lettres, messages, réclamations : je rédige, je corrige ou je reformule, et je crée le document Word.",
     "exemples": ["Aide-moi à écrire une lettre de réclamation", "Corrige ce texte : …"],
     "suggestion": ("Écrire une lettre", "Je vous aide à rédiger", "Aide-moi à écrire une lettre pour ")},
    {"id": "emails", "emoji": "📧", "titre": "Préparer des e-mails",
     "description": "Je prépare l'e-mail dans votre messagerie. Vous le relisez et cliquez vous-même sur Envoyer.",
     "exemples": ["Envoie un mail à Nicole pour lui dire merci", "Envoie-moi la liste de courses par mail"],
     "suggestion": ("Écrire un e-mail", "Je le prépare, vous l'envoyez", "Envoie un mail à ")},
    {"id": "agenda", "emoji": "⏰", "titre": "Agenda et rappels",
     "description": "Je note vos rendez-vous et je vous préviens à l'heure, avec une sonnerie et à voix haute. "
                    "Je sers aussi de minuteur, pour la cuisine par exemple.",
     "exemples": ["Rappelle-moi le dentiste mardi à 15 h", "Mes médicaments tous les jours à 8 h",
                  "Mets un minuteur de 10 minutes", "Qu'est-ce que j'ai demain ?"],
     "suggestion": ("Noter un rendez-vous", "Je vous le rappellerai", "Rappelle-moi ")},
    {"id": "internet", "emoji": "🔎", "titre": "Chercher sur internet",
     "description": "Météo, horaires, actualités, informations : je cherche et je vous résume en citant le site.",
     "exemples": ["Quel temps fera-t-il demain à Lyon ?", "À quelle heure ferme la poste de mon quartier ?"],
     "suggestion": ("Chercher sur internet", "Météo, horaires, infos…", "Cherche sur internet : ")},
    {"id": "sites", "emoji": "🌐", "titre": "Ouvrir des sites",
     "description": "J'ouvre un site ou une recherche dans votre navigateur. Vos sites favoris s'ajoutent dans « Ma mémoire ».",
     "exemples": ["Ouvre YouTube et cherche des recettes de crêpes", "Ouvre le site de la CAF"],
     "suggestion": ("Ouvrir un site", "YouTube, CAF, Ameli…", "Ouvre le site ")},
    {"id": "excel", "emoji": "📊", "titre": "Tableaux Excel",
     "description": "Je crée, lis, complète et résume vos tableaux (Excel, LibreOffice), avec des calculs exacts.",
     "exemples": ["Fais-moi un tableau de mes dépenses du mois", "Lis le fichier budget et fais le total"],
     "suggestion": ("Faire un tableau Excel", "Dépenses, listes, suivis…", "Fais-moi un tableau Excel pour ")},
    {"id": "documents", "emoji": "📄", "titre": "Lire vos documents et fichiers",
     "description": "Je lis et résume vos Word, PDF et tableaux, et j'ouvre les fichiers de votre Bureau ou de vos "
                    "Documents. Vous pouvez aussi glisser un fichier dans ma fenêtre.",
     "exemples": ["Lis-moi le courrier de la mairie sur mon bureau", "Résume le fichier Excel que j'ai ouvert"],
     "suggestion": ("Lire un document", "Word, PDF, tableaux…", "Lis-moi le fichier ")},
]
# Toujours présentées, sans case à cocher
FONCTIONS_DE_BASE = [
    {"id": "voix", "emoji": "🎙️", "titre": "Me parler",
     "description": "Maintenez la touche « parler » (Ctrl droit au départ) ou le bouton micro, parlez, puis relâchez. "
                    "Je vous réponds à voix haute.",
     "exemples": ["Bonjour Dawaa, qu'est-ce que tu sais faire ?"]},
    {"id": "memoire", "emoji": "🧠", "titre": "Me souvenir de vous",
     "description": "Je retiens ce qui est utile (vos proches, votre ville, vos habitudes). Tout est visible et "
                    "effaçable dans « Ma mémoire ».",
     "exemples": ["Retiens que ma fille s'appelle Léa", "Oublie ma ville"]},
    {"id": "ecran", "emoji": "👀", "titre": "Regarder votre écran",
     "description": "Un message bizarre, un bouton introuvable ? Dites « regarde mon écran » : je le regarde et je "
                    "vous explique où cliquer. L'image reste sur votre ordinateur et n'est pas gardée.",
     "exemples": ["Regarde mon écran, qu'est-ce que ce message veut dire ?", "Regarde l'écran : où je clique ?"]},
    {"id": "calculs", "emoji": "🧮", "titre": "Faire des calculs",
     "description": "Pourcentages, remises, partage d'une addition, moyennes : je fais le calcul exact.",
     "exemples": ["Combien font 15 % de 240 ?", "Un pull à 45 € avec 30 % de remise", "Partager 187,50 € entre 6"]},
    {"id": "raccourcis", "emoji": "⚡", "titre": "Raccourcis",
     "description": "Faites quelques actions, puis donnez-leur un nom : je les referai toutes d'un coup.",
     "exemples": ["Retiens ça sous le nom ma routine du matin", "Fais ma routine du matin"]},
]
USAGES = {f["id"]: f["titre"] for f in FONCTIONS}
SUGGESTIONS_PAR_DEFAUT = ["lettres", "excel", "internet"]
DOMAINES_OUTLOOK = re.compile(r"@(hotmail|outlook|live|msn)\.", re.I)


def messagerie_pour(email: str) -> str | None:
    """@gmail.com → gmail ; @hotmail.fr, @outlook.com… → outlook ; sinon on ne change rien."""
    if email.lower().endswith(("@gmail.com", "@googlemail.com")):
        return "gmail"
    if DOMAINES_OUTLOOK.search(email):
        return "outlook"
    return None


def apercu(usages: list[str]) -> list[dict]:
    """Les fonctions choisies par l'utilisateur d'abord, puis les autres, puis les fonctions de base."""
    choisies = [f for f in FONCTIONS if f["id"] in usages]
    autres = [f for f in FONCTIONS if f["id"] not in usages]
    return [{k: v for k, v in f.items() if k != "suggestion"} | {"choisie": f in choisies}
            for f in FONCTIONS_DE_BASE[:1] + choisies + autres + FONCTIONS_DE_BASE[1:]]


def suggestions(usages: list[str]) -> list[dict]:
    """Les trois cartes de l'écran d'accueil, selon les usages cochés."""
    ids = [u for u in usages if u in USAGES][:3]
    ids += [i for i in SUGGESTIONS_PAR_DEFAUT if i not in ids][:3 - len(ids)]
    par_id = {f["id"]: f for f in FONCTIONS}
    return [{"emoji": par_id[i]["emoji"], "titre": par_id[i]["suggestion"][0], "sousTitre": par_id[i]["suggestion"][1],
             "texte": par_id[i]["suggestion"][2]} for i in ids]


def salutation(prenom: str, maintenant: datetime) -> str:
    """Phrase dite à voix haute quand Dawaa est prêt, écrite pour être bien lue par la voix (« 9 heures 5 »)."""
    bonjour = "Bonsoir" if maintenant.hour >= 18 else "Bonjour"
    jour = "1er" if maintenant.day == 1 else str(maintenant.day)
    heure = f"{maintenant.hour} heure{'s' if maintenant.hour > 1 else ''}"
    if maintenant.minute:
        heure += f" {maintenant.minute}"
    return (f"{bonjour}{' ' + prenom if prenom else ''}, bienvenue ! Nous sommes le {JOURS[maintenant.weekday()]} "
            f"{jour} {MOIS[maintenant.month - 1]}, et il est {heure}. Que puis-je faire pour vous aujourd'hui ?")


def _remplacer_souvenir(memoire: Memoire, debut: str, valeur: str) -> None:
    """« Son prénom est Michèle » remplace « Son prénom est Michel » (trop différents pour être fusionnés seuls)."""
    for s in memoire.souvenirs():
        if s["texte"].startswith(debut):
            memoire.supprimer_souvenir(s["id"])
    memoire.retenir(debut + valeur)


def enregistrer(reglages, memoire: Memoire, prenom: str, email: str, usages: list[str]) -> str | None:
    """Enregistre les réponses ; renvoie un message d'erreur à afficher, ou None."""
    prenom = re.sub(r"\s+", " ", str(prenom or "")).strip()[:40]
    email = str(email or "").strip().lower()
    if email and not ADRESSE_EMAIL.fullmatch(email):
        return "Cette adresse e-mail ne semble pas correcte (exemple : marie.dupont@gmail.com). Vous pouvez aussi la laisser vide."
    usages = [u for u in usages or [] if u in USAGES]

    if prenom and prenom != reglages.prenom:
        _remplacer_souvenir(memoire, "Son prénom est ", prenom)
    # Contact « Moi (Michel) » : retrouvé par « envoie-moi » comme par « envoie à Michel »
    for c in memoire.contacts():
        if c["nom"] == "Moi" or c["nom"].startswith("Moi ("):
            memoire.supprimer_contact(c["id"])
    if email:
        memoire.ajouter_contact(f"Moi ({prenom})" if prenom else "Moi", email)
        reglages.messagerie = messagerie_pour(email) or reglages.messagerie
    if usages and usages != reglages.usages:
        _remplacer_souvenir(memoire, "Utilise surtout Dawaa pour : ", ", ".join(USAGES[u].lower() for u in usages))
    reglages.prenom, reglages.email, reglages.usages, reglages.accueil_fait = prenom, email, usages, True
    reglages.enregistrer()
    return None
