"""Calculs dits en français : « combien font 15 % de 240 », « 12 fois 37 », « 1 250 € moins 20 % », « la moyenne de 12, 15 et 9 ».

Comme pour les dates, c'est le programme qui calcule, jamais le modèle (un petit modèle se trompe souvent en calcul) :
les résultats sont glissés dans le prompt et le modèle n'a plus qu'à les formuler.
"""
import ast
import math
import operator
import re

from raya.dates import _simplifier

MAX_CALCULS = 5
# Sans un de ces mots, des nombres et un tiret (« factures 2024 - 2025 ») ne sont pas une demande de calcul
DEMANDE = re.compile(r"\b(combien|calcul\w*|font|ca fait|egal\w*|resultat|total|somme|moyenne|pour ?cent|fois|multipli\w*|"
                     r"divis\w*|racine|au (carre|cube)|puissance|partag\w*|repartir|reduction|remise)\b|[=%×÷*/+]")
NB = r"\d+(?:\.\d+)?"
REMISE = r"de (?:reduction|remise|rabais|promo(?:tion)?|soldes?)"
OPERATEURS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
              ast.Pow: operator.pow}


class CalculImpossible(ValueError):
    pass


def _evaluer(noeud: ast.AST) -> float:
    """Évalue une expression de calcul simple (nombres, + - * / ^ et parenthèses), sans rien exécuter d'autre."""
    if isinstance(noeud, ast.Expression):
        return _evaluer(noeud.body)
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, (int, float)):
        return noeud.value
    if isinstance(noeud, ast.UnaryOp) and isinstance(noeud.op, (ast.USub, ast.UAdd)):
        v = _evaluer(noeud.operand)
        return -v if isinstance(noeud.op, ast.USub) else v
    if isinstance(noeud, ast.BinOp) and type(noeud.op) in OPERATEURS:
        a, b = _evaluer(noeud.left), _evaluer(noeud.right)
        if isinstance(noeud.op, ast.Pow) and (abs(b) > 100 or abs(a) > 1e6):
            raise CalculImpossible("nombre trop grand")
        if isinstance(noeud.op, ast.Div) and b == 0:
            raise CalculImpossible("division par zéro impossible")
        return OPERATEURS[type(noeud.op)](a, b)
    raise CalculImpossible("expression non reconnue")


def _nombre(x: float, euros: bool) -> str:
    """36 → « 36 » ; 1250.5 → « 1 250,5 » ; 10/3 → « 3,3333 (arrondi) » ; en euros, 2 décimales."""
    if abs(x) >= 1e15:
        raise CalculImpossible("nombre trop grand")
    decimales = 2 if euros else 4
    arrondi = round(x, decimales)
    if arrondi == int(arrondi) and (not euros or abs(x - arrondi) < 1e-9):
        texte = f"{int(arrondi):,}".replace(",", " ")
    else:
        texte = f"{arrondi:,.{decimales}f}".replace(",", " ").replace(".", ",")
        if not euros:
            texte = texte.rstrip("0").rstrip(",")
    if euros:
        texte += " €"
    if abs(x - arrondi) > 1e-9:
        texte += " (arrondi)"
    return texte


def _lisible(expression: str) -> str:
    """« (120+45)/3 » → « (120 + 45) ÷ 3 », « 1250.5 » → « 1 250,5 »."""
    e = expression.replace("**", "^").replace("*", "×").replace("/", "÷")
    e = re.sub(r"(?<=[\d)])\s*-\s*", " − ", e)  # le moins entre deux nombres, pas le signe d'un nombre négatif
    e = re.sub(r"\s*([×÷+^])\s*", r" \1 ", e)
    e = re.sub(r"(?<![\d.])\d{4,}", lambda m: f"{int(m[0]):,}".replace(",", " "), e)
    return re.sub(r"\s+", " ", e.replace(".", ",")).strip()


