/* =========================================================================
   Diagnostic de bancabilité — outil signature KBO Corporate Finance.
   Un vrai instrument, utilisable sans créer de compte : quelques questions
   simples sur l'activité → un score indicatif + une recommandation d'étape.
   Deux montages :
     KBODiag.mountMini(el)  — aperçu jouable dans le hero (3 questions, score live)
     KBODiag.mountFull(el)  — version complète (5 questions) + capture de contact
   Aucune donnée n'est envoyée tant que le visiteur ne demande pas son rapport.
   ========================================================================= */
(function () {
  "use strict";

  // --- Modèle de score (pondérations sur 100) --------------------------------
  //  Chaque facteur mesure une dimension réelle de la bancabilité d'une TPE.
  var W = { ca: 30, regularite: 20, mobile: 20, anciennete: 15, tenue: 15 };

  function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }

  // Sous-scores normalisés (0..1) → points
  function scoreParts(v) {
    return {
      ca: clamp((v.ca || 0) / 600000, 0, 1) * W.ca,              // CA mensuel FCFA
      regularite: ({ irr: 0, sais: 0.5, reg: 1 }[v.regularite] || 0) * W.regularite,
      mobile: ({ rare: 0, parfois: 0.5, systematique: 1 }[v.mobile] || 0) * W.mobile,
      anciennete: clamp((v.anciennete || 0) / 3, 0, 1) * W.anciennete, // années
      tenue: ({ non: 0, peu: 0.5, oui: 1 }[v.tenue] || 0) * W.tenue,
    };
  }

  // score complet (5 facteurs) sur 100
  function scoreFull(v) {
    var p = scoreParts(v);
    return Math.round(p.ca + p.regularite + p.mobile + p.anciennete + p.tenue);
  }
  // score mini (3 facteurs) rapporté à 100
  function scoreMini(v) {
    var p = scoreParts(v);
    var max = W.ca + W.regularite + W.mobile;
    return Math.round((p.ca + p.regularite + p.mobile) / max * 100);
  }

  function band(score) {
    if (score < 40) return { key: "low", label: "À structurer" };
    if (score < 70) return { key: "mid", label: "En bonne voie" };
    return { key: "high", label: "Prêt pour la bancarisation" };
  }

  function reco(score) {
    var b = band(score);
    if (b.key === "low") {
      return "Votre activité a des bases, mais une banque manque encore de <strong>traces exploitables</strong> pour vous évaluer. La première étape : rendre vos revenus lisibles (encaissements mobile money centralisés, un relevé d'activité simple). C'est exactement ce que nous mettons en place ensemble dès la phase 1.";
    }
    if (b.key === "mid") {
      return "Vous êtes <strong>à mi-chemin</strong>. Votre activité est réelle et régulière ; il reste à formaliser sa présentation (comptes simples, historique de flux) pour qu'un banquier puisse la lire sans effort. Un accompagnement de quelques semaines suffit généralement à franchir le seuil.";
    }
    return "Votre profil est <strong>déjà solide</strong>. L'enjeu n'est plus de structurer mais de <strong>valoriser</strong> : constituer un dossier de bancabilité présentable et choisir le bon interlocuteur bancaire. Nous pouvons préparer ce dossier avec vous directement.";
  }

  var FCFA = new Intl.NumberFormat("fr-FR");

  // --- Fabriques de composants -----------------------------------------------
  function rangeField(opts) {
    // opts: {id,label,min,max,step,value,fmt}
    var wrap = document.createElement("div");
    wrap.className = "diag-field";
    var out = document.createElement("span");
    out.className = "diag-field__val";
    var lab = document.createElement("label");
    lab.className = "diag-field__label";
    lab.setAttribute("for", opts.id);
    lab.innerHTML = "<span>" + opts.label + "</span>";
    lab.appendChild(out);
    var input = document.createElement("input");
    input.type = "range"; input.className = "diag-range";
    input.id = opts.id; input.min = opts.min; input.max = opts.max;
    input.step = opts.step; input.value = opts.value;
    function sync() { out.textContent = opts.fmt(+input.value); }
    input.addEventListener("input", function () { sync(); opts.onchange(+input.value); });
    sync();
    wrap.appendChild(lab); wrap.appendChild(input);
    return wrap;
  }

  function segField(opts) {
    // opts: {id,label,options:[{val,label}],value}
    var wrap = document.createElement("div");
    wrap.className = "diag-field";
    var lab = document.createElement("div");
    lab.className = "diag-field__label";
    lab.innerHTML = "<span>" + opts.label + "</span>";
    var seg = document.createElement("div");
    seg.className = "diag-seg"; seg.setAttribute("role", "group");
    seg.setAttribute("aria-label", opts.label);
    opts.options.forEach(function (o) {
      var b = document.createElement("button");
      b.type = "button"; b.textContent = o.label;
      b.setAttribute("aria-pressed", String(o.val === opts.value));
      b.addEventListener("click", function () {
        seg.querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-pressed", "false"); });
        b.setAttribute("aria-pressed", "true");
        opts.onchange(o.val);
      });
      seg.appendChild(b);
    });
    wrap.appendChild(lab); wrap.appendChild(seg);
    return wrap;
  }

  // Anneau SVG (jauge circulaire)
  function ring(size, stroke) {
    var r = (size - stroke) / 2, c = 2 * Math.PI * r;
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 " + size + " " + size);
    svg.setAttribute("width", size); svg.setAttribute("height", size);
    function circle(color, cls) {
      var el = document.createElementNS(ns, "circle");
      el.setAttribute("cx", size / 2); el.setAttribute("cy", size / 2); el.setAttribute("r", r);
      el.setAttribute("fill", "none"); el.setAttribute("stroke", color);
      el.setAttribute("stroke-width", stroke); el.setAttribute("stroke-linecap", "round");
      if (cls) el.setAttribute("class", cls);
      return el;
    }
    var track = circle("rgba(255,255,255,.16)");
    var prog = circle("currentColor", "diag-ring__prog");
    prog.setAttribute("stroke-dasharray", c);
    prog.setAttribute("stroke-dashoffset", c);
    prog.setAttribute("transform", "rotate(-90 " + size / 2 + " " + size / 2 + ")");
    prog.style.transition = "stroke-dashoffset .5s var(--ease,ease)";
    svg.appendChild(track); svg.appendChild(prog);
    return { svg: svg, set: function (pct) { prog.setAttribute("stroke-dashoffset", c * (1 - pct / 100)); } };
  }

  var bandColor = { low: "#f0a58a", mid: "#B8934A", high: "#7fd6a8" };

  // --- Version MINI (hero) ----------------------------------------------------
  function mountMini(el) {
    if (!el || el.__mounted) return; el.__mounted = true;
    var v = { ca: 150000, regularite: "sais", mobile: "parfois" };
    el.classList.add("diag-mini");
    el.innerHTML =
      '<div class="diag-mini__head"><span class="diag-mini__title">Suis-je bancable&nbsp;?</span>' +
      '<span class="badge-serious" style="font-size:.68rem">Aperçu · 30 s</span></div>' +
      '<p class="diag-mini__hint">Trois questions, un score indicatif en direct. Aucune donnée envoyée.</p>';
    var body = document.createElement("div");
    el.appendChild(body);

    var scoreWrap = document.createElement("div");
    scoreWrap.className = "diag-mini__score";
    var gaugeBox = document.createElement("div");
    gaugeBox.className = "diag-mini__gauge";
    var g = ring(60, 7);
    gaugeBox.appendChild(g.svg);
    var valEl = document.createElement("div");
    valEl.className = "diag-mini__score-value";
    valEl.style.cssText = "position:absolute;inset:0;display:grid;place-items:center;font-size:1rem";
    gaugeBox.appendChild(valEl);
    var lblEl = document.createElement("div");
    lblEl.className = "diag-mini__score-label";
    scoreWrap.appendChild(gaugeBox); scoreWrap.appendChild(lblEl);

    function refresh() {
      var s = scoreMini(v), b = band(s);
      g.svg.style.color = bandColor[b.key];
      g.set(s);
      valEl.textContent = s;
      lblEl.innerHTML = "<strong>" + b.label + "</strong><br>score de bancabilité";
    }

    body.appendChild(rangeField({
      id: "dm-ca", label: "Chiffre d'affaires mensuel", min: 0, max: 1000000, step: 25000, value: v.ca,
      fmt: function (x) { return FCFA.format(x) + " FCFA"; },
      onchange: function (x) { v.ca = x; refresh(); },
    }));
    body.appendChild(segField({
      id: "dm-reg", label: "Régularité de l'activité", value: v.regularite,
      options: [{ val: "irr", label: "Irrégulière" }, { val: "sais", label: "Saisonnière" }, { val: "reg", label: "Régulière" }],
      onchange: function (x) { v.regularite = x; refresh(); },
    }));
    body.appendChild(segField({
      id: "dm-mm", label: "Encaissements par mobile money", value: v.mobile,
      options: [{ val: "rare", label: "Rarement" }, { val: "parfois", label: "Parfois" }, { val: "systematique", label: "Toujours" }],
      onchange: function (x) { v.mobile = x; refresh(); },
    }));
    el.appendChild(scoreWrap);

    var cta = document.createElement("a");
    cta.href = "accompagnement.html#diagnostic";
    cta.className = "btn btn--primary";
    cta.style.cssText = "margin-top:1.1rem;width:100%;justify-content:center";
    cta.innerHTML = 'Faire le diagnostic complet <span class="arrow">→</span>';
    el.appendChild(cta);
    refresh();
  }

  // --- Version COMPLÈTE (page Accompagnement) --------------------------------
  function mountFull(el) {
    if (!el || el.__mounted) return; el.__mounted = true;
    var v = { ca: 150000, regularite: "sais", mobile: "parfois", anciennete: 2, tenue: "peu" };

    el.classList.add("diag");
    var panel = document.createElement("div");
    panel.className = "diag__panel";
    var result = document.createElement("div");
    result.className = "diag-result";
    el.appendChild(panel); el.appendChild(result);

    function q(node) { var w = document.createElement("div"); w.className = "diag__q"; w.appendChild(node); panel.appendChild(w); }

    q(rangeField({
      id: "df-ca", label: "Chiffre d'affaires mensuel estimé", min: 0, max: 1500000, step: 25000, value: v.ca,
      fmt: function (x) { return FCFA.format(x) + " FCFA"; },
      onchange: function (x) { v.ca = x; refresh(); },
    }));
    q(segField({
      id: "df-reg", label: "Votre activité est-elle régulière&nbsp;?", value: v.regularite,
      options: [{ val: "irr", label: "Irrégulière" }, { val: "sais", label: "Saisonnière" }, { val: "reg", label: "Régulière" }],
      onchange: function (x) { v.regularite = x; refresh(); },
    }));
    q(segField({
      id: "df-mm", label: "Encaissez-vous via mobile money&nbsp;?", value: v.mobile,
      options: [{ val: "rare", label: "Rarement" }, { val: "parfois", label: "Parfois" }, { val: "systematique", label: "Systématiquement" }],
      onchange: function (x) { v.mobile = x; refresh(); },
    }));
    q(rangeField({
      id: "df-anc", label: "Ancienneté de l'activité", min: 0, max: 10, step: 1, value: v.anciennete,
      fmt: function (x) { return x >= 10 ? "10 ans et +" : (x <= 0 ? "moins d'un an" : x + " an" + (x > 1 ? "s" : "")); },
      onchange: function (x) { v.anciennete = x; refresh(); },
    }));
    q(segField({
      id: "df-tenue", label: "Tenez-vous des traces écrites de vos revenus&nbsp;?", value: v.tenue,
      options: [{ val: "non", label: "Non" }, { val: "peu", label: "Un peu" }, { val: "oui", label: "Oui, régulièrement" }],
      onchange: function (x) { v.tenue = x; refresh(); },
    }));

    // Colonne résultat
    var g = ring(96, 9);
    result.innerHTML = '<h3>Votre score de bancabilité</h3>';
    var scoreRow = document.createElement("div");
    scoreRow.className = "diag-score";
    var ringBox = document.createElement("div");
    ringBox.className = "diag-score__ring";
    ringBox.appendChild(g.svg);
    var val = document.createElement("div");
    val.className = "diag-score__value num";
    ringBox.appendChild(val);
    var bandBox = document.createElement("div");
    var bandLbl = document.createElement("div");
    bandLbl.className = "diag-score__band";
    var bandSub = document.createElement("div");
    bandSub.style.cssText = "font-size:.85rem;color:#aebbd6;margin-top:.2rem";
    bandSub.textContent = "sur 100 — indicatif";
    bandBox.appendChild(bandLbl); bandBox.appendChild(bandSub);
    scoreRow.appendChild(ringBox); scoreRow.appendChild(bandBox);
    result.appendChild(scoreRow);

    var recoEl = document.createElement("p");
    recoEl.className = "diag-reco";
    result.appendChild(recoEl);

    // Capture de contact (rapport complet)
    var cap = document.createElement("div");
    cap.className = "diag-capture";
    cap.innerHTML =
      '<p style="font-size:.92rem;color:#cdd8ee;margin-bottom:.9rem">Recevez votre <strong style="color:#fff">rapport complet</strong> et la prochaine étape recommandée, par e-mail ou WhatsApp.</p>' +
      '<form id="diagForm" class="stack" novalidate>' +
      '<div class="field"><label for="diagNom">Nom / activité</label><input id="diagNom" name="nom" required></div>' +
      '<div class="field"><label for="diagContact">E-mail ou numéro WhatsApp</label><input id="diagContact" name="email" required placeholder="vous@exemple.com ou 229…"></div>' +
      '<button class="btn btn--primary" type="submit" style="justify-content:center">Recevoir mon rapport</button>' +
      '<span class="form-msg" id="diagMsg"></span>' +
      '</form>';
    result.appendChild(cap);

    function refresh() {
      var s = scoreFull(v), b = band(s);
      g.svg.style.color = bandColor[b.key];
      g.set(s);
      val.textContent = s;
      bandLbl.textContent = b.label;
      bandLbl.className = "diag-score__band diag-score__band--" + b.key;
      recoEl.innerHTML = reco(s);
    }
    refresh();

    // Envoi du rapport → réutilise l'endpoint de contact (stocké + envoyé par e-mail).
    var form = cap.querySelector("#diagForm");
    var msg = cap.querySelector("#diagMsg");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var nom = form.nom.value.trim(), contact = form.email.value.trim();
      if (!nom || !contact) { msg.textContent = "Merci d'indiquer votre nom et un moyen de contact."; msg.className = "form-msg err"; return; }
      var s = scoreFull(v), b = band(s);
      var payload = {
        _kind: "Diagnostic de bancabilité",
        nom: nom, email: contact,
        score: s + "/100 (" + b.label + ")",
        "chiffre d'affaires mensuel": FCFA.format(v.ca) + " FCFA",
        "régularité": { irr: "Irrégulière", sais: "Saisonnière", reg: "Régulière" }[v.regularite],
        "mobile money": { rare: "Rarement", parfois: "Parfois", systematique: "Systématiquement" }[v.mobile],
        "ancienneté": v.anciennete + " an(s)",
        "tenue de comptes": { non: "Non", peu: "Un peu", oui: "Oui" }[v.tenue],
      };
      var btn = form.querySelector('[type="submit"]');
      btn.disabled = true;
      msg.textContent = "Envoi en cours…"; msg.className = "form-msg";
      fetch("/api/contact/diagnostic", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (o) {
          if (!o.ok) throw new Error((o.j && o.j.error) || "Erreur");
          msg.innerHTML = "✓ Merci&nbsp;! Votre rapport arrive. Nous revenons vers vous rapidement.";
          msg.className = "form-msg ok";
          form.reset();
        })
        .catch(function (err) {
          var offline = /Failed to fetch|NetworkError/i.test(err.message);
          msg.textContent = offline ? "Serveur indisponible. Réessayez dans un instant." : err.message;
          msg.className = "form-msg err";
        })
        .finally(function () { btn.disabled = false; });
    });
  }

  // --- Auto-montage sur attributs data ---------------------------------------
  function autoMount() {
    document.querySelectorAll("[data-diag='mini']").forEach(mountMini);
    document.querySelectorAll("[data-diag='full']").forEach(mountFull);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", autoMount);
  else autoMount();

  window.KBODiag = { mountMini: mountMini, mountFull: mountFull, scoreFull: scoreFull, scoreMini: scoreMini };
})();
