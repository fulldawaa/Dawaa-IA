// Interface de Dawaa. Python appelle les fonctions de `window.dawaa` ; l'interface appelle `pywebview.api.*`.
(function () {
  const $ = (s) => document.querySelector(s);
  const fil = $("#fil");
  const accueil = $("#accueil");
  const texte = $("#texte");
  const btnEnvoyer = $("#btn-envoyer");
  const btnMicro = $("#btn-micro");
  const zoneJoints = $("#joints");

  const api = () => (window.pywebview && window.pywebview.api) || null;
  let joints = [];           // chemins des fichiers joints au prochain message
  let reponse = null;        // { element, contenu, brut } de la réponse en cours
  let enCours = false;
  let etatActuel = "demarrage";
  let conversationActive = null;
  let nomTouche = "Ctrl droit";

  const ICONES = {
    ecouter: '<svg viewBox="0 0 24 24"><path d="M11 5 6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/></svg>',
    copier: '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
    fichier: '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>',
    dossier: '<svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
    croix: '<svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>',
    trombone: '<svg viewBox="0 0 24 24"><path d="M21 11.5l-8.6 8.6a5.5 5.5 0 0 1-7.8-7.8l8.6-8.6a3.7 3.7 0 0 1 5.2 5.2l-8.6 8.6a1.8 1.8 0 0 1-2.6-2.6l7.9-7.9"/></svg>',
  };

  // ---------- outils d'affichage ----------

  function echapper(t) {
    const d = document.createElement("div");
    d.textContent = t;
    return d.innerHTML;
  }

  function defilerEnBas() {
    fil.scrollTop = fil.scrollHeight;
  }

  function notifier(message) {
    const n = document.createElement("div");
    n.className = "notification";
    n.textContent = message;
    $("#notifications").appendChild(n);
    setTimeout(() => n.remove(), 5000);
  }

  function ajusterHauteur() {
    texte.style.height = "auto";
    texte.style.height = texte.scrollHeight + "px";
  }

  function nomFichier(chemin) {
    return chemin.split(/[\\/]/).pop();
  }

  function separerJoints(contenu) {
    const fichiers = [];
    const propre = contenu.replace(/\n?\[Fichier joint : ([^\]]+)\]/g, (_, c) => { fichiers.push(c); return ""; });
    return { propre, fichiers };
  }

  function afficherUtilisateur(contenu) {
    accueil.hidden = true;
    const { propre, fichiers } = separerJoints(contenu);
    const div = document.createElement("div");
    div.className = "message user";
    div.innerHTML = '<div class="contenu"></div>';
    const bulle = div.firstChild;
    bulle.textContent = propre;
    fichiers.forEach((f) => {
      const p = document.createElement("div");
      p.className = "joint-message";
      p.innerHTML = ICONES.trombone + echapper(nomFichier(f));
      bulle.appendChild(p);
    });
    fil.appendChild(div);
    defilerEnBas();
  }

  function creerReponse() {
    accueil.hidden = true;
    const div = document.createElement("div");
    div.className = "message assistant";
    div.innerHTML = '<div class="contenu"><span class="attente"><i></i><i></i><i></i></span></div>';
    fil.appendChild(div);
    defilerEnBas();
    return { element: div, contenu: div.querySelector(".contenu"), brut: "" };
  }

  function ajouterSouvenirs(element, souvenirs) {
    (souvenirs || []).forEach((s) => {
      const div = document.createElement("div");
      div.className = "souvenir";
      div.innerHTML = "📌 <span></span><button>Effacer</button>";
      div.querySelector("span").textContent = "J'ai retenu : " + s.texte;
      div.querySelector("button").onclick = (e) => {
        api() && api().supprimer_souvenir(s.id);
        div.classList.add("efface");
        e.target.remove();
        notifier("C'est oublié.");
      };
      element.appendChild(div);
    });
  }

  function ajouterPropositions(element, propositions) {
    (propositions || []).forEach((p) => {
      const div = document.createElement("div");
      div.className = "proposition";
      div.innerHTML = '<span style="font-size:1.4em">🌐</span><div class="info"><strong></strong><span></span></div>' +
        '<button class="btn-ouvrir">Ouvrir ce site</button>';
      div.querySelector("strong").textContent = p.titre || p.domaine;
      div.querySelector(".info span").textContent = p.domaine;
      div.querySelector("button").onclick = () => api() && api().ouvrir_lien(p.url);
      element.appendChild(div);
    });
  }

  function ajouterActions(element, brut, fichiers) {
    const actions = document.createElement("div");
    actions.className = "actions";
    (fichiers || []).forEach((chemin) => {
      const ouvrir = document.createElement("button");
      ouvrir.className = "action fichier";
      ouvrir.innerHTML = ICONES.fichier + "Ouvrir " + echapper(nomFichier(chemin));
      ouvrir.onclick = () => api() && api().ouvrir_fichier(chemin);
      const dossier = document.createElement("button");
      dossier.className = "action";
      dossier.innerHTML = ICONES.dossier + "Voir dans le dossier";
      dossier.onclick = () => api() && api().ouvrir_dossier(chemin);
      actions.append(ouvrir, dossier);
    });
    if (brut.trim()) {
      const ecouter = document.createElement("button");
      ecouter.className = "action";
      ecouter.innerHTML = ICONES.ecouter + "Écouter";
      ecouter.onclick = () => api() && api().lire(brut);
      const copier = document.createElement("button");
      copier.className = "action";
      copier.innerHTML = ICONES.copier + "Copier";
      copier.onclick = () => {
        navigator.clipboard.writeText(brut).then(() => notifier("Texte copié. Vous pouvez le coller avec Ctrl + V."));
      };
      actions.append(ecouter, copier);
    }
    if (actions.children.length) element.appendChild(actions);
  }

  function afficherAssistant(brut) {
    const r = creerReponse();
    r.contenu.innerHTML = markdown(brut);
    ajouterActions(r.element, brut, []);
  }

  function viderFil() {
    fil.querySelectorAll(".message").forEach((m) => m.remove());
    accueil.hidden = false;
  }

  function majBoutonEnvoyer() {
    const arreter = enCours || etatActuel === "parle";
    btnEnvoyer.textContent = arreter ? "Arrêter" : "Envoyer";
    btnEnvoyer.classList.toggle("arreter", arreter);
  }

  function afficherJoints() {
    zoneJoints.innerHTML = "";
    joints.forEach((chemin, i) => {
      const puce = document.createElement("span");
      puce.className = "puce-joint";
      puce.innerHTML = ICONES.trombone + echapper(nomFichier(chemin)) + '<button title="Retirer">' + ICONES.croix + "</button>";
      puce.querySelector("button").onclick = () => { joints.splice(i, 1); afficherJoints(); };
      zoneJoints.appendChild(puce);
    });
  }

  // ---------- actions de l'utilisateur ----------

  function envoyer(message) {
    const contenu = (message !== undefined ? message : texte.value).trim();
    if (!contenu && !joints.length) return;
    if (!api()) return notifier("Un instant, je démarre…");
    if (enCours) return notifier("Je réponds encore. Cliquez sur « Arrêter » pour m'interrompre.");
    const fichiers = joints.slice();
    const affiche = (contenu || "Voici un fichier.") + fichiers.map((f) => `\n[Fichier joint : ${f}]`).join("");
    afficherUtilisateur(affiche);
    api().envoyer(contenu || "Voici un fichier. Dis-moi brièvement ce qu'il contient.", fichiers);
    texte.value = "";
    joints = [];
    afficherJoints();
    ajusterHauteur();
  }

  btnEnvoyer.onclick = () => {
    if (enCours || etatActuel === "parle") { api() && api().arreter(); return; }
    envoyer();
  };

  texte.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); envoyer(); }
  });
  texte.addEventListener("input", ajusterHauteur);

  document.querySelectorAll(".suggestion").forEach((b) => {
    b.onclick = () => { texte.value = b.dataset.texte; texte.focus(); ajusterHauteur(); };
  });

  // Bouton micro : maintenir pour parler (comme la touche du clavier)
  let microEnfonce = false;
  function microDebut(e) {
    e.preventDefault();
    if (microEnfonce || !api()) return;
    microEnfonce = true;
    btnMicro.classList.add("actif");
    api().micro_appui();
  }
  function microFin() {
    if (!microEnfonce) return;
    microEnfonce = false;
    btnMicro.classList.remove("actif");
    api().micro_relache();
  }
  btnMicro.addEventListener("mousedown", microDebut);
  btnMicro.addEventListener("touchstart", microDebut);
  window.addEventListener("mouseup", microFin);
  window.addEventListener("touchend", microFin);
  btnMicro.addEventListener("click", (e) => e.preventDefault());

  $("#btn-joindre").onclick = () => api() && api().choisir_fichiers();
  $("#btn-fichiers").onclick = () => api() && api().ouvrir_dossier("");
  $("#btn-nouvelle").onclick = () => {
    if (!api()) return;
    api().nouvelle_conversation();
    conversationActive = null;
    enCours = false;
    reponse = null;
    viderFil();
    majBoutonEnvoyer();
    document.querySelectorAll(".conversation").forEach((c) => c.classList.remove("active"));
    texte.focus();
  };

  // Liens : toujours dans le navigateur habituel
  fil.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-lien]");
    if (a) { e.preventDefault(); api() && api().ouvrir_lien(a.dataset.lien); }
  });

  // Glisser-déposer (les chemins complets sont récupérés côté Python)
  let compteurDepot = 0;
  window.addEventListener("dragenter", (e) => { e.preventDefault(); compteurDepot++; $("#depot").hidden = false; });
  window.addEventListener("dragleave", () => { if (--compteurDepot <= 0) { compteurDepot = 0; $("#depot").hidden = true; } });
  window.addEventListener("dragover", (e) => e.preventDefault());
  // En phase de capture : Python intercepte le dépôt sur `document` et arrête sa propagation,
  // un écouteur normal sur `window` ne serait donc jamais appelé et le cadre resterait affiché.
  window.addEventListener("drop", (e) => { e.preventDefault(); compteurDepot = 0; $("#depot").hidden = true; }, true);

  // ---------- ma mémoire ----------

  function afficherMemoire(donnees) {
    if (!donnees) return;
    const souvenirs = $("#liste-souvenirs");
    souvenirs.innerHTML = "";
    if (!donnees.souvenirs.length) {
      souvenirs.innerHTML = '<li class="vide">Rien pour l\'instant. Parlez-moi de vous : je retiendrai ce qui est utile.</li>';
    }
    donnees.souvenirs.forEach((s) => {
      const li = document.createElement("li");
      li.innerHTML = '<span class="texte"></span><button title="Oublier">' + ICONES.croix + "</button>";
      li.querySelector(".texte").textContent = s.texte;
      li.querySelector("button").onclick = async () => afficherMemoire(await api().supprimer_souvenir(s.id));
      souvenirs.appendChild(li);
    });
    $("#btn-tout-oublier").hidden = !donnees.souvenirs.length;

    const favoris = $("#liste-favoris");
    favoris.innerHTML = "";
    if (!donnees.favoris.length) favoris.innerHTML = '<li class="vide">Aucun site favori.</li>';
    donnees.favoris.forEach((f) => {
      const li = document.createElement("li");
      li.innerHTML = '<span class="texte"><strong></strong><br><span class="url"></span></span>' +
        '<button title="Supprimer">' + ICONES.croix + "</button>";
      li.querySelector("strong").textContent = f.nom;
      li.querySelector(".url").textContent = f.url;
      li.querySelector("button").onclick = async () => afficherMemoire(await api().supprimer_favori(f.id));
      favoris.appendChild(li);
    });
    const raccourcis = $("#liste-raccourcis");
    raccourcis.innerHTML = "";
    if (!(donnees.raccourcis || []).length) raccourcis.innerHTML = '<li class="vide">Aucun raccourci.</li>';
    (donnees.raccourcis || []).forEach((r) => {
      const li = document.createElement("li");
      li.innerHTML = '<span class="texte"><strong></strong><br><span class="url"></span></span>' +
        '<button title="Supprimer">' + ICONES.croix + "</button>";
      li.querySelector("strong").textContent = r.nom;
      li.querySelector(".url").textContent = r.actions.map((a, i) => (i + 1) + ". " + a).join("  ·  ");
      li.querySelector("button").onclick = async () => afficherMemoire(await api().supprimer_raccourci(r.id));
      raccourcis.appendChild(li);
    });

    $("#erreur-favori").hidden = !donnees.erreur;
    $("#erreur-favori").textContent = donnees.erreur || "";
  }

  $("#btn-memoire").onclick = async () => {
    if (!api()) return;
    afficherMemoire(await api().memoire());
    $("#ecran-memoire").hidden = false;
  };
  $("#btn-fermer-memoire").onclick = () => { $("#ecran-memoire").hidden = true; };
  $("#btn-tout-oublier").onclick = async () => {
    if (confirm("Effacer tout ce que Dawaa sait de vous ? Vos favoris et vos conversations sont conservés.")) {
      afficherMemoire(await api().tout_oublier());
    }
  };
  $("#form-favori").onsubmit = async (e) => {
    e.preventDefault();
    const donnees = await api().ajouter_favori($("#favori-nom").value, $("#favori-url").value);
    afficherMemoire(donnees);
    if (!donnees.erreur) { $("#favori-nom").value = ""; $("#favori-url").value = ""; }
  };

  // ---------- réglages ----------

  $("#btn-reglages").onclick = () => { $("#ecran-reglages").hidden = false; };
  $("#btn-fermer-reglages").onclick = () => { $("#ecran-reglages").hidden = true; $("#aide-touche").hidden = true; };
  $("#btn-changer-touche").onclick = () => {
    $("#aide-touche").hidden = false;
    $("#reglage-touche").textContent = "…";
    api() && api().capturer_touche();
  };
  $("#reglage-voix").onchange = (e) => api() && api().reglages({ voix: e.target.value });
  $("#btn-tester-voix").onclick = () => api() && api().lire("Bonjour, je suis Dawaa. Voici ma voix.");
  $("#reglage-taille").oninput = (e) => {
    document.documentElement.style.setProperty("--taille", e.target.value + "px");
  };
  $("#reglage-taille").onchange = (e) => api() && api().reglages({ tailleTexte: +e.target.value });

  // ---------- premier lancement ----------

  $("#btn-installer").onclick = () => {
    $("#btn-installer").hidden = true;
    $("#erreur-installation").hidden = true;
    $("#progression").hidden = false;
    api() && api().lancer_telechargement();
  };

  // ---------- fonctions appelées par Python ----------

  const TEXTES_ETAT = {
    demarrage: () => "Je me prépare…",
    pret: () => `Prêt. Maintenez <kbd>${echapper(nomTouche)}</kbd> (ou le bouton micro) pour parler, ou écrivez ci-dessous.`,
    ecoute: () => "Je vous écoute… relâchez quand vous avez fini.",
    transcription: () => "Je note ce que vous avez dit…",
    reflechit: () => "Je réfléchis…",
    outil: () => "Je travaille…",
    parle: () => "Je parle… (cliquez sur « Arrêter » pour me couper)",
    erreur: () => "Un problème est survenu.",
  };

  window.dawaa = {
    etat(etat, detail, touche) {
      etatActuel = etat;
      if (touche) nomTouche = touche;
      const zone = $("#etat");
      zone.className = "etat " + etat;
      $("#etat-texte").innerHTML = detail ? echapper(detail) : (TEXTES_ETAT[etat] || TEXTES_ETAT.pret)();
      if (etat !== "ecoute") btnMicro.classList.remove("actif");
      if (etat === "ecoute") btnMicro.classList.add("actif");
      majBoutonEnvoyer();
    },

    notification: notifier,

    messageUtilisateur(contenu) { afficherUtilisateur(contenu); },

    debutReponse() {
      enCours = true;
      reponse = creerReponse();
      majBoutonEnvoyer();
    },

    ajouterTexte(morceau) {
      if (!reponse) reponse = creerReponse();
      reponse.brut += morceau;
      reponse.contenu.innerHTML = markdown(reponse.brut);
      defilerEnBas();
    },

    effacerReponse() {
      if (!reponse) return;
      reponse.brut = "";
      reponse.contenu.innerHTML = '<span class="attente"><i></i><i></i><i></i></span>';
    },

    finReponse(elements) {
      enCours = false;
      elements = elements || {};
      if (reponse) {
        if (!reponse.brut.trim()) reponse.contenu.innerHTML = "<p><em>(Réponse interrompue)</em></p>";
        ajouterPropositions(reponse.element, elements.propositions);
        ajouterSouvenirs(reponse.element, elements.souvenirs);
        ajouterActions(reponse.element, reponse.brut, elements.fichiers);
      }
      reponse = null;
      majBoutonEnvoyer();
      defilerEnBas();
    },

    erreurReponse(message) {
      enCours = false;
      if (!reponse) reponse = creerReponse();
      reponse.contenu.innerHTML = '<p class="erreur-message">' + echapper(message) + "</p>";
      reponse = null;
      majBoutonEnvoyer();
    },

    fichierJoint(chemin) {
      if (!joints.includes(chemin)) joints.push(chemin);
      afficherJoints();
      texte.focus();
    },

    listeConversations(liste) {
      const nav = $("#liste-conversations");
      nav.innerHTML = "";
      if (!liste.length) {
        nav.innerHTML = '<div class="vide">Aucune conversation pour l\'instant</div>';
        return;
      }
      liste.forEach((c) => {
        const b = document.createElement("button");
        b.className = "conversation" + (c.id === conversationActive ? " active" : "");
        b.innerHTML = '<span class="titre"></span><span class="suppr" title="Supprimer">' + ICONES.croix + "</span>";
        b.querySelector(".titre").textContent = c.titre;
        b.title = c.titre;
        b.onclick = async (e) => {
          if (e.target.closest(".suppr")) {
            if (confirm("Supprimer cette conversation ?")) api().supprimer_conversation(c.id);
            return;
          }
          const messages = await api().ouvrir_conversation(c.id);
          conversationActive = c.id;
          enCours = false;
          reponse = null;
          viderFil();
          messages.forEach((m) => (m.role === "user" ? afficherUtilisateur(m.content) : afficherAssistant(m.content)));
          document.querySelectorAll(".conversation").forEach((x) => x.classList.toggle("active", x === b));
          majBoutonEnvoyer();
        };
        nav.appendChild(b);
      });
    },

    appliquerReglages(r) {
      nomTouche = r.toucheNom;
      document.querySelectorAll(".nom-touche").forEach((k) => (k.textContent = r.toucheNom));
      $("#aide-touche").hidden = true;
      const select = $("#reglage-voix");
      select.innerHTML = "";
      Object.entries(r.voixListe).forEach(([id, nom]) => {
        const o = document.createElement("option");
        o.value = id;
        o.textContent = nom;
        o.selected = id === r.voix;
        select.appendChild(o);
      });
      $("#reglage-taille").value = r.tailleTexte;
      document.documentElement.style.setProperty("--taille", r.tailleTexte + "px");
    },

    premierLancement(tailleGo) {
      $("#taille-installation").textContent = String(tailleGo).replace(".", ",") + " Go";
      $("#ecran-installation").hidden = false;
    },

    progression(fraction, message) {
      const pct = Math.floor(fraction * 100);
      $("#progression-remplie").style.width = pct + "%";
      $("#progression-texte").textContent = `${message} ${pct} %`;
    },

    erreurTelechargement(message) {
      $("#erreur-installation").textContent = message;
      $("#erreur-installation").hidden = false;
      $("#btn-installer").textContent = "Réessayer";
      $("#btn-installer").hidden = false;
    },

    finPremierLancement() {
      $("#ecran-installation").hidden = true;
      notifier("Installation terminée ! Je démarre…");
    },
  };

  // Pour la conversation active après envoi : Python renvoie la liste, la plus récente en premier
  const listeOrigine = window.dawaa.listeConversations;
  window.dawaa.listeConversations = function (liste) {
    if (conversationActive === null && fil.querySelector(".message") && liste.length) conversationActive = liste[0].id;
    listeOrigine(liste);
  };

  texte.focus();
})();
