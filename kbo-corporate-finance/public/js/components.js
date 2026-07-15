/* Shared header + footer, injected on every page.
   Set <body data-page="accueil|personnel|professionnel|contact"> to highlight nav.
   Live site settings (texts, email, socials, hero photo) come from /api/settings
   and are applied everywhere via applySettings(). */
(function () {
  const page = document.body.getAttribute("data-page") || "";
  const year = new Date().getFullYear();

  // Menu réduit : Personnel et Professionnel restent accessibles depuis les
  // boutons de la page d'accueil, mais sont retirés du menu de navigation.
  const links = [
    { href: "index.html", label: "Accueil", key: "accueil" },
    { href: "galerie.html", label: "Galerie", key: "galerie" },
    { href: "contact.html", label: "Contact", key: "contact" },
  ];

  const brand = `
    <a class="brand" href="index.html" aria-label="Accueil">
      <span class="brand__mark" data-text="brandMark">KBO</span>
      <span class="brand__sub" data-text="brandSub">corporate finance</span>
    </a>`;

  const header = `
    <header class="site-header">
      <div class="container">
        <nav class="nav" id="nav" aria-label="Navigation principale">
          ${brand}
          <button class="nav__toggle" id="navToggle" aria-label="Ouvrir le menu" aria-expanded="false" aria-controls="navLinks">
            <span></span>
          </button>
          <ul class="nav__links" id="navLinks">
            ${links.map(l => `<li><a href="${l.href}" class="${page === l.key ? "is-active" : ""}">${l.label}</a></li>`).join("")}
          </ul>
        </nav>
      </div>
    </header>`;

  const ic = {
    linkedin: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M4.98 3.5A2.5 2.5 0 1 1 5 8.5a2.5 2.5 0 0 1-.02-5zM3 9h4v12H3zM9 9h3.8v1.7h.05c.53-1 1.82-2.05 3.75-2.05C20.4 8.65 21 11 21 14.1V21h-4v-6.1c0-1.45-.03-3.3-2-3.3s-2.3 1.57-2.3 3.2V21H9z"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M18.9 3H22l-7 8 8.2 10h-6.4l-5-6.1L6 21H3l7.5-8.6L2.5 3h6.5l4.5 5.6zm-1.1 16h1.7L7.3 4.8H5.5z"/></svg>',
    youtube: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M23 12s0-3.2-.4-4.7a2.5 2.5 0 0 0-1.8-1.8C19.3 5 12 5 12 5s-7.3 0-8.8.5A2.5 2.5 0 0 0 1.4 7.3C1 8.8 1 12 1 12s0 3.2.4 4.7a2.5 2.5 0 0 0 1.8 1.8C4.7 19 12 19 12 19s7.3 0 8.8-.5a2.5 2.5 0 0 0 1.8-1.8C23 15.2 23 12 23 12zM9.8 15.3V8.7l5.7 3.3z"/></svg>',
    facebook: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M22 12a10 10 0 1 0-11.6 9.9v-7H7.9V12h2.5V9.8c0-2.5 1.5-3.9 3.8-3.9 1.1 0 2.2.2 2.2.2v2.5h-1.2c-1.2 0-1.6.8-1.6 1.6V12h2.7l-.4 2.9h-2.3v7A10 10 0 0 0 22 12z"/></svg>',
    instagram: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1.2" fill="currentColor" stroke="none"/></svg>',
    mail: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m4 7 8 6 8-6"/></svg>',
    gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="3.2"/><path d="M19.4 13a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 0 1-4 0v-.1A1.7 1.7 0 0 0 7 19.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 3 13H3a2 2 0 0 1 0-4h.1A1.7 1.7 0 0 0 4.7 7l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 10 4.7V4a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V11a2 2 0 0 1 0 4h-.7z"/></svg>',
  };

  const socialAnchor = (key, label) =>
    `<a href="#" data-social="${key}" aria-label="${label}" target="_blank" rel="noopener" style="display:none">${ic[key]}</a>`;

  const footer = `
    <footer class="site-footer">
      <div class="container">
        <div class="footer__grid">
          <div>
            <a class="brand" href="index.html">
              <span class="brand__mark" data-text="brandMark">KBO</span>
              <span class="brand__sub" data-text="brandSub">corporate finance</span>
            </a>
            <p class="footer__about" data-text="footerAbout">Obed Kabeya — banquier de marché & trader. Formation, structuration comptable et conseil en investissement, au service d'une finance lucide et exigeante.</p>
            <div class="footer__social">
              ${socialAnchor("linkedin", "LinkedIn")}
              ${socialAnchor("x", "X")}
              ${socialAnchor("youtube", "YouTube")}
              ${socialAnchor("facebook", "Facebook")}
              ${socialAnchor("instagram", "Instagram")}
              <a href="#" data-email-link aria-label="Email">${ic.mail}</a>
            </div>
          </div>
        </div>
        <div class="footer__bottom">
          <span class="footer__copy">© ${year} <span data-text="brandMark">KBO</span> Corporate Finance — <span data-text="name">Obed Kabeya</span>. Tous droits réservés.</span>
          <span class="footer__admin">
            <a href="#" data-email-link data-email-text>e-mail</a>
            <!-- Accès admin volontairement invisible : tapez 5x sur le logo, ou allez sur /admin.html -->
          </span>
        </div>
      </div>
    </footer>`;

  const h = document.getElementById("site-header");
  const f = document.getElementById("site-footer");
  if (h) h.outerHTML = header;
  if (f) f.outerHTML = footer;

  // Secret owner access: tap the footer copyright 5 times quickly → login page.
  // No visible admin link for visitors; only you know the gesture.
  (function () {
    const secret = document.querySelector(".footer__copy");
    if (!secret) return;
    secret.style.cursor = "default";
    let taps = 0, timer = null;
    const hit = () => {
      taps++;
      if (taps >= 5) { taps = 0; location.href = "admin.html"; return; }
      clearTimeout(timer);
      timer = setTimeout(() => { taps = 0; }, 1600);
    };
    secret.addEventListener("click", hit);
  })();

  // Burger toggle
  const nav = document.getElementById("nav");
  const toggle = document.getElementById("navToggle");
  if (nav && toggle) {
    toggle.addEventListener("click", () => {
      const open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Fermer le menu" : "Ouvrir le menu");
    });
    nav.querySelectorAll(".nav__links a").forEach(a =>
      a.addEventListener("click", () => nav.classList.remove("is-open"))
    );
    document.addEventListener("keydown", e => {
      if (e.key === "Escape") nav.classList.remove("is-open");
    });
  }

  // Subtle header elevation once the page is scrolled
  const hdr = document.querySelector(".site-header");
  if (hdr) {
    const onScroll = () => hdr.classList.toggle("scrolled", window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  // Reveal on scroll
  const obs = new IntersectionObserver((entries) => {
    entries.forEach(en => { if (en.isIntersecting) { en.target.classList.add("is-in"); obs.unobserve(en.target); } });
  }, { threshold: 0.12 });
  document.querySelectorAll(".reveal").forEach(el => obs.observe(el));

  // ---- Live settings: applied to every page ----
  let currentSettings = null;
  function applySettings(s) {
    if (!s) return;
    currentSettings = s;
    const texts = s.texts || {};
    document.querySelectorAll("[data-text]").forEach(el => {
      const v = texts[el.getAttribute("data-text")];
      if (v != null && v !== "") el.textContent = v;
    });
    const social = s.social || {};
    document.querySelectorAll("[data-social]").forEach(a => {
      const url = social[a.getAttribute("data-social")];
      if (url) { a.href = url; a.style.display = ""; }
      else { a.style.display = "none"; }
    });
    if (s.email) {
      document.querySelectorAll("[data-email-link]").forEach(a => { a.href = "mailto:" + s.email; });
      document.querySelectorAll("[data-email-text]").forEach(el => { el.textContent = s.email; });
    }
    const photo = document.getElementById("heroPhoto");
    if (photo && s.photo) photo.src = s.photo;
    // Editable images (biography, etc.)
    const images = s.images || {};
    document.querySelectorAll("[data-img]").forEach(el => {
      const src = images[el.getAttribute("data-img")];
      if (src) {
        const img = el.querySelector("img");
        if (img) img.src = src;
      }
    });
    document.dispatchEvent(new CustomEvent("kbo:settings", { detail: s }));
  }

  // ---- Editable free text (biography, service pages, all headings…) ----
  const EDIT_SELECTOR = "h1,h2,h3,h4,h5,p,li,.eyebrow,.lead,figcaption,blockquote";
  const pageKey = page || "page";

  function domPath(el) {
    const parts = [];
    while (el && el !== document.body && el.nodeType === 1) {
      const parent = el.parentNode; if (!parent) break;
      parts.unshift(el.tagName + Array.prototype.indexOf.call(parent.children, el));
      el = parent;
    }
    return parts.join("/");
  }

  // Text elements that may be edited. Elements with data-text are saved to the
  // site settings; everything else to the content store (keyed by position).
  function editableElements() {
    const set = new Set();
    document.querySelectorAll(EDIT_SELECTOR + ",[data-text]").forEach(el => {
      if (el.hasAttribute("data-noedit")) return;
      if (el.querySelector(EDIT_SELECTOR + ",[data-text]")) return;  // only leaf text blocks
      const inChrome = el.closest(".site-header, .site-footer, form, .admin-bar, .preview-bar");
      if (inChrome && !el.hasAttribute("data-text")) return;         // skip nav/footer chrome
      if (!el.textContent.trim()) return;
      set.add(el);
    });
    return [...set];
  }
  function editableKey(el) {
    if (el.hasAttribute("data-text")) return { kind: "setting", key: el.getAttribute("data-text") };
    return { kind: "content", key: pageKey + "|" + domPath(el) };
  }

  function applyContent(map) {
    if (!map) return;
    editableElements().forEach(el => {
      if (el.hasAttribute("data-text")) return;                 // handled by settings
      const k = pageKey + "|" + domPath(el);
      if (Object.prototype.hasOwnProperty.call(map, k)) el.innerHTML = map[k];
    });
    document.dispatchEvent(new CustomEvent("kbo:content"));
  }

  // ---- Editable images (every illustration/photo on the site) ----
  function editableImages() {
    const out = [];
    document.querySelectorAll("section img").forEach(img => {
      if (img.hasAttribute("data-noedit")) return;
      if (img.closest(".site-header, .site-footer, .admin-bar, #blogGrid, #galleryGrid")) return;
      if (img.closest("[data-slot]")) return;                    // géré par le système de slots
      out.push(img);
    });
    return out;
  }
  function imageKey(img) {
    if (img.id === "heroPhoto") return { kind: "setting-image", key: "photo" };
    const holder = img.closest("[data-img]");
    if (holder) return { kind: "setting-image", key: holder.getAttribute("data-img") };
    return { kind: "img", key: pageKey + "|" + domPath(img) };
  }
  function applyImageContent(map) {
    if (!map) return;
    editableImages().forEach(img => {
      const info = imageKey(img);
      if (info.kind !== "img") return;                          // photo/bio via settings
      if (Object.prototype.hasOwnProperty.call(map, info.key)) img.src = map[info.key];
    });
  }

  // ---- Image slots (carrousels d'images par emplacement) ----
  function defaultSlotImage(slot) {
    return slot.getAttribute("data-default") || "";
  }
  function renderSlot(slot, arr) {
    slot.__images = Array.isArray(arr) ? arr.slice() : null;
    const list = (slot.__images && slot.__images.length) ? slot.__images : null;
    if (!list) {
      // aucun override : garder / restaurer l'image par défaut
      const def = defaultSlotImage(slot);
      if (def) slot.innerHTML = '<img src="' + def + '" alt="">';
      return;
    }
    if (list.length === 1) {
      slot.innerHTML = '<img src="' + list[0] + '" alt="">';
      return;
    }
    const imgs = list.map(p => '<img src="' + p + '" alt="" loading="lazy">').join("");
    const dots = list.map((_, i) => '<button type="button" class="slot-dot' + (i === 0 ? " is-on" : "") + '" data-i="' + i + '" aria-label="Image ' + (i + 1) + '"></button>').join("");
    slot.innerHTML = '<div class="slot-carousel"><div class="slot-track">' + imgs + '</div><div class="slot-dots">' + dots + '</div></div>';
    wireSlotCarousel(slot);
  }
  function wireSlotCarousel(slot) {
    const track = slot.querySelector(".slot-track");
    const dots = [...slot.querySelectorAll(".slot-dot")];
    if (!track) return;
    const setActive = () => {
      const i = Math.round(track.scrollLeft / Math.max(1, track.clientWidth));
      dots.forEach((d, k) => d.classList.toggle("is-on", k === i));
      slot.__index = i;
    };
    track.addEventListener("scroll", () => { window.requestAnimationFrame(setActive); }, { passive: true });
    dots.forEach(d => d.addEventListener("click", () => {
      track.scrollTo({ left: track.clientWidth * parseInt(d.dataset.i, 10), behavior: "smooth" });
    }));
    // Défilement automatique (pause quand l'onglet n'est pas visible ou en édition)
    clearInterval(slot.__timer);
    slot.__timer = setInterval(() => {
      if (document.body.classList.contains("editing") || document.hidden) return;
      const n = dots.length; if (n < 2) return;
      const next = ((slot.__index || 0) + 1) % n;
      track.scrollTo({ left: track.clientWidth * next, behavior: "smooth" });
    }, 5000);
  }
  function applySlides(map) {
    document.querySelectorAll("[data-slot]").forEach(slot => {
      // mémorise l'image par défaut d'origine (avant tout remplacement)
      if (!slot.hasAttribute("data-default")) {
        const img = slot.querySelector("img");
        slot.setAttribute("data-default", img ? img.getAttribute("src") : "");
      }
      const key = slot.getAttribute("data-slot");
      renderSlot(slot, map ? map[key] : null);
    });
  }

  window.KBO = window.KBO || {};
  window.KBO.applySettings = applySettings;
  window.KBO.getSettings = () => currentSettings;
  window.KBO.editableElements = editableElements;
  window.KBO.editableKey = editableKey;
  window.KBO.editableImages = editableImages;
  window.KBO.imageKey = imageKey;
  window.KBO.renderSlot = renderSlot;

  fetch("/api/settings")
    .then(r => (r.ok ? r.json() : null))
    .then(applySettings)
    .catch(() => { /* offline: keep static defaults already in the markup */ });

  fetch("/api/content")
    .then(r => (r.ok ? r.json() : null))
    .then(applyContent)
    .catch(() => {});

  fetch("/api/imgcontent")
    .then(r => (r.ok ? r.json() : null))
    .then(applyImageContent)
    .catch(() => {});

  if (document.querySelector("[data-slot]")) {
    fetch("/api/slides")
      .then(r => (r.ok ? r.json() : null))
      .then(map => { applySlides(map); document.dispatchEvent(new CustomEvent("kbo:slides")); })
      .catch(() => applySlides(null));
  }

  // ---- Preview-as-visitor: force the pure visitor view even when logged in ----
  const previewVisitor = new URLSearchParams(location.search).get("visitor") === "1";
  if (previewVisitor) {
    const bar = document.createElement("div");
    bar.className = "preview-bar";
    bar.innerHTML = `<span>👁 Aperçu <strong>visiteur</strong> — voici exactement ce que voient vos visiteurs.</span>
      <a href="admin.html">Quitter l'aperçu</a>`;
    document.addEventListener("DOMContentLoaded", () => document.body.appendChild(bar));
    if (document.body) document.body.appendChild(bar);
    // Keep the visitor flag while navigating within the preview.
    document.addEventListener("click", (e) => {
      const a = e.target.closest && e.target.closest('a[href]');
      if (!a) return;
      const href = a.getAttribute("href");
      if (!href || /^(https?:|mailto:|tel:|#)/.test(href) || a.target === "_blank" || href.indexOf("admin.html") === 0) return;
      if (/[?&]visitor=1/.test(href)) return;
      e.preventDefault();
      const hash = href.indexOf("#"); const base = hash >= 0 ? href.slice(0, hash) : href; const frag = hash >= 0 ? href.slice(hash) : "";
      location.href = base + (base.includes("?") ? "&" : "?") + "visitor=1" + frag;
    });
    return; // do NOT enable admin mode in preview
  }

  // ---- Admin mode: driven by the SERVER (window.__KBO_ADMIN__ injected only
  //      into pages served to an authenticated admin). Visitors never get it. ----
  if (window.__KBO_ADMIN__ === true) {
    document.body.classList.add("is-admin");
    document.dispatchEvent(new CustomEvent("kbo:admin"));
  }
})();
