/* =========================================================================
   Gestionnaire de TOUS les textes du site, depuis le tableau de bord.
   Choisissez une page : le module la lit, en extrait chaque bloc de texte
   modifiable (mêmes règles que l'édition en ligne) et affiche un champ pour
   chacun. Les modifications sont enregistrées exactement comme si vous les
   aviez faites directement sur la page.
   ========================================================================= */
(function () {
  "use strict";

  var PAGES = [
    { file: "index.html",             label: "Accueil" },
    { file: "formation.html",         label: "Formation — choix des parcours" },
    { file: "formation-trading.html", label: "Formation — Trading (détail)" },
    { file: "formation-finance.html", label: "Formation — Finance de marché (détail)" },
    { file: "candidature.html",       label: "Formation — candidature" },
    { file: "accompagnement.html",    label: "Accompagnement des entreprises" },
    { file: "conseil.html",           label: "Conseil en investissement" },
    { file: "ressources.html",        label: "Ressources" },
    { file: "faq.html",               label: "FAQ" },
    { file: "personnel.html",         label: "À propos" },
    { file: "contact.html",           label: "Contact" },
    { file: "galerie.html",           label: "Galerie" },
    { file: "mentions-legales.html",  label: "Mentions légales" },
    { file: "confidentialite.html",   label: "Confidentialité" },
    { file: "risques.html",           label: "Avertissement sur les risques" },
  ];

  // Mêmes règles que components.js (pour produire EXACTEMENT les mêmes clés).
  var EDIT_SELECTOR = "h1,h2,h3,h4,h5,p,li,.eyebrow,.lead,figcaption,blockquote,[data-edit]";

  function domPath(el, body) {
    var parts = [];
    while (el && el !== body && el.nodeType === 1) {
      var parent = el.parentNode; if (!parent) break;
      parts.unshift(el.tagName + Array.prototype.indexOf.call(parent.children, el));
      el = parent;
    }
    return parts.join("/");
  }

  function editableElements(doc) {
    var body = doc.body, set = [];
    body.querySelectorAll(EDIT_SELECTOR + ",[data-text]").forEach(function (el) {
      if (el.hasAttribute("data-noedit")) return;
      if (el.querySelector(EDIT_SELECTOR + ",[data-text]")) return;          // blocs feuilles uniquement
      var inChrome = el.closest(".site-header, .site-footer, form, .admin-bar, .preview-bar");
      if (inChrome && !el.hasAttribute("data-text")) return;
      if (!el.textContent.trim()) return;
      set.push(el);
    });
    return set;
  }

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  var state = { rows: [], file: null };

  function load(file) {
    var host = $("contentList");
    if (!host) return;
    state.file = file; state.rows = [];
    host.innerHTML = '<p class="muted">Chargement des textes…</p>';

    Promise.all([
      fetch(file, { cache: "no-store" }).then(function (r) { return r.text(); }),
      fetch("/api/content").then(function (r) { return r.ok ? r.json() : {}; }).catch(function () { return {}; }),
      fetch("/api/settings").then(function (r) { return r.ok ? r.json() : {}; }).catch(function () { return {}; }),
    ]).then(function (res) {
      var html = res[0], contentMap = res[1] || {}, settings = res[2] || {};
      var texts = settings.texts || {};
      var doc = new DOMParser().parseFromString(html, "text/html");
      var pageKey = doc.body.getAttribute("data-page") || "page";
      var els = editableElements(doc);

      if (!els.length) { host.innerHTML = '<p class="muted">Aucun texte modifiable trouvé sur cette page.</p>'; return; }

      var groups = [], current = null;
      els.forEach(function (el, i) {
        // Titre de repère : la section la plus proche
        var sec = el.closest("section");
        var secName = sec ? (sec.getAttribute("id") || (sec.className || "").split(" ")[0] || "section") : "page";
        if (!current || current.name !== secName) { current = { name: secName, items: [] }; groups.push(current); }

        var info = el.hasAttribute("data-text")
          ? { kind: "setting", key: el.getAttribute("data-text") }
          : { kind: "content", key: pageKey + "|" + domPath(el, doc.body) };
        var original = el.innerHTML.trim();
        var value = info.kind === "setting"
          ? (texts[info.key] != null && texts[info.key] !== "" ? texts[info.key] : original)
          : (Object.prototype.hasOwnProperty.call(contentMap, info.key) ? contentMap[info.key] : original);

        var row = { id: "ct" + i, info: info, original: original, value: value, tag: el.tagName.toLowerCase() };
        state.rows.push(row);
        current.items.push(row);
      });

      host.innerHTML = groups.map(function (g) {
        return '<div class="settings-block"><h3 style="text-transform:capitalize">' + esc(g.name.replace(/-/g, " ")) + "</h3>" +
          g.items.map(function (r) {
            var big = r.value.length > 90;
            var label = r.tag === "h1" ? "Grand titre" : r.tag === "h2" ? "Titre" : r.tag === "h3" || r.tag === "h4" ? "Sous-titre"
              : r.tag === "li" ? "Élément de liste" : "Paragraphe";
            if (r.info.kind === "setting") label += " · réglage « " + r.info.key + " »";
            return '<div class="field field--full"><label for="' + r.id + '">' + esc(label) + "</label>" +
              (big
                ? '<textarea id="' + r.id + '" rows="3">' + esc(r.value) + "</textarea>"
                : '<input type="text" id="' + r.id + '" value="' + esc(r.value) + '" />') +
              "</div>";
          }).join("") + "</div>";
      }).join("");
    }).catch(function () {
      host.innerHTML = '<p class="form-msg err">Impossible de lire cette page.</p>';
    });
  }

  function save() {
    var msg = $("contentMsg");
    var changed = state.rows.filter(function (r) {
      var el = $(r.id); return el && el.value.trim() !== r.value.trim();
    });
    if (!changed.length) { msg.textContent = "Aucune modification à enregistrer."; msg.className = "form-msg"; return; }

    msg.textContent = "Enregistrement de " + changed.length + " texte(s)…"; msg.className = "form-msg";
    Promise.all(changed.map(function (r) {
      var el = $(r.id), val = el.value.trim();
      var url = r.info.kind === "setting" ? "/api/settings/text" : "/api/content";
      return fetch(url, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: r.info.key, value: val }),
      }).then(function (rp) {
        if (!rp.ok) throw new Error(r.info.key);
        r.value = val;                       // nouvelle référence
      });
    })).then(function () {
      msg.textContent = "✓ " + changed.length + " texte(s) enregistré(s). Rechargez la page du site pour voir le résultat.";
      msg.className = "form-msg ok";
    }).catch(function (e) {
      msg.textContent = "Échec sur « " + e.message + " ». Réessayez.";
      msg.className = "form-msg err";
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var sel = $("contentPage");
    if (!sel) return;
    sel.innerHTML = PAGES.map(function (p) { return '<option value="' + p.file + '">' + esc(p.label) + "</option>"; }).join("");
    sel.addEventListener("change", function () { load(sel.value); });
    var btn = $("contentSave");
    if (btn) btn.addEventListener("click", save);
    var reload = $("contentReload");
    if (reload) reload.addEventListener("click", function () { load(sel.value); });
    load(sel.value);
  });
})();
