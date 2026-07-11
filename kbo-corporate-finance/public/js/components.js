/* Shared header + footer, injected on every page.
   Set <body data-page="accueil|personnel|professionnel|contact"> to highlight nav.
   Live site settings (texts, email, socials, hero photo) come from /api/settings
   and are applied everywhere via applySettings(). */
(function () {
  const page = document.body.getAttribute("data-page") || "";
  const year = new Date().getFullYear();

  const links = [
    { href: "index.html", label: "Accueil", key: "accueil" },
    { href: "personnel.html", label: "Personnel", key: "personnel" },
    { href: "galerie.html", label: "Galerie", key: "galerie" },
    { href: "professionnel.html", label: "Professionnel", key: "professionnel" },
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
            <li class="nav__admin-item"><a href="admin.html">⚙ Espace admin</a></li>
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
          <div>
            <h5>Navigation</h5>
            <ul>
              <li><a href="index.html">Accueil</a></li>
              <li><a href="personnel.html">Biographie & Blog</a></li>
              <li><a href="galerie.html">Galerie</a></li>
              <li><a href="professionnel.html">Services</a></li>
              <li><a href="contact.html">Contact</a></li>
            </ul>
          </div>
          <div>
            <h5>Services</h5>
            <ul>
              <li><a href="formation.html">Formation en finance des marchés</a></li>
              <li><a href="comptabilite.html">Comptabilité des jeunes entreprises</a></li>
              <li><a href="conseil.html">Conseil en investissement</a></li>
            </ul>
          </div>
        </div>
        <div class="footer__bottom">
          <span>© ${year} <span data-text="brandMark">KBO</span> Corporate Finance — <span data-text="name">Obed Kabeya</span>. Tous droits réservés.</span>
          <span class="footer__admin">
            <a href="#" data-email-link data-email-text>e-mail</a>
            <a href="admin.html" class="footer__gear" aria-label="Espace administration" title="Espace admin — gérer le site">${ic.gear}<span>Paramètres</span></a>
          </span>
        </div>
      </div>
    </footer>`;

  const h = document.getElementById("site-header");
  const f = document.getElementById("site-footer");
  if (h) h.outerHTML = header;
  if (f) f.outerHTML = footer;

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

  window.KBO = window.KBO || {};
  window.KBO.applySettings = applySettings;
  window.KBO.getSettings = () => currentSettings;

  fetch("/api/settings")
    .then(r => (r.ok ? r.json() : null))
    .then(applySettings)
    .catch(() => { /* offline: keep static defaults already in the markup */ });

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

  // ---- Admin mode: reveal admin-only UI only for a logged-in admin ----
  const token = localStorage.getItem("kbo_admin_pw");
  if (token) {
    fetch("/api/admin/verify", { headers: { "X-Admin-Password": token } })
      .then(r => {
        if (r.ok) {
          document.body.classList.add("is-admin");
          window.KBO.adminPassword = token;
          document.dispatchEvent(new CustomEvent("kbo:admin"));
        }
      })
      .catch(() => {});
  }
})();
