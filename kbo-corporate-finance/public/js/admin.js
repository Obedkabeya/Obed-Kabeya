/* KBO admin dashboard — authentification par session (cookie). Aucune donnée
   sensible en localStorage : le cookie HttpOnly est envoyé automatiquement. */
(function () {
  const $ = (id) => document.getElementById(id);

  const loginPane = $("loginPane"), dashboard = $("dashboard");
  const loginForm = $("loginForm"), loginMsg = $("loginMsg");
  const SOCIAL = ["linkedin", "x", "youtube", "facebook", "instagram"];

  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (iso) => { try { return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" }); } catch { return iso; } };
  const kb = (n) => n > 1048576 ? (n / 1048576).toFixed(1) + " Mo" : Math.max(1, Math.round(n / 1024)) + " Ko";

  function showToast(text) {
    const t = $("toast"); $("toastText").textContent = text || "Modifications enregistrées";
    t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 3200);
  }

  // ---------- raw upload (images + vidéos) — cookie de session envoyé auto ----------
  function uploadRaw(file) {
    return fetch("/api/upload-raw", {
      method: "POST",
      headers: { "X-Filename": encodeURIComponent(file.name), "Content-Type": file.type || "application/octet-stream" },
      body: file,
    }).then(r => r.json().then(j => { if (!r.ok) throw new Error(j.error || "Upload impossible."); return j; }));
  }

  // ---------- auth (session) ----------
  function showDashboard() {
    loginPane.hidden = true; dashboard.hidden = false;
    loadSettings(); loadArticles(); loadMedia();
  }
  // Déjà connecté ? (cookie de session valide côté serveur)
  fetch("/api/me").then(r => r.json()).then(m => { if (m.role === "admin") showDashboard(); }).catch(() => {});

  loginForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const val = $("pw").value;
    loginMsg.textContent = "Vérification…"; loginMsg.className = "form-msg";
    fetch("/api/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: val }),
    })
      .then(r => r.json().then(j => ({ ok: r.ok, j })))
      .then(({ ok, j }) => {
        if (ok && j.role === "admin") { loginMsg.textContent = ""; $("pw").value = ""; showDashboard(); }
        else { loginMsg.textContent = j.error || "Mot de passe incorrect."; loginMsg.className = "form-msg err"; }
      })
      .catch(() => { loginMsg.textContent = "Serveur injoignable. Démarrez « python3 server.py »."; loginMsg.className = "form-msg err"; });
  });
  $("logoutBtn").addEventListener("click", () => {
    fetch("/api/logout", { method: "POST" }).finally(() => {
      dashboard.hidden = true; loginPane.hidden = false; $("pw").value = "";
    });
  });

  // ---------- tabs ----------
  const SETTINGS_TABS = ["identite", "textes", "reseaux"];
  $("adminTabs").addEventListener("click", (e) => {
    const btn = e.target.closest(".admin-tab"); if (!btn || !btn.dataset.tab) return;
    const tab = btn.dataset.tab;
    document.querySelectorAll(".admin-tab").forEach(b => b.classList.toggle("is-active", b === btn));
    const inSettings = SETTINGS_TABS.includes(tab);
    $("settingsForm").style.display = inSettings ? "" : "none";
    document.querySelectorAll(".tabpanel").forEach(p => {
      p.classList.toggle("is-active", p.dataset.panel === tab);
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  // ---------- settings ----------
  function fillSettings(s) {
    const texts = s.texts || {};
    document.querySelectorAll("[data-textkey]").forEach(el => { el.value = texts[el.dataset.textkey] || ""; });
    $("email").value = s.email || "";
    const social = s.social || {};
    SOCIAL.forEach(k => { $(k).value = social[k] || ""; });
    currentPhoto = s.photo || "images/portrait.svg";
    $("photoPreview").src = currentPhoto;
    $("emailStatus").textContent = s._emailConfigured
      ? "✓ L'envoi d'e-mail est actif : les messages seront livrés à cette adresse."
      : "Les messages sont enregistrés et affichés dans le terminal du serveur. Pour l'envoi automatique par e-mail, configurez le SMTP (voir README).";
    syncTitlePreview();
  }
  function loadSettings() {
    fetch("/api/settings").then(r => r.json()).then(fillSettings).catch(() => {});
  }
  function syncTitlePreview() {
    $("titlePreviewName").textContent = $("name").value || "votre nom";
    $("titlePreviewRole").textContent = $("role").value || "votre rôle";
  }
  $("name").addEventListener("input", syncTitlePreview);
  $("role").addEventListener("input", syncTitlePreview);

  let currentPhoto = "images/portrait.svg";
  $("photoFile").addEventListener("change", () => {
    const file = $("photoFile").files[0]; if (!file) return;
    $("photoName").textContent = "Téléversement…";
    uploadRaw(file).then(j => { currentPhoto = j.path; $("photoPreview").src = j.path; $("photoName").textContent = file.name; loadMedia(); })
      .catch(err => { $("photoName").textContent = err.message; });
  });

  $("settingsForm").addEventListener("submit", (e) => {
    e.preventDefault();
    if (!$("email").value.trim() || !$("name").value.trim()) {
      $("saveMsg").textContent = "Le nom et l'e-mail sont obligatoires."; $("saveMsg").className = "form-msg err"; return;
    }
    const texts = {}; document.querySelectorAll("[data-textkey]").forEach(el => { texts[el.dataset.textkey] = el.value.trim(); });
    const social = {}; SOCIAL.forEach(k => { social[k] = $(k).value.trim(); });
    const payload = { email: $("email").value.trim(), photo: currentPhoto, social, texts };
    $("saveBtn").disabled = true; $("saveMsg").textContent = "Enregistrement…"; $("saveMsg").className = "form-msg";
    fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
      .then(r => r.json().then(j => ({ ok: r.ok, j })))
      .then(({ ok, j }) => {
        if (!ok) throw new Error(j.error || "Erreur d'enregistrement.");
        $("saveMsg").textContent = "✓ Enregistré."; $("saveMsg").className = "form-msg ok";
        fillSettings(j.settings);
        if (window.KBO && window.KBO.applySettings) window.KBO.applySettings(j.settings);
        showToast("Modifications publiées sur tout le site");
      })
      .catch(err => { $("saveMsg").textContent = err.message; $("saveMsg").className = "form-msg err"; })
      .finally(() => { $("saveBtn").disabled = false; });
  });

  // ---------- blog & histoires ----------
  const aType = $("a_type");
  function toggleVideoFields() {
    const isVideo = aType.value === "video";
    document.querySelectorAll(".video-only").forEach(el => { el.hidden = !isVideo; });
  }
  aType.addEventListener("change", toggleVideoFields);
  toggleVideoFields();

  function setImgPreview(box, path, isVideo) {
    box.classList.remove("is-empty");
    box.innerHTML = isVideo ? `<video src="${esc(path)}" muted></video>` : `<img src="${esc(path)}" alt="">`;
  }
  $("a_imageFile").addEventListener("change", () => {
    const file = $("a_imageFile").files[0]; if (!file) return;
    $("a_imageName").textContent = "Téléversement…";
    uploadRaw(file).then(j => { $("a_image").value = j.path; setImgPreview($("a_imagePreview"), j.path, false); $("a_imageName").textContent = file.name; loadMedia(); })
      .catch(err => { $("a_imageName").textContent = err.message; });
  });
  $("a_videoFile").addEventListener("change", () => {
    const file = $("a_videoFile").files[0]; if (!file) return;
    $("a_videoName").textContent = "Téléversement de la vidéo…";
    uploadRaw(file).then(j => { $("a_videoPath").value = j.path; setImgPreview($("a_videoPreview"), j.path, true); $("a_videoName").textContent = file.name; loadMedia(); })
      .catch(err => { $("a_videoName").textContent = err.message; });
  });

  // media picker for article image
  $("a_pickImage").addEventListener("click", () => openPicker((item) => {
    $("a_image").value = item.path; setImgPreview($("a_imagePreview"), item.path, item.kind === "video");
    $("a_imageName").textContent = item.title || item.name;
  }));

  $("articleForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData($("articleForm")).entries());
    $("articleMsg").textContent = "Publication…"; $("articleMsg").className = "form-msg";
    fetch("/api/articles", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) })
      .then(r => r.json().then(j => ({ ok: r.ok, j })))
      .then(({ ok, j }) => {
        if (!ok) throw new Error(j.error || "Erreur");
        $("articleMsg").textContent = "✓ Publié."; $("articleMsg").className = "form-msg ok";
        $("articleForm").reset();
        $("a_image").value = ""; $("a_videoPath").value = "";
        $("a_imagePreview").innerHTML = ""; $("a_imagePreview").classList.add("is-empty");
        $("a_videoPreview").innerHTML = ""; $("a_videoPreview").classList.add("is-empty");
        $("a_date").value = new Date().toISOString().slice(0, 10);
        toggleVideoFields();
        loadArticles();
        showToast("Publication en ligne");
      })
      .catch(err => { $("articleMsg").textContent = err.message; $("articleMsg").className = "form-msg err"; });
  });

  function loadArticles() {
    const list = $("adminList");
    fetch("/api/articles").then(r => r.json()).then(items => {
      if (!items.length) { list.innerHTML = `<p class="muted">Aucune publication.</p>`; return; }
      const label = { article: "Article", story: "Histoire", video: "Vidéo" };
      list.innerHTML = items.map(a => `
        <div style="display:flex;justify-content:space-between;align-items:center;gap:1rem;padding:1rem 1.2rem;border:1px solid var(--line);border-radius:6px;background:#fff;">
          <div>
            <strong style="color:var(--navy)">${esc(a.title)}</strong>
            <div class="muted" style="font-size:.82rem">${label[a.type] || "Article"}${a.type === "video" && a.orientation === "vertical" ? " · verticale" : ""} · ${fmt(a.date)}</div>
          </div>
          <div style="display:flex;gap:.5rem;flex-shrink:0">
            <a class="btn btn--ghost" style="padding:.5em 1em;font-size:.8rem" href="article.html?id=${encodeURIComponent(a.id)}" target="_blank">Voir</a>
            <button class="btn btn--ghost" style="padding:.5em 1em;font-size:.8rem;border-color:#d9b3b0;color:#b3261e" data-del="${esc(a.id)}">Supprimer</button>
          </div>
        </div>`).join("");
      list.querySelectorAll("[data-del]").forEach(b => b.addEventListener("click", () => {
        if (!confirm("Supprimer cette publication ?")) return;
        fetch(`/api/articles/${encodeURIComponent(b.dataset.del)}`, { method: "DELETE" })
          .then(r => { if (!r.ok) throw new Error(); loadArticles(); }).catch(() => alert("Suppression impossible."));
      }));
    }).catch(() => { list.innerHTML = `<p class="form-msg err">Chargement impossible.</p>`; });
  }

  // ---------- médias ----------
  function mediaCardHTML(m, picker) {
    const thumb = m.kind === "video"
      ? `<video src="${esc(m.path)}" muted></video><span class="media-card__badge">Vidéo</span>`
      : `<img src="${esc(m.path)}" alt="${esc(m.title || "")}" loading="lazy"><span class="media-card__badge">Image</span>`;
    if (picker) return `<div class="media-card"><div class="media-card__thumb" data-pick="${esc(m.name)}">${thumb}</div></div>`;
    return `<div class="media-card">
      <div class="media-card__thumb">${thumb}</div>
      <div class="media-card__actions">
        <button class="copy" data-path="${esc(m.path)}">Copier le lien</button>
        <button class="del" data-name="${esc(m.name)}">Supprimer</button>
      </div>
    </div>`;
  }

  let mediaCache = [];
  function loadMedia() {
    fetch("/api/media").then(r => r.json()).then(items => {
      mediaCache = Array.isArray(items) ? items : [];
      const grid = $("mediaGrid");
      if (!mediaCache.length) { grid.innerHTML = `<p class="muted">Aucun média. Téléversez votre première image ou vidéo.</p>`; return; }
      grid.innerHTML = mediaCache.map(m => mediaCardHTML(m, false)).join("");
      grid.querySelectorAll(".copy").forEach(b => b.addEventListener("click", () => {
        const val = b.dataset.path;
        navigator.clipboard && navigator.clipboard.writeText(val);
        b.textContent = "Copié ✓"; setTimeout(() => (b.textContent = "Copier le lien"), 1500);
      }));
      grid.querySelectorAll(".del").forEach(b => b.addEventListener("click", () => {
        if (!confirm("Supprimer ce média ?")) return;
        fetch(`/api/media/${encodeURIComponent(b.dataset.name)}`, { method: "DELETE" })
          .then(r => { if (!r.ok) throw new Error(); loadMedia(); }).catch(() => alert("Suppression impossible."));
      }));
    }).catch(() => { $("mediaGrid").innerHTML = `<p class="form-msg err">Chargement impossible.</p>`; });
  }

  $("mediaFile").addEventListener("change", () => {
    const files = [...$("mediaFile").files]; if (!files.length) return;
    $("mediaMsg").textContent = `Téléversement de ${files.length} fichier(s)…`; $("mediaMsg").className = "form-msg";
    files.reduce((p, f) => p.then(() => uploadRaw(f)), Promise.resolve())
      .then(() => { $("mediaMsg").textContent = "✓ Ajouté."; $("mediaMsg").className = "form-msg ok"; $("mediaFile").value = ""; loadMedia(); })
      .catch(err => { $("mediaMsg").textContent = err.message; $("mediaMsg").className = "form-msg err"; loadMedia(); });
  });

  // ---------- media picker modal ----------
  let pickCb = null;
  function openPicker(cb) {
    pickCb = cb;
    const grid = $("pickerGrid");
    const imgs = mediaCache.filter(m => m.kind === "image");
    grid.innerHTML = imgs.length ? imgs.map(m => mediaCardHTML(m, true)).join("")
      : `<p class="muted">Aucune image téléversée. Utilisez « Téléverser une image » ou l'onglet Médias.</p>`;
    grid.querySelectorAll("[data-pick]").forEach(el => el.addEventListener("click", () => {
      const item = mediaCache.find(m => m.name === el.dataset.pick);
      if (item && pickCb) pickCb(item);
      closePicker();
    }));
    $("pickerModal").hidden = false;
  }
  function closePicker() { $("pickerModal").hidden = true; }
  $("pickerClose").addEventListener("click", closePicker);
  $("pickerModal").addEventListener("click", (e) => { if (e.target === $("pickerModal")) closePicker(); });

  // ---------- biography photo slots (save immediately) ----------
  ["bio1", "bio2", "bio3"].forEach(key => {
    const input = $(key + "File"); if (!input) return;
    input.addEventListener("change", () => {
      const file = input.files[0]; if (!file) return;
      uploadRaw(file)
        .then(up => fetch("/api/settings/image", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ key, path: up.path }),
        }).then(r => r.json().then(j => { if (!r.ok) throw new Error(j.error); return up; })))
        .then(up => { $(key + "Preview").src = up.path; loadMedia(); showToast("Photo de la biographie mise à jour"); })
        .catch(err => alert(err.message || "Erreur"));
      input.value = "";
    });
  });
  function fillBioSlots(images) {
    if (!images) return;
    if (images.bio1) $("bio1Preview").src = images.bio1;
    if (images.bio2) $("bio2Preview").src = images.bio2;
    if (images.bio3) $("bio3Preview").src = images.bio3;
  }

  // ---------- galerie ----------
  let galFileSel = null;
  const galFile = $("galFile");
  galFile.addEventListener("change", () => {
    galFileSel = galFile.files[0] || null;
    const isVideo = galFileSel && galFileSel.type.startsWith("video");
    document.querySelectorAll(".gal-video-only").forEach(el => { el.hidden = !isVideo; });
    $("galPublish").disabled = !galFileSel;
    $("galFileName").textContent = galFileSel ? galFileSel.name : "Aucun fichier sélectionné.";
    const box = $("galPreview");
    if (galFileSel) {
      const url = URL.createObjectURL(galFileSel);
      box.classList.remove("is-empty");
      box.innerHTML = isVideo ? `<video src="${url}" muted></video>` : `<img src="${url}" alt="">`;
    } else { box.innerHTML = ""; box.classList.add("is-empty"); }
  });

  $("galPublish").addEventListener("click", () => {
    if (!galFileSel) return;
    const isVideo = galFileSel.type.startsWith("video");
    const orient = (document.querySelector('input[name="galOrientation"]:checked') || {}).value || "landscape";
    $("galPublish").disabled = true; $("galMsg").textContent = "Publication…"; $("galMsg").className = "form-msg";
    uploadRaw(galFileSel)
      .then(up => fetch("/api/gallery", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: up.path, kind: isVideo ? "video" : "image", orientation: orient, caption: $("galCaption").value.trim(), published: true }),
      }).then(r => r.json().then(j => { if (!r.ok) throw new Error(j.error); return j; })))
      .then(() => {
        $("galMsg").textContent = "✓ Publié."; $("galMsg").className = "form-msg ok";
        galFileSel = null; galFile.value = ""; $("galCaption").value = "";
        $("galPreview").innerHTML = ""; $("galPreview").classList.add("is-empty");
        $("galFileName").textContent = "Aucun fichier sélectionné.";
        document.querySelectorAll(".gal-video-only").forEach(el => { el.hidden = true; });
        loadGalleryAdmin(); loadMedia();
        showToast("Ajouté à la galerie");
      })
      .catch(err => { $("galMsg").textContent = err.message; $("galMsg").className = "form-msg err"; $("galPublish").disabled = false; });
  });

  function loadGalleryAdmin() {
    const grid = $("galAdminGrid");
    fetch("/api/gallery?all=1").then(r => r.json()).then(items => {
      if (!Array.isArray(items) || !items.length) { grid.innerHTML = `<p class="muted">Aucun élément. Publiez votre première photo ou vidéo.</p>`; return; }
      grid.innerHTML = items.map(g => {
        const thumb = g.kind === "video"
          ? `<video src="${esc(g.path)}" muted></video><span class="media-card__badge">Vidéo${g.orientation === "vertical" ? " · 9:16" : ""}</span>`
          : `<img src="${esc(g.path)}" alt="" loading="lazy"><span class="media-card__badge">Photo</span>`;
        return `<div class="media-card" style="${g.published ? "" : "opacity:.55"}">
          <div class="media-card__thumb">${thumb}</div>
          ${g.caption ? `<div style="padding:.5rem .6rem;font-size:.78rem;color:var(--gray)">${esc(g.caption)}</div>` : ""}
          <div class="media-card__actions">
            <button class="pub" data-id="${esc(g.id)}" data-pub="${g.published ? 1 : 0}">${g.published ? "Masquer" : "Publier"}</button>
            <button class="del" data-id="${esc(g.id)}">Supprimer</button>
          </div>
        </div>`;
      }).join("");
      grid.querySelectorAll(".pub").forEach(b => b.addEventListener("click", () => {
        fetch(`/api/gallery/${encodeURIComponent(b.dataset.id)}`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ published: b.dataset.pub !== "1" }),
        }).then(r => { if (!r.ok) throw new Error(); loadGalleryAdmin(); }).catch(() => alert("Action impossible."));
      }));
      grid.querySelectorAll(".del").forEach(b => b.addEventListener("click", () => {
        if (!confirm("Supprimer cet élément de la galerie ?")) return;
        fetch(`/api/gallery/${encodeURIComponent(b.dataset.id)}`, { method: "DELETE" })
          .then(r => { if (!r.ok) throw new Error(); loadGalleryAdmin(); }).catch(() => alert("Suppression impossible."));
      }));
    }).catch(() => { grid.innerHTML = `<p class="form-msg err">Chargement impossible.</p>`; });
  }

  // ---------- compte : état e-mail (via variables d'environnement) + mot de passe ----------
  function loadMailConfig() {
    fetch("/api/mailconfig")
      .then(r => r.json()).then(c => {
        const el = $("mailStatus"); if (!el) return;
        if (c.active) {
          el.textContent = "✓ L'envoi d'e-mail est ACTIF (via " + (c.provider || "?") + ", expéditeur : " + (c.from || "?") + ").";
          el.style.color = "#1a7a4c";
        } else {
          el.textContent = "⚠ L'envoi d'e-mail n'est PAS actif — ajoutez BREVO_API_KEY (et MAIL_FROM) dans les variables du serveur.";
          el.style.color = "#b3261e";
        }
      }).catch(() => {});
  }
  $("mailTest").addEventListener("click", () => {
    $("mailMsg").textContent = "Envoi du test…"; $("mailMsg").className = "form-msg";
    fetch("/api/mailtest", { method: "POST" })
      .then(r => r.json().then(j => ({ ok: r.ok, j }))).then(({ ok, j }) => {
        if (ok && j.ok) { $("mailMsg").textContent = "✓ E-mail de test envoyé à " + j.to + ". Vérifiez votre boîte."; $("mailMsg").className = "form-msg ok"; }
        else throw new Error((j && j.error) || "Échec");
      }).catch(err => { $("mailMsg").textContent = "Échec : " + err.message + " — vérifiez l'e-mail et le mot de passe d'application."; $("mailMsg").className = "form-msg err"; });
  });
  $("pwSave").addEventListener("click", () => {
    const a = $("pwNew").value, b = $("pwConfirm").value;
    if (a.length < 4) { $("pwMsg").textContent = "Au moins 4 caractères."; $("pwMsg").className = "form-msg err"; return; }
    if (a !== b) { $("pwMsg").textContent = "Les deux mots de passe ne correspondent pas."; $("pwMsg").className = "form-msg err"; return; }
    fetch("/api/admin/password", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new: a }),
    }).then(r => r.json().then(j => ({ ok: r.ok, j }))).then(({ ok, j }) => {
      if (!ok) throw new Error(j.error || "Erreur");
      // La session en cours reste valide ; pas besoin de se reconnecter.
      $("pwNew").value = ""; $("pwConfirm").value = "";
      $("pwMsg").textContent = "✓ Mot de passe changé."; $("pwMsg").className = "form-msg ok";
      showToast("Mot de passe administrateur mis à jour");
    }).catch(err => { $("pwMsg").textContent = err.message; $("pwMsg").className = "form-msg err"; });
  });

  // hook into dashboard load + settings fill
  const _origShowDashboard = showDashboard;
  showDashboard = function () { _origShowDashboard(); loadGalleryAdmin(); loadMailConfig(); };
  const _origFill = fillSettings;
  fillSettings = function (s) { _origFill(s); fillBioSlots(s.images); };
})();
