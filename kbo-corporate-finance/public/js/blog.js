/* Blog rendering — fetches articles from the API and renders cards.
   Degrades gracefully if the API is unreachable (e.g. opened as a static file). */
(function () {
  const grid = document.getElementById("blogGrid");
  if (!grid) return;

  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  function formatDate(iso) {
    try {
      return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" });
    } catch (e) { return iso; }
  }

  const kindLabel = { video: "Vidéo", story: "Histoire", article: "Réflexion" };

  function mediaFor(a) {
    let inner;
    if (a.type === "video" && a.videoFile && !a.image) {
      // Miniature directe de la vidéo téléversée (verticale ou horizontale)
      inner = `<video src="${esc(a.videoFile)}#t=0.1" muted playsinline preload="metadata"></video>`;
    } else {
      const src = a.image || "images/post-default.svg";
      inner = `<img src="${esc(src)}" alt="${esc(a.title)}" loading="lazy" />`;
    }
    if (a.type === "video") {
      return `<div class="post-card__media">${inner}<span class="post-card__play"><span></span></span></div>`;
    }
    return `<div class="post-card__media">${inner}</div>`;
  }

  function cardFor(a) {
    const cls = a.type === "video" ? "post-card post-card--video" : "post-card";
    const label = a.type === "video" ? "Regarder la vidéo" : (a.type === "story" ? "Lire l'histoire" : "Lire l'article");
    return `
      <article class="${cls} reveal is-in">
        <a href="article.html?id=${encodeURIComponent(a.id)}" aria-label="${esc(a.title)}">
          ${mediaFor(a)}
        </a>
        <div class="post-card__body">
          <div class="post-card__meta">
            <span class="tag">${esc(a.tag || kindLabel[a.type] || "Réflexion")}</span>
            <span>${formatDate(a.date)}</span>
          </div>
          <h3><a href="article.html?id=${encodeURIComponent(a.id)}" style="color:inherit">${esc(a.title)}</a></h3>
          <p>${esc(a.excerpt || "")}</p>
          <a class="post-card__link" href="article.html?id=${encodeURIComponent(a.id)}">${label} →</a>
        </div>
      </article>`;
  }

  fetch("/api/articles")
    .then(r => { if (!r.ok) throw new Error("api"); return r.json(); })
    .then(list => {
      if (!Array.isArray(list) || list.length === 0) {
        grid.innerHTML = `<p class="empty-state">Aucun article pour le moment. Les premières publications arrivent bientôt.</p>`;
        return;
      }
      grid.innerHTML = list.map(cardFor).join("");
    })
    .catch(() => {
      grid.innerHTML = `<p class="empty-state">Le blog se charge lorsque le serveur est démarré (<code>python3 server.py</code>). Aucun article à afficher pour l'instant.</p>`;
    });
})();
