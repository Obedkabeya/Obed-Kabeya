/* Public gallery. Grid modes via #galleryGrid[data-mode]:
   - "teaser": show up to data-limit items; hide the section if empty (Personnel).
   - "full":  show everything with a click-to-enlarge lightbox (galerie.html). */
(function () {
  const grid = document.getElementById("galleryGrid");
  if (!grid) return;
  const mode = grid.getAttribute("data-mode") || "full";
  const limit = parseInt(grid.getAttribute("data-limit"), 10) || 0;
  const section = grid.closest("section");
  const empty = document.getElementById("galleryEmpty");

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  let items = [];

  function itemHTML(g, i) {
    const media = g.kind === "video"
      ? `<video src="${esc(g.path)}" ${mode === "full" ? "" : "muted "}playsinline preload="metadata"></video><span class="gallery-item__play"></span>`
      : `<img src="${esc(g.path)}" alt="${esc(g.caption || "")}" loading="lazy">`;
    const cap = g.caption ? `<figcaption>${esc(g.caption)}</figcaption>` : "";
    const cls = "gallery-item" + (g.orientation === "vertical" ? " gallery-item--vertical" : "") + (g.kind === "video" ? " gallery-item--video" : "");
    const open = mode === "full" ? ` data-open="${i}" role="button" tabindex="0"` : "";
    return `<figure class="${cls}"${open}>${media}${cap}</figure>`;
  }

  function render(list) {
    items = Array.isArray(list) ? list : [];
    const shown = (mode === "teaser" && limit) ? items.slice(0, limit) : items;
    if (!items.length) {
      if (mode === "teaser" && section) { section.hidden = true; return; }
      grid.innerHTML = "";
      if (empty) empty.hidden = false;
      return;
    }
    if (section) section.hidden = false;
    if (empty) empty.hidden = true;
    grid.innerHTML = shown.map((g, i) => itemHTML(g, i)).join("");
    if (mode === "full") wireLightbox();
  }

  fetch("/api/gallery").then(r => r.json()).then(render).catch(() => { if (mode === "teaser" && section) section.hidden = true; });

  // ---------- Lightbox (full mode) ----------
  let lb, lbMedia, lbCap, idx = 0;
  function ensureLightbox() {
    if (lb) return;
    lb = document.createElement("div");
    lb.className = "lightbox"; lb.hidden = true;
    lb.innerHTML = `
      <button class="lightbox__close" aria-label="Fermer">×</button>
      <button class="lightbox__nav lightbox__prev" aria-label="Précédent">‹</button>
      <div class="lightbox__stage"><div class="lightbox__media"></div><div class="lightbox__cap"></div></div>
      <button class="lightbox__nav lightbox__next" aria-label="Suivant">›</button>`;
    document.body.appendChild(lb);
    lbMedia = lb.querySelector(".lightbox__media");
    lbCap = lb.querySelector(".lightbox__cap");
    lb.querySelector(".lightbox__close").addEventListener("click", close);
    lb.querySelector(".lightbox__prev").addEventListener("click", (e) => { e.stopPropagation(); go(-1); });
    lb.querySelector(".lightbox__next").addEventListener("click", (e) => { e.stopPropagation(); go(1); });
    lb.addEventListener("click", (e) => { if (e.target === lb || e.target.classList.contains("lightbox__stage")) close(); });
    document.addEventListener("keydown", (e) => {
      if (lb.hidden) return;
      if (e.key === "Escape") close();
      else if (e.key === "ArrowLeft") go(-1);
      else if (e.key === "ArrowRight") go(1);
    });
  }
  function show(i) {
    idx = (i + items.length) % items.length;
    const g = items[idx];
    lbMedia.className = "lightbox__media" + (g.orientation === "vertical" ? " is-vertical" : "");
    lbMedia.innerHTML = g.kind === "video"
      ? `<video src="${esc(g.path)}" controls autoplay playsinline></video>`
      : `<img src="${esc(g.path)}" alt="${esc(g.caption || "")}">`;
    lbCap.textContent = g.caption || "";
    lbCap.style.display = g.caption ? "" : "none";
  }
  function open(i) { ensureLightbox(); lb.hidden = false; document.body.style.overflow = "hidden"; show(i); }
  function close() { if (!lb) return; lb.hidden = true; lbMedia.innerHTML = ""; document.body.style.overflow = ""; }
  function go(d) { show(idx + d); }

  function wireLightbox() {
    grid.querySelectorAll("[data-open]").forEach(el => {
      const i = parseInt(el.getAttribute("data-open"), 10);
      el.addEventListener("click", () => open(i));
      el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(i); } });
    });
  }
})();
