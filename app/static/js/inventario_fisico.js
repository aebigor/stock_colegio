(() => {
  "use strict";

  function copiarConFallback(texto) {
    const campo = document.createElement("textarea");
    campo.value = texto;
    campo.setAttribute("readonly", "");
    campo.style.position = "fixed";
    campo.style.top = "0";
    campo.style.left = "-9999px";
    campo.style.opacity = "0";
    document.body.appendChild(campo);
    campo.focus();
    campo.select();
    campo.setSelectionRange(0, campo.value.length);

    let copiado = false;
    try {
      copiado = document.execCommand("copy");
    } finally {
      campo.remove();
    }
    if (!copiado) {
      throw new Error("El navegador no permitió copiar el enlace.");
    }
  }

  async function copiarTexto(texto) {
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(texto);
        return;
      } catch (_error) {
        // Algunos navegadores bloquean el permiso; se intenta el método clásico.
      }
    }
    copiarConFallback(texto);
  }

  document.addEventListener("click", async (evento) => {
    const boton = evento.target.closest("[data-copy-url]");
    if (!boton || boton.disabled) return;

    const enlace = boton.dataset.copyUrl;
    if (!enlace) return;

    const etiqueta = boton.querySelector("[data-copy-label]");
    const estado = boton.closest(".public-link-note")?.querySelector("[data-copy-status]");
    const textoOriginal = etiqueta ? etiqueta.textContent : boton.textContent;
    boton.disabled = true;

    try {
      await copiarTexto(enlace);
      if (etiqueta) etiqueta.textContent = "¡Copiado!";
      if (estado) estado.textContent = "Enlace copiado. Ya puedes pegarlo en WhatsApp o correo.";
      boton.classList.remove("btn-outline-primary");
      boton.classList.add("btn-success");
    } catch (_error) {
      if (estado) estado.textContent = "No se pudo copiar automáticamente. Copia el enlace desde la ventana que aparece.";
      window.prompt("Copia este enlace para enviarlo a la profesora:", enlace);
    } finally {
      window.setTimeout(() => {
        if (etiqueta) etiqueta.textContent = textoOriginal;
        boton.classList.remove("btn-success");
        boton.classList.add("btn-outline-primary");
        boton.disabled = false;
      }, 2200);
    }
  });

  // La verificación se guarda en el servidor sin recargar la lista completa.
  // Así el usuario conserva exactamente su posición aunque revise cientos de grupos.
  document.addEventListener("submit", async (evento) => {
    const formulario = evento.target.closest("form[data-ajax-review-form]");
    if (!formulario) return;

    evento.preventDefault();
    const boton = formulario.querySelector("[data-review-button]");
    const feedback = formulario.querySelector("[data-review-feedback], .review-feedback");
    if (!boton || boton.disabled) return;

    const textoAnterior = boton.textContent.trim();
    const claseVerificada = "btn-success";
    const clasePendiente = "btn-outline-primary";
    boton.disabled = true;
    boton.textContent = "Guardando…";
    if (feedback) {
      feedback.classList.remove("visually-hidden", "text-danger");
      feedback.textContent = "";
    }

    try {
      const respuesta = await fetch(formulario.action, {
        method: "POST",
        body: new FormData(formulario),
        credentials: "same-origin",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          "Accept": "application/json"
        }
      });

      const tipo = respuesta.headers.get("content-type") || "";
      if (!respuesta.ok || !tipo.includes("application/json")) {
        let detalle = "No se pudo guardar la revisión. Actualiza la página e inténtalo de nuevo.";
        if (tipo.includes("application/json")) {
          const error = await respuesta.json();
          detalle = error.detail || detalle;
        }
        throw new Error(detalle);
      }

      const resultado = await respuesta.json();
      if (!resultado.ok) throw new Error(resultado.message || "No se pudo guardar la revisión.");

      const verificado = Boolean(resultado.verified);
      boton.dataset.verified = verificado ? "true" : "false";
      boton.classList.toggle(claseVerificada, verificado);
      boton.classList.toggle(clasePendiente, !verificado);
      boton.textContent = verificado ? "✓ Grupo verificado" : "Revisar grupo";
      formulario.dataset.saved = "true";
      if (feedback) {
        feedback.classList.remove("visually-hidden");
        feedback.textContent = resultado.message || "Guardado.";
      }
    } catch (error) {
      boton.textContent = textoAnterior;
      if (feedback) {
        feedback.classList.remove("visually-hidden");
        feedback.classList.add("text-danger");
        feedback.textContent = error.message;
      } else {
        window.alert(error.message);
      }
    } finally {
      boton.disabled = false;
    }
  });

})();
