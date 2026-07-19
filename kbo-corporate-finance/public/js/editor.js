/* Owner-only tools: a fixed admin bar + click-to-edit for every text on the site.
   Loads on public pages but does NOTHING for visitors — everything is gated behind
   body.is-admin (set by components.js only for a logged-in owner). */
(function () {
  function $(id) { return document.getElementById(id); }

  function init() {
    if (window.__KBO_ADMIN__ !== true) return;                 // serveur : admin uniquement
    if (!document.body.classList.contains("is-admin")) return;
    if (document.querySelector(".admin-bar")) return;
    if (new URLSearchParams(location.search).get("visitor") === "1") return; // preview mode
    if (!window.KBO || !window.KBO.editableElements) return;

    const bar = document.createElement("div");
    bar.className = "admin-bar";
    bar.innerHTML =
      '<span class="admin-bar__tag">● Mode administrateur</span>' +
      '<button type="button" class="admin-bar__btn" id="abEdit">✏️ Modifier le texte</button>' +
      '<a class="admin-bar__btn" href="admin.html">⚙ Tableau de bord</a>' +
      '<a class="admin-bar__btn" id="abPreview" href="?visitor=1">👁 Aperçu visiteur</a>' +
      '<button type="button" class="admin-bar__btn admin-bar__btn--out" id="abLogout">Déconnexion</button>' +
      '<span class="admin-bar__hint" id="abHint"></span>';
    document.body.appendChild(bar);
    document.body.classList.add("has-admin-bar");
    $("abPreview").href = location.pathname + "?visitor=1";

    // ---- Barre de mise en forme (style traitement de texte) ----
    // Apparaît en mode édition et s'applique au texte sélectionné / au bloc actif.
    let activeEl = null;
    const tb = document.createElement("div");
    tb.className = "fmt-bar";
    tb.hidden = true;
    tb.innerHTML =
      '<button type="button" data-cmd="bold" title="Gras"><b>G</b></button>' +
      '<button type="button" data-cmd="italic" title="Italique"><i>I</i></button>' +
      '<button type="button" data-cmd="underline" title="Souligné"><u>S</u></button>' +
      '<span class="fmt-bar__sep"></span>' +
      '<button type="button" data-align="left" title="Aligner à gauche">⯇</button>' +
      '<button type="button" data-align="center" title="Centrer">≡</button>' +
      '<button type="button" data-align="right" title="Aligner à droite">⯈</button>' +
      '<span class="fmt-bar__sep"></span>' +
      '<button type="button" data-size="-1" title="Réduire la taille">A−</button>' +
      '<button type="button" data-size="1" title="Agrandir la taille">A+</button>' +
      '<button type="button" data-case="upper" title="MAJUSCULES">AA</button>' +
      '<span class="fmt-bar__sep"></span>' +
      '<select class="fmt-bar__font" data-font title="Police du texte">' +
        '<option value="">Police…</option>' +
        '<option value="var(--title)">Titre (Archivo)</option>' +
        '<option value="var(--sans)">Texte (Inter)</option>' +
        '<option value="var(--mono)">Chiffres (Plex Mono)</option>' +
        '<option value="Georgia, \'Times New Roman\', serif">Classique (serif)</option>' +
      "</select>" +
      '<span class="fmt-bar__sep"></span>' +
      '<label class="fmt-bar__color" title="Couleur du texte">A<input type="color" data-color value="#1e3b8b"></label>' +
      '<button type="button" data-clear title="Effacer la mise en forme">✕ mise en forme</button>';
    document.body.appendChild(tb);

    // Ne jamais perdre la sélection quand on clique un bouton de la barre.
    // (On laisse passer les menus/champs, sinon la liste des polices ne s'ouvre pas.)
    tb.addEventListener("mousedown", (e) => {
      if (!e.target.closest("select, input")) e.preventDefault();
    });

    function targetEl() {
      return activeEl && activeEl.isContentEditable ? activeEl : null;
    }
    function afterFormat(el) { if (el) save(el); }

    // Les styles posés sur l'élément lui-même ne sont pas enregistrés (seul son
    // contenu l'est) : on les applique donc à un conteneur INTERNE, qui, lui,
    // fait partie du contenu et survit au rechargement.
    function fmtWrap(el) {
      let w = el.querySelector(":scope > span[data-fmt]");
      if (!w) {
        w = document.createElement("span");
        w.setAttribute("data-fmt", "");
        w.style.display = "block";
        while (el.firstChild) w.appendChild(el.firstChild);
        el.appendChild(w);
      }
      return w;
    }
    function unwrapFmt(el) {
      const w = el.querySelector(":scope > span[data-fmt]");
      if (!w) return;
      while (w.firstChild) el.insertBefore(w.firstChild, w);
      w.remove();
    }

    tb.addEventListener("click", (e) => {
      const btn = e.target.closest("button, label");
      if (!btn) return;
      const el = targetEl();
      if (!el) { hint("Cliquez d'abord dans un texte à modifier.", "err"); return; }
      el.focus();
      if (btn.dataset.cmd) {
        document.execCommand(btn.dataset.cmd, false, null);
      } else if (btn.dataset.align) {
        fmtWrap(el).style.textAlign = btn.dataset.align;
      } else if (btn.dataset.size) {
        const w = fmtWrap(el);
        const cur = parseFloat(getComputedStyle(w).fontSize) || 16;
        const next = Math.min(72, Math.max(10, cur + (parseInt(btn.dataset.size, 10) * 2)));
        w.style.fontSize = next + "px";
      } else if (btn.dataset.case) {
        const w = fmtWrap(el);
        w.style.textTransform = w.style.textTransform === "uppercase" ? "none" : "uppercase";
      } else if (btn.hasAttribute("data-clear")) {
        document.execCommand("removeFormat", false, null);
        unwrapFmt(el);
      } else { return; }
      afterFormat(el);
    });
    tb.querySelector("[data-font]").addEventListener("change", (e) => {
      const el = targetEl();
      if (!el) { hint("Cliquez d'abord dans un texte à modifier.", "err"); e.target.value = ""; return; }
      if (e.target.value) fmtWrap(el).style.fontFamily = e.target.value;
      e.target.value = "";
      afterFormat(el);
    });
    tb.querySelector("[data-color]").addEventListener("input", (e) => {
      const el = targetEl();
      if (!el) return;
      el.focus();
      document.execCommand("foreColor", false, e.target.value);
      afterFormat(el);
    });

    let editing = false;
    const editBtn = $("abEdit");
    editBtn.addEventListener("click", () => setEditing(!editing));
    $("abLogout").addEventListener("click", () => {
      fetch("/api/logout", { method: "POST" }).finally(() => { location.href = location.pathname; });
    });

    function setEditing(on) {
      editing = on;
      document.body.classList.toggle("editing", on);
      editBtn.classList.toggle("is-on", on);
      editBtn.textContent = on ? "✓ Terminer" : "✏️ Modifier le texte";
      hint(on ? "Cliquez un texte pour le modifier — il s'enregistre tout seul." : "");
      tb.hidden = !on;
      if (!on) activeEl = null;
      window.KBO.editableElements().forEach(el => {
        if (on) {
          el.setAttribute("contenteditable", "true");
          el.classList.add("kbo-editable");
          if (!el.__wired) {
            el.__wired = true;
            el.addEventListener("focus", () => { activeEl = el; });
            el.addEventListener("blur", () => save(el));
            el.addEventListener("keydown", (e) => {
              if (e.key === "Enter" && /^(H[1-5]|SPAN)$/.test(el.tagName)) { e.preventDefault(); el.blur(); }
              if (e.key === "Escape") el.blur();
            });
          }
        } else {
          el.removeAttribute("contenteditable");
          el.classList.remove("kbo-editable");
        }
      });
      wireImages(on);
      wireSlots(on);
    }

    // ---- Upload helper (cookie de session envoyé automatiquement) ----
    function chooseAndUpload(onDone) {
      const input = document.createElement("input");
      input.type = "file"; input.accept = "image/*"; input.style.display = "none";
      document.body.appendChild(input);
      input.addEventListener("change", () => {
        const file = input.files[0];
        if (!file) { input.remove(); return; }
        hint("Téléversement…");
        fetch("/api/upload-raw", {
          method: "POST",
          headers: { "X-Filename": encodeURIComponent(file.name), "Content-Type": file.type || "application/octet-stream" },
          body: file,
        })
          .then(r => r.json().then(j => { if (!r.ok) throw new Error(j.error); return j; }))
          .then(up => onDone(up.path))
          .catch(err => hint("Échec : " + (err.message || "image"), "err"))
          .finally(() => input.remove());
      });
      input.click();
    }

    // ---- Image slots : plusieurs images par carré (carrousel) ----
    function wireSlots(on) {
      document.querySelectorAll("[data-slot]").forEach(slot => {
        let bar = slot.querySelector(".slot-admin");
        if (on) {
          slot.classList.add("kbo-slot-editing");
          if (!bar) {
            bar = document.createElement("div");
            bar.className = "slot-admin";
            bar.innerHTML = '<button type="button" class="slot-admin__btn" data-act="add">＋ Ajouter une image</button>' +
                            '<button type="button" class="slot-admin__btn slot-admin__btn--del" data-act="del">🗑 Retirer l\'image affichée</button>' +
                            '<span class="slot-admin__count"></span>';
            slot.appendChild(bar);
            bar.querySelector('[data-act="add"]').addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); addToSlot(slot); });
            bar.querySelector('[data-act="del"]').addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); removeFromSlot(slot); });
          }
          updateSlotCount(slot);
        } else {
          slot.classList.remove("kbo-slot-editing");
          if (bar) bar.remove();
        }
      });
    }
    function currentSlotImages(slot) {
      if (Array.isArray(slot.__images) && slot.__images.length) return slot.__images.slice();
      const def = slot.getAttribute("data-default");
      return def ? [] : [];   // 1re image ajoutée remplace l'illustration par défaut
    }
    function saveSlot(slot, arr) {
      hint("Enregistrement…");
      return fetch("/api/slides", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: slot.getAttribute("data-slot"), paths: arr }),
      }).then(r => { if (!r.ok) throw new Error(); })
        .then(() => { window.KBO.renderSlot(slot, arr); wireSlots(true); hint("Image mise à jour ✓", "ok"); })
        .catch(() => hint("Échec de l'enregistrement", "err"));
    }
    function addToSlot(slot) {
      chooseAndUpload(path => { const arr = currentSlotImages(slot); arr.push(path); saveSlot(slot, arr); });
    }
    function removeFromSlot(slot) {
      const arr = currentSlotImages(slot);
      if (!arr.length) { hint("Cette image est l'illustration par défaut.", "err"); return; }
      const i = Math.min(slot.__index || 0, arr.length - 1);
      arr.splice(i, 1);
      saveSlot(slot, arr);
    }
    function updateSlotCount(slot) {
      const bar = slot.querySelector(".slot-admin__count");
      if (bar) { const n = (slot.__images && slot.__images.length) || 0; bar.textContent = n > 1 ? (n + " images — glissez pour défiler") : (n === 1 ? "1 image" : "image par défaut"); }
    }

    function save(el) {
      const info = window.KBO.editableKey(el);
      const value = el.innerHTML.trim();
      const url = info.kind === "setting" ? "/api/settings/text" : "/api/content";
      hint("Enregistrement…");
      fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key: info.key, value: value }),
      })
        .then(r => { if (!r.ok) throw new Error(); hint("Enregistré ✓", "ok"); })
        .catch(() => hint("Échec de l'enregistrement", "err"));
    }

    // ---- Editable images ----
    function wireImages(on) {
      window.KBO.editableImages().forEach(img => {
        const parent = img.parentElement;
        if (!parent) return;
        if (on) {
          parent.classList.add("kbo-imgwrap");
          if (!img.__imgwired) {
            img.__imgwired = true;
            const btn = document.createElement("button");
            btn.type = "button"; btn.className = "kbo-imgbtn"; btn.textContent = "📷 Changer l'image";
            btn.addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); pickImage(img); });
            parent.appendChild(btn);
            img.__imgbtn = btn;
          }
          if (img.__imgbtn) img.__imgbtn.style.display = "";
        } else {
          parent.classList.remove("kbo-imgwrap");
          if (img.__imgbtn) img.__imgbtn.style.display = "none";
        }
      });
    }

    function pickImage(img) {
      const input = document.createElement("input");
      input.type = "file"; input.accept = "image/*"; input.style.display = "none";
      document.body.appendChild(input);
      input.addEventListener("change", () => {
        const file = input.files[0];
        if (!file) { input.remove(); return; }
        hint("Téléversement de l'image…");
        fetch("/api/upload-raw", {
          method: "POST",
          headers: { "X-Filename": encodeURIComponent(file.name), "Content-Type": file.type || "application/octet-stream" },
          body: file,
        })
          .then(r => r.json().then(j => { if (!r.ok) throw new Error(j.error); return j; }))
          .then(up => {
            const info = window.KBO.imageKey(img);
            const url = info.kind === "setting-image" ? "/api/settings/image" : "/api/imgcontent";
            return fetch(url, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ key: info.key, path: up.path }),
            }).then(r => { if (!r.ok) throw new Error(); img.src = up.path; hint("Image mise à jour ✓", "ok"); });
          })
          .catch(err => hint("Échec : " + (err.message || "image"), "err"))
          .finally(() => input.remove());
      });
      input.click();
    }

    let ft;
    function hint(msg, kind) {
      const h = $("abHint");
      h.textContent = msg;
      h.style.color = kind === "ok" ? "#8fe3b0" : kind === "err" ? "#ffb4ad" : "";
      if (kind) { clearTimeout(ft); ft = setTimeout(() => { h.style.color = ""; h.textContent = editing ? "Cliquez un texte pour le modifier." : ""; }, 2200); }
    }
  }

  if (document.body.classList.contains("is-admin")) init();
  document.addEventListener("kbo:admin", init);
})();
