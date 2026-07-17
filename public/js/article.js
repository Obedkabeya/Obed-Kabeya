/* Single article view. Reads ?id= and renders title, date, media and body. */
(function () {
  const root = document.getElementById("article");
  if (!root) return;
  const id = new URLSearchParams(location.search).get("id");

  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  const fmt = (iso) => { try { return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" }); } catch { return iso; } };

  // Turn a YouTube/Vimeo URL into an embeddable src, else null.
  function embed(url) {
    if (!url) return null;
    let m = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([\w-]{11})/);
    if (m) return `https://www.youtube.com/embed/${m[1]}`;
    m = url.match(/vimeo\.com\/(\d+)/);
    if (m) return `https://player.vimeo.com/video/${m[1]}`;
    return null;
  }

  function paragraphs(body) {
    return String(body || "").split(/\n{2,}/).map(p => `<p>${esc(p).replace(/\n/g, "<br>")}</p>`).join("");
  }

  const kindLabel = { video: "Vidéo", story: "Histoire", article: "Réflexion" };

  function render(a) {
    document.title = `${a.title} · Obed Kabeya`;
    let videoBlock = "";
    if (a.type === "video") {
      const vertical = a.orientation === "vertical";
      const cls = "article__video" + (vertical ? " article__video--vertical" : "");
      if (a.videoFile) {
        // Vidéo téléversée (idéale pour le format vertical / mobile)
        videoBlock = `<div class="${cls}"><video src="${esc(a.videoFile)}" controls playsinline preload="metadata"${a.image ? ` poster="${esc(a.image)}"` : ""}></video></div>`;
      } else {
        const emb = embed(a.video);
        if (emb) videoBlock = `<div class="article__video"><iframe src="${esc(emb)}" title="${esc(a.title)}" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe></div>`;
        else if (a.video) videoBlock = `<div class="${cls}"><video src="${esc(a.video)}" controls playsinline></video></div>`;
      }
    }
    // No separate hero when a video is present (the video is the hero).
    const showHero = a.image && !(a.type === "video");
    const hero = showHero
      ? `<div class="article__hero"><img src="${esc(a.image)}" alt="${esc(a.title)}"></div>`
      : (a.type === "video" ? "" : `<div class="article__hero"><img src="images/post-default.svg" alt="${esc(a.title)}"></div>`);

    root.innerHTML = `
      <p class="breadcrumb"><a href="personnel.html#blog">Blog</a> · ${esc(a.tag || kindLabel[a.type] || "Réflexion")}</p>
      <h1>${esc(a.title)}</h1>
      <p class="muted" style="letter-spacing:.08em;text-transform:uppercase;font-size:.8rem">${fmt(a.date)} · Obed Kabeya</p>
      <hr class="divider" />
      ${hero}
      ${videoBlock}
      <div class="article__body">${paragraphs(a.body || a.excerpt)}</div>
      ${shareBlock(a)}
    `;
    wireShare(a);
  }

  const ICON = {
    whatsapp: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 0 0-8.5 15.2L2 22l4.9-1.5A10 10 0 1 0 12 2zm5.8 14.1c-.2.7-1.4 1.3-2 1.4-.5.1-1.2.1-1.9-.1-.4-.1-1-.3-1.8-.6-3.1-1.3-5.1-4.4-5.3-4.6-.1-.2-1.2-1.6-1.2-3s.7-2.1 1-2.4c.2-.3.5-.4.7-.4h.5c.2 0 .4 0 .6.5l.8 2c.1.2.1.4 0 .5l-.4.6c-.2.2-.3.4-.1.7.2.3.9 1.4 1.9 2.3 1.3 1.1 2.3 1.5 2.6 1.6.2.1.4.1.6-.1l.7-.8c.2-.2.4-.2.6-.1l1.9.9c.3.2.5.2.5.4.1.1.1.7-.1 1.3z"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M18.9 3H22l-7 8 8.2 10h-6.4l-5-6.1L6 21H3l7.5-8.6L2.5 3h6.5l4.5 5.6zm-1.1 16h1.7L7.3 4.8H5.5z"/></svg>',
    facebook: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M22 12a10 10 0 1 0-11.6 9.9v-7H7.9V12h2.5V9.8c0-2.5 1.5-3.9 3.8-3.9 1.1 0 2.2.2 2.2.2v2.5h-1.2c-1.2 0-1.6.8-1.6 1.6V12h2.7l-.4 2.9h-2.3v7A10 10 0 0 0 22 12z"/></svg>',
    linkedin: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4.98 3.5A2.5 2.5 0 1 1 5 8.5a2.5 2.5 0 0 1-.02-5zM3 9h4v12H3zM9 9h3.8v1.7h.05c.53-1 1.82-2.05 3.75-2.05C20.4 8.65 21 11 21 14.1V21h-4v-6.1c0-1.45-.03-3.3-2-3.3s-2.3 1.57-2.3 3.2V21H9z"/></svg>',
    mail: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7 8 6 8-6"/></svg>',
    link: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/></svg>',
  };

  function shareBlock() {
    return `
      <div class="share">
        <span class="share__label">Partager</span>
        <a class="share__btn" data-share="whatsapp" target="_blank" rel="noopener" aria-label="Partager sur WhatsApp">${ICON.whatsapp}</a>
        <a class="share__btn" data-share="x" target="_blank" rel="noopener" aria-label="Partager sur X">${ICON.x}</a>
        <a class="share__btn" data-share="facebook" target="_blank" rel="noopener" aria-label="Partager sur Facebook">${ICON.facebook}</a>
        <a class="share__btn" data-share="linkedin" target="_blank" rel="noopener" aria-label="Partager sur LinkedIn">${ICON.linkedin}</a>
        <a class="share__btn" data-share="mail" aria-label="Partager par e-mail">${ICON.mail}</a>
        <button class="share__btn share__btn--copy" id="copyLink" type="button">${ICON.link}<span>Copier le lien</span></button>
        <span class="share__copied" id="copied" hidden>Lien copié ✓</span>
      </div>`;
  }

  function wireShare(a) {
    const url = location.href;
    const t = a.title || "";
    const enc = encodeURIComponent;
    const map = {
      whatsapp: `https://wa.me/?text=${enc(t + " — " + url)}`,
      x: `https://twitter.com/intent/tweet?text=${enc(t)}&url=${enc(url)}`,
      facebook: `https://www.facebook.com/sharer/sharer.php?u=${enc(url)}`,
      linkedin: `https://www.linkedin.com/sharing/share-offsite/?url=${enc(url)}`,
      mail: `mailto:?subject=${enc(t)}&body=${enc(url)}`,
    };
    root.querySelectorAll("[data-share]").forEach(el => { el.href = map[el.getAttribute("data-share")]; });
    const copy = root.querySelector("#copyLink");
    if (copy) copy.addEventListener("click", () => {
      const done = () => { const c = root.querySelector("#copied"); if (c) { c.hidden = false; setTimeout(() => (c.hidden = true), 2000); } };
      if (navigator.clipboard) navigator.clipboard.writeText(url).then(done).catch(done);
      else { const ta = document.createElement("textarea"); ta.value = url; document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); } catch (e) {} ta.remove(); done(); }
    });
  }

  if (!id) {
    root.innerHTML = `<p class="empty-state">Article introuvable. <a href="personnel.html#blog">Retour au blog</a>.</p>`;
    return;
  }

  fetch(`/api/articles/${encodeURIComponent(id)}`)
    .then(r => { if (!r.ok) throw new Error("nf"); return r.json(); })
    .then(render)
    .catch(() => {
      root.innerHTML = `<p class="empty-state">Cet article n'a pas pu être chargé. Assurez-vous que le serveur est démarré, puis <a href="personnel.html#blog">retournez au blog</a>.</p>`;
    });
})();