def calculs(texte: str) -> list[str]:
    """Les calculs repérés dans la demande, déjà faits : ["15 % de 240 = 36", "12 × 37 = 444"]."""
    s = _simplifier(re.sub(r"\[[^\]]*\]", " ", texte))  # sans « [Fichier joint : …] »
    if not DEMANDE.search(s):
        return []
    s = re.sub(r"\b\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}\b", " ", s)  # dates
    for _ in range(4):  # « 1 250 000 » → 1250000
        s = re.sub(r"(?<=\d) (?=\d{3}\b)", "", s)
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)  # virgule décimale
    s = re.sub(r"(?<=\d)-(?=\d)", " a ", s)  # « 15-20 » : une fourchette, pas une soustraction
    euros = bool(re.search(r"€|\beuros?\b", s))
    s = re.sub(r" ?(€|\beuros?\b)", "", s)
    for motif, symbole in ((r"\bmultiplie(e)?s? par\b|\bfois\b|×|(?<=\d) ?x ?(?=\d)", "*"),
                           (r"\bdivise(e)?s? par\b|÷|(?<=\d) : (?=\d)", "/"),
                           (r"\bplus\b", "+"), (r"\bmoins\b", "-"), (r"\bau carre\b", "^2"), (r"\bau cube\b", "^3"),
                           (r"\b(puissance|exposant)\b", "^"), (r" ?\b(pour ?cents?|pourcents?)\b", "%")):
        s = re.sub(motif, f" {symbole} ", s)
    s = re.sub(r"\s+", " ", s)

    resultats = []

    def ajouter(m: re.Match, libelle: str, calcul) -> str:
        try:
            resultats.append(f"{libelle} = {_nombre(calcul(), euros)}")
        except CalculImpossible as e:
            resultats.append(f"{libelle} : {e}")
        except (OverflowError, ValueError):
            resultats.append(f"{libelle} : nombre trop grand")
        except SyntaxError:  # parenthèses mal fermées : on laisse le modèle répondre seul
            pass
        return " ; "  # le morceau déjà calculé ne doit pas resservir

    def f(x: str) -> float:
        return float(x)

    def remplacer(motif: str, faire) -> None:
        nonlocal s
        s = re.sub(motif, lambda m: ajouter(m, *faire(m)), s)

    # « un loyer de 780 augmente de 3,5 % », « le prix baisse de 20 % sur 50 » : le nouveau montant et l'écart
    variation = r"\b(augment|hausse|baiss|diminu)\w* (?:de )?"
    for motif, montant, sens, taux in ((rf"({NB})\D{{0,40}}?{variation}({NB}) ?%", 1, 2, 3),
                                       (rf"{variation}({NB}) ?% (?:sur|de|d'un|d'une) (?:\D{{0,20}}?)({NB})", 3, 1, 2)):
        for m in re.finditer(motif, s):
            a, p = f(m[montant]), f(m[taux])
            signe, libelle = (1, "plus") if m[sens] in ("augment", "hausse") else (-1, "moins")
            ajouter(m, f"{_lisible(m[montant])} {libelle} {_lisible(m[taux])} %", lambda: a * (1 + signe * p / 100))
            ajouter(m, f"{_lisible(m[taux])} % de {_lisible(m[montant])}", lambda: a * p / 100)
        s = re.sub(motif, " ; ", s)
    # Remises et pourcentages : « 30 % de réduction sur 80 », « 80 avec 30 % de remise », « 240 + 20 % », « 15 % de 240 »
    remplacer(rf"({NB}) ?% {REMISE} (?:sur|de) ({NB})",
              lambda m: (f"{_lisible(m[2])} moins {_lisible(m[1])} %", lambda: f(m[2]) * (1 - f(m[1]) / 100)))
    remplacer(rf"({NB}) (?:avec|a) ({NB}) ?% {REMISE}",
              lambda m: (f"{_lisible(m[1])} moins {_lisible(m[2])} %", lambda: f(m[1]) * (1 - f(m[2]) / 100)))
    remplacer(rf"({NB}) ?([+-]) ?({NB}) ?%",
              lambda m: (f"{_lisible(m[1])} {'plus' if m[2] == '+' else 'moins'} {_lisible(m[3])} %",
                         lambda: f(m[1]) * (1 + (1 if m[2] == "+" else -1) * f(m[3]) / 100)))
    remplacer(rf"({NB}) ?% (?:de |d'|sur )({NB})",
              lambda m: (f"{_lisible(m[1])} % de {_lisible(m[2])}", lambda: f(m[1]) * f(m[2]) / 100))
    # « la moyenne de 12, 15 et 9 », « elle a eu 12, 15,5 et 9, quelle est sa moyenne ? »
    if "moyenne" in s and (m := re.search(rf"{NB}(?:(?:, | et |, et ){NB})+", s)):
        notes = re.findall(NB, m[0])
        ajouter(m, f"moyenne de {_lisible(', '.join(notes))}", lambda: sum(map(f, notes)) / len(notes))
        s = s.replace(m[0], " ; ")
    # « partager 120 entre 4 », « l'addition fait 187,50, on est 6 : combien chacun ? »
    remplacer(rf"\b(?:partager|diviser|repartir) ({NB}) (?:entre|en|par|pour) ({NB})",
              lambda m: (f"{_lisible(m[1])} ÷ {_lisible(m[2])}",
                         lambda: _evaluer(ast.parse(f"{m[1]}/{m[2]}", mode="eval"))))
    if re.search(r"\b(chacun|par personne|par tete|chaque personne|partag\w*)\b", s) and \
            len(nombres := re.findall(NB, s)) == 2 and not resultats:
        total, personnes = sorted(nombres, key=float, reverse=True)
        ajouter(None, f"{_lisible(total)} ÷ {_lisible(personnes)}",
                lambda: _evaluer(ast.parse(f"{total}/{personnes}", mode="eval")))
    remplacer(rf"\bracine (?:carree )?(?:de )?({NB})",
              lambda m: (f"racine carrée de {_lisible(m[1])}", lambda: math.sqrt(f(m[1]))))
    # Le reste : « 12 * 37 », « (120 + 45) / 3 », « 2 ^ 10 »
    remplacer(rf"[(]*-?{NB}[)]*(?: ?[-+*/^] ?[(]*{NB}[)]*)+",
              lambda m: (_lisible(m[0]), lambda: _evaluer(ast.parse(m[0].replace("^", "**"), mode="eval"))))
    return resultats[:MAX_CALCULS]


def bloc_calculs(texte: str) -> str:
    """Partie du prompt qui donne au modèle les calculs de la dernière demande, déjà faits."""
    lignes = calculs(texte)
    if not lignes:
        return ""
    return ("\n\nCalculs exacts faits par le programme pour la dernière demande de l'utilisateur : donne ces résultats "
            "tels quels, ne refais jamais le calcul de tête.\n" + "\n".join(f"- {l}" for l in lignes))
