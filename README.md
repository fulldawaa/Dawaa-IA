# Dawaa — assistant IA vocal local

Assistant pour débutants : on lui parle (touche maintenue) ou on lui écrit. Il rédige et corrige des textes, crée et lit des fichiers Word/PDF, cherche sur internet, et crée, lit, modifie ou met en graphique des tableaux Excel.

- **Modèle** : Qwen3.5-4B (Q4_K_M) via `llama-server` (llama.cpp, build Vulkan), entièrement en local. Version 2B si le PC a moins de 8 Go de RAM.
- **Voix** : Whisper `small` en local pour comprendre ; voix Edge (internet) pour parler, avec repli hors ligne sur la voix Windows.
- **Fichiers créés** : `Documents\Dawaa\`. Un original n'est jamais écrasé, chaque modification produit une copie.
- **Mémoire à long terme** : Dawaa retient tout seul les informations durables (proches, ville, préférences…) et l'annonce par « 📌 J'ai retenu… ». Il résume aussi chaque conversation passée en une phrase. Les mots de passe, cartes bancaires, IBAN et numéros de Sécurité sociale ne sont jamais retenus. Tout est consultable et effaçable dans la page **Ma mémoire**.
- **Sites web** : « ouvre YouTube », « montre-moi des recettes de crêpes sur YouTube », « ouvre ma banque » (favori). Les favoris et les grands sites connus s'ouvrent directement. Un site trouvé par recherche est d'abord proposé avec un bouton « Ouvrir ce site » (ou une réponse « oui »).
- **Fichiers de l'ordinateur** : « ouvre le fichier factures sur mon bureau », « lis-moi le courrier de la mairie », « ouvre mes téléchargements ». Dawaa cherche par une partie du nom dans le Bureau, les Documents, les Téléchargements, les Images, les Vidéos et la Musique (sur 3 niveaux de sous-dossiers). Si plusieurs fichiers correspondent, il demande lequel. Il ne lance jamais de programme ni de raccourci (.exe, .lnk…), et ne supprime ni ne déplace rien. Il sait aussi de quel document on parle quand on dit « le fichier que j'ai ouvert » : il lit le titre des fenêtres Word, Excel, LibreOffice, Bloc-notes et Acrobat (jamais celui des navigateurs).
- **Tableaux** : Excel (.xlsx, .xlsm et l'ancien format .xls), LibreOffice Calc (.ods) et CSV. Le résumé retrouve le tableau même s'il ne commence pas en A1 (titre, lignes vides), et ne compte pas deux fois une ligne « Total ». Modifier un .xls, un .ods ou un .csv produit une copie au format .xlsx.
- **Raccourcis** : on fait une ou plusieurs actions (ouvrir un site ou un fichier, lire un document, chercher sur internet), puis on dit « retiens ça sous le nom ma routine du matin ». Ensuite, « fais ma routine du matin » rejoue ces actions telles quelles, sans que le modèle ait à les reconstituer. Les actions qui créent ou modifient un fichier ne sont pas enregistrées. Les raccourcis se suppriment dans **Ma mémoire**, ou en disant « supprime le raccourci … ».
- **Données** : `%APPDATA%\Dawaa\` contient les modèles, `config.json`, `historique.sqlite` et le journal `dawaa.log`.

## Développement

```powershell
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt pytest pyinstaller
.venv\Scripts\python -m pytest -q
.venv\Scripts\python lancer_dawaa.py          # ajouter --debug pour les outils de développement web
```

`llama-server.exe` est téléchargé automatiquement dans `vendor\llama\` par `build.ps1`. Les modèles sont téléchargés par l'application au premier lancement.

## Construire l'installateur

Prérequis : [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`).

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

Le script produit `dist\Dawaa-Setup.exe` (environ 105 Mo). L'installation se fait pour l'utilisateur courant, sans droits administrateur. Les modèles (environ 3,2 Go) sont téléchargés au premier lancement, avec une barre de progression ; le téléchargement reprend là où il s'était arrêté s'il est interrompu.

## À dire aux utilisateurs

Le programme n'est pas encore signé. Windows peut donc afficher « Windows a protégé votre ordinateur ». Cliquez sur **Informations complémentaires**, puis sur **Exécuter quand même**.
