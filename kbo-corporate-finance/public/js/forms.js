/* Generic form submitter for candidature / contact forms.
   A form opts in with: data-endpoint="/api/..." and data-kind="Label".
   Its status <span> must have id="<formId minus 'Form'>Msg" (e.g. formationForm -> formationMsg). */
(function () {
  document.querySelectorAll("form[data-endpoint]").forEach((form) => {
    const endpoint = form.getAttribute("data-endpoint");
    const kind = form.getAttribute("data-kind") || "Message";
    const msgId = form.id.replace(/Form$/, "") + "Msg";
    const msg = document.getElementById(msgId);
    const submitBtn = form.querySelector('[type="submit"]');

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      if (!form.reportValidity()) return;

      const data = {};
      new FormData(form).forEach((v, k) => { data[k] = v; });
      data._kind = kind;

      if (msg) { msg.textContent = "Envoi en cours…"; msg.className = "form-msg"; }
      if (submitBtn) submitBtn.disabled = true;

      fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      })
        .then((r) => r.json().then((j) => ({ ok: r.ok, j })))
        .then(({ ok, j }) => {
          if (!ok) throw new Error(j && j.error ? j.error : "Une erreur est survenue.");
          if (msg) {
            msg.textContent = "✓ Merci ! Votre demande a bien été reçue. Vous serez recontacté par e-mail.";
            msg.className = "form-msg ok";
          }
          form.reset();
        })
        .catch((err) => {
          const offline = /Failed to fetch|NetworkError/i.test(err.message);
          if (msg) {
            msg.textContent = offline
              ? "Le serveur n'est pas démarré. Lancez « python3 server.py » puis réessayez."
              : err.message;
            msg.className = "form-msg err";
          }
        })
        .finally(() => { if (submitBtn) submitBtn.disabled = false; });
    });
  });
})();
