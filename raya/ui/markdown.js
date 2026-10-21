// Mini-rendu Markdown sûr (le texte est échappé avant toute mise en forme).
(function () {
  function echapper(t) {
    return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function enLigne(t) {
    t = echapper(t);
    const codes = [];
    t = t.replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return "\u0000" + (codes.length - 1) + "\u0000"; });
    t = t.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="#" data-lien="$2">$1</a>');
    t = t.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="#" data-lien="$2">$2</a>');
    t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    t = t.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
    t = t.replace(/\u0000(\d+)\u0000/g, (_, i) => "<code>" + codes[+i] + "</code>");
    return t;
  }

  function cellules(ligne) {
    return ligne.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
  }

  window.markdown = function (source) {
    const lignes = source.replace(/\r\n/g, "\n").split("\n");
    const html = [];
    let i = 0;
    while (i < lignes.length) {
      const ligne = lignes[i];
      if (/^```/.test(ligne)) {
        const bloc = [];
        i++;
        while (i < lignes.length && !/^```/.test(lignes[i])) bloc.push(lignes[i++]);
        i++;
        html.push("<pre><code>" + echapper(bloc.join("\n")) + "</code></pre>");
        continue;
      }
      let m = ligne.match(/^(#{1,6})\s+(.*)/);
      if (m) {
        const n = Math.min(m[1].length + 1, 4);
        html.push(`<h${n}>${enLigne(m[2])}</h${n}>`);
        i++;
        continue;
      }
      if (/^\s*\|.*\|\s*$/.test(ligne) && i + 1 < lignes.length && /^\s*\|?\s*:?-{2,}/.test(lignes[i + 1])) {
        const entete = cellules(ligne);
        i += 2;
        const corps = [];
        while (i < lignes.length && /^\s*\|/.test(lignes[i])) corps.push(cellules(lignes[i++]));
        html.push("<table><thead><tr>" + entete.map((c) => "<th>" + enLigne(c) + "</th>").join("") + "</tr></thead><tbody>" +
          corps.map((l) => "<tr>" + l.map((c) => "<td>" + enLigne(c) + "</td>").join("") + "</tr>").join("") + "</tbody></table>");
        continue;
      }
      if (/^\s*([-*•]|\d+[.)])\s+/.test(ligne)) {
        const ordonnee = /^\s*\d+[.)]/.test(ligne);
        const elements = [];
        while (i < lignes.length && /^\s*([-*•]|\d+[.)])\s+/.test(lignes[i])) {
          elements.push(lignes[i].replace(/^\s*([-*•]|\d+[.)])\s+/, ""));
          i++;
        }
        const balise = ordonnee ? "ol" : "ul";
        html.push(`<${balise}>` + elements.map((e) => "<li>" + enLigne(e) + "</li>").join("") + `</${balise}>`);
        continue;
      }
      if (/^\s*([-*_])\1{2,}\s*$/.test(ligne)) { html.push("<hr>"); i++; continue; }
      if (!ligne.trim()) { i++; continue; }
      const paragraphe = [];
      while (i < lignes.length && lignes[i].trim() && !/^(#{1,6}\s|```|\s*([-*•]|\d+[.)])\s+|\s*\|)/.test(lignes[i])) {
        paragraphe.push(enLigne(lignes[i++]));
      }
      if (!paragraphe.length) { paragraphe.push(enLigne(lignes[i++])); }
      html.push("<p>" + paragraphe.join("<br>") + "</p>");
    }
    return html.join("");
  };
})();
