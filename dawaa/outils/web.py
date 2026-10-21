"""Outils internet : recherche DuckDuckGo (sans clé) et lecture d'une page."""
import httpx
import trafilatura
from ddgs import DDGS

from dawaa.outils.fichiers import ErreurOutil

NB_RESULTATS = 5
LONGUEUR_MAX_PAGE = 4000
PAS_D_INTERNET = "Pas de connexion internet : je ne peux pas faire de recherche pour le moment."


def recherche_web(requete: str) -> str:
    try:
        resultats = DDGS().text(requete, region="fr-fr", safesearch="moderate", max_results=NB_RESULTATS)
    except Exception as e:
        if "connect" in str(e).lower() or "timed out" in str(e).lower():
            raise ErreurOutil(PAS_D_INTERNET) from e
        raise ErreurOutil(f"La recherche n'a pas fonctionné ({e}).") from e
    if not resultats:
        return "Aucun résultat trouvé."
    lignes = [f"Résultats pour « {requete} » :"]
    for i, r in enumerate(resultats, start=1):
        lignes.append(f"{i}. {r.get('title', '')}\n   {r.get('body', '')}\n   Source : {r.get('href', '')}")
    lignes.append("Si les extraits ne suffisent pas, lis la page la plus pertinente avec lire_page_web.")
    return "\n".join(lignes)


def lire_page_web(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        raise ErreurOutil("L'adresse doit commencer par http:// ou https://")
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Dawaa/0.1"})
        r.raise_for_status()
    except httpx.ConnectError as e:
        raise ErreurOutil(PAS_D_INTERNET) from e
    except httpx.HTTPError as e:
        raise ErreurOutil(f"Je n'arrive pas à ouvrir cette page ({e}).") from e
    texte = trafilatura.extract(r.text, include_comments=False, include_tables=True) or ""
    if not texte.strip():
        return "Je n'ai pas trouvé de texte lisible sur cette page."
    if len(texte) > LONGUEUR_MAX_PAGE:
        texte = texte[:LONGUEUR_MAX_PAGE] + " […]"
    return f"Contenu de {url} :\n\n{texte}"


SCHEMAS = [
    {
        "name": "recherche_web",
        "description": "Cherche sur internet une information récente (actualités, météo, prix) ou précise sur un lieu ou un organisme (numéro de téléphone, adresse, horaires d'ouverture). Inutile pour des conseils ou explications générales.",
        "parameters": {
            "type": "object",
            "properties": {"requete": {"type": "string", "description": "Mots-clés de recherche"}},
            "required": ["requete"],
        },
    },
    {
        "name": "lire_page_web",
        "description": "Lit le texte d'une page internet à partir de son adresse.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
]

FONCTIONS = {"recherche_web": recherche_web, "lire_page_web": lire_page_web}
