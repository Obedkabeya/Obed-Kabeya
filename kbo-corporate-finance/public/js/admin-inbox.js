/* =========================================================================
   Boîte de réception + contacts + fréquentation.
   Tout ce que le site reçoit est visible ICI, même si l'e-mail ne fonctionne
   pas : candidatures, messages de contact, diagnostics, inscrits aux
   actualités, et statistiques de visite (anonymes).
   ========================================================================= */
(function () {
  "use strict";

  function $(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function fmt(iso) {
    try {
      return new Date(iso).toLocaleString("fr-FR",
        { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
    } catch (e) { return iso || ""; }
  }

  var KINDS = {
    "apply": "Candidature",
    "contact": "Message",
  };

  // ---------------- Messages reçus ----------------
  function loadInbox() {
    var host = $("inboxList");
    if (!host) return;
    host.innerHTML = '<p class="muted">Chargement…</p>';
    fetch("/api/submissions").then(function (r) { return r.ok ? r.json() : []; })
      .then(function (list) {
        if (!list.length) {
          host.innerHTML = '<p class="muted">Aucun message pour l\'instant. Tout ce que vos visiteurs envoient apparaîtra ici.</p>';
          $("inboxCount").textContent = "0";
          return;
        }
        $("inboxCount").textContent = String(list.length);
        host.innerHTML = list.map(function (s) {
          var f = s.fields || {};
          var titre = s.kind || (KINDS[s.category] || "Message") + " — " + (s.service || "");
          var rows = Object.keys(f).map(function (k) {
            return '<div class="inbox__row"><span>' + esc(k) + "</span><div>" + esc(f[k]).replace(/\n/g, "<br>") + "</div></div>";
          }).join("");
          var mail = f.email || "";
          return '<details class="inbox__item">' +
            "<summary><strong>" + esc(f.nom || "Sans nom") + "</strong>" +
            '<span class="inbox__tag">' + esc(titre) + "</span>" +
            '<span class="inbox__date">' + fmt(s.received) + "</span></summary>" +
            '<div class="inbox__body">' + rows +
            (mail ? '<div class="inbox__actions"><a class="btn btn--ghost" href="mailto:' + esc(mail) +
              '">Répondre par e-mail</a></div>' : "") +
            "</div></details>";
        }).join("");
      })
      .catch(function () { host.innerHTML = '<p class="form-msg err">Impossible de charger les messages.</p>'; });
  }

  // ---------------- Inscrits aux actualités ----------------
  var emails = [];
  function loadNews() {
    var host = $("newsList");
    if (!host) return;
    fetch("/api/newsletter").then(function (r) { return r.ok ? r.json() : []; })
      .then(function (list) {
        emails = list.map(function (s) { return s.email; });
        $("newsCount").textContent = String(list.length);
        if (!list.length) {
          host.innerHTML = '<p class="muted">Personne inscrit pour l\'instant. Le formulaire est en bas de chaque page.</p>';
          return;
        }
        host.innerHTML = '<div class="news-emails">' + list.map(function (s) {
          return "<div><span>" + esc(s.email) + "</span><em>" + fmt(s.date) + "</em></div>";
        }).join("") + "</div>";
      })
      .catch(function () { host.innerHTML = '<p class="form-msg err">Impossible de charger la liste.</p>'; });
  }

  function copyEmails() {
    if (!emails.length) return;
    var txt = emails.join(", ");
    var done = function () {
      var m = $("newsMsgAdmin");
      m.textContent = "✓ " + emails.length + " adresse(s) copiée(s). Collez-les dans le champ « Cci » de votre e-mail.";
      m.className = "form-msg ok";
    };
    if (navigator.clipboard) navigator.clipboard.writeText(txt).then(done).catch(done);
    else {
      var ta = document.createElement("textarea");
      ta.value = txt; document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); } catch (e) {}
      ta.remove(); done();
    }
  }

  function downloadCsv() {
    if (!emails.length) return;
    var csv = "email\n" + emails.join("\n");
    var blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "contacts-kbo.csv";
    document.body.appendChild(a); a.click(); a.remove();
  }

  // ---------------- Fréquentation ----------------
  function loadStats() {
    var host = $("statsBox");
    if (!host) return;
    fetch("/api/stats").then(function (r) { return r.ok ? r.json() : null; })
      .then(function (s) {
        if (!s) { host.innerHTML = '<p class="form-msg err">Statistiques indisponibles.</p>'; return; }
        var days = s.days || [];
        var max = Math.max.apply(null, days.map(function (d) { return d.views; }).concat([1]));
        var bars = days.slice(-14).map(function (d) {
          var h = Math.round((d.views / max) * 100);
          return '<div class="bar" title="' + esc(d.date) + " — " + d.views + ' vue(s)"><span style="height:' +
            Math.max(h, 3) + '%"></span></div>';
        }).join("");
        host.innerHTML =
          '<div class="stat-cards">' +
            '<div class="stat-card"><b>' + (s.total || 0) + "</b><span>visites au total</span></div>" +
            '<div class="stat-card"><b>' + (s.last30 || 0) + "</b><span>sur les 30 derniers jours</span></div>" +
          "</div>" +
          (days.length ? '<p class="muted" style="margin:1.2rem 0 .4rem;font-size:.9rem">14 derniers jours</p><div class="bars">' + bars + "</div>" : "") +
          '<div class="stat-lists">' +
            "<div><h4>Pages les plus vues</h4>" + (s.topPages || []).map(function (p) {
              return "<div><span>" + esc(p.page) + "</span><em>" + p.views + "</em></div>";
            }).join("") + "</div>" +
            "<div><h4>D'où viennent les visiteurs</h4>" + (s.topSources || []).map(function (p) {
              return "<div><span>" + esc(p.source) + "</span><em>" + p.views + "</em></div>";
            }).join("") + "</div>" +
          "</div>";
      })
      .catch(function () { host.innerHTML = '<p class="form-msg err">Statistiques indisponibles.</p>'; });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!$("inboxList")) return;
    var reload = $("inboxReload");
    if (reload) reload.addEventListener("click", function () { loadInbox(); loadNews(); loadStats(); });
    var cp = $("newsCopy"); if (cp) cp.addEventListener("click", copyEmails);
    var dl = $("newsCsv"); if (dl) dl.addEventListener("click", downloadCsv);
    // Chargement quand l'onglet est ouvert (et au démarrage)
    document.querySelectorAll('.admin-tab[data-tab="boite"]').forEach(function (b) {
      b.addEventListener("click", function () { loadInbox(); loadNews(); loadStats(); });
    });
    loadInbox(); loadNews(); loadStats();
  });
})();
