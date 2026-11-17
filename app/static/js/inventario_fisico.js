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
      if (etiqueta) etiqueta.textContent = "Enlace copiado";
      if (estado) estado.textContent = "Enlace copiado";
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
    const estadoEsperado = boton.dataset.verified !== "true";
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
      let resultado;

      if (respuesta.ok && tipo.toLowerCase().includes("application/json")) {
        resultado = await respuesta.json();
      } else {
        // Compatibilidad con servidores que aún respondan con la redirección
        // tradicional después de haber guardado correctamente la revisión.
        // No se confunde con una sesión vencida: el destino debe ser la pantalla
        // de revisión del mismo levantamiento.
        let destinoFinal = "";
        try {
          destinoFinal = new URL(respuesta.url, window.location.href).pathname;
        } catch (_error) {
          destinoFinal = "";
        }
        const redireccionTrasGuardar = respuesta.ok && respuesta.redirected &&
          /\/activos\/inventario-fisico\/\d+\/revisar\/?$/.test(destinoFinal);

        if (redireccionTrasGuardar) {
          resultado = {
            ok: true,
            verified: estadoEsperado,
            message: "Grupo guardado correctamente."
          };
        } else {
          let detalle = "No se pudo guardar la revisión. Verifica tu sesión e inténtalo de nuevo.";
          if (tipo.toLowerCase().includes("application/json")) {
            try {
              const error = await respuesta.json();
              detalle = error.detail || detalle;
            } catch (_error) { /* conserva el mensaje genérico */ }
          }
          throw new Error(detalle);
        }
      }

      if (!resultado || !resultado.ok) {
        throw new Error((resultado && resultado.message) || "No se pudo guardar la revisión.");
      }

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

  function recalcularResumenDevolucion() {
    const filas = Array.from(document.querySelectorAll(".return-group-row"));
    let entregadas = 0;
    let recibidas = 0;
    let nuevasTotal = 0;
    filas.forEach((fila) => {
      const entregada = Math.max(0, Number.parseInt(fila.dataset.delivered || "0", 10) || 0);
      const campo = fila.querySelector(".return-quantity");
      const encontrada = campo
        ? Math.max(0, Math.min(5000, Number.parseInt(campo.value || "0", 10) || 0))
        : Math.max(0, Number.parseInt(fila.querySelector("[data-found-value]")?.dataset.foundValue || fila.dataset.found || "0", 10) || 0);
      const recibida = Math.min(entregada, encontrada);
      const nuevas = Math.max(0, encontrada - entregada);
      const faltante = Math.max(0, entregada - encontrada);
      entregadas += entregada;
      recibidas += recibida;
      nuevasTotal += nuevas;
      const indicador = fila.querySelector(".return-missing-count");
      if (indicador) {
        indicador.textContent = String(faltante);
        indicador.classList.toggle("zero", faltante === 0);
      }
      const indicadorNuevas = fila.querySelector(".return-surplus-count");
      if (indicadorNuevas) {
        indicadorNuevas.textContent = String(nuevas);
        indicadorNuevas.classList.toggle("zero", nuevas === 0);
      }
      fila.dataset.found = String(encontrada);
      const observacion = fila.querySelector(".return-observation");
      if (observacion) {
        const hayDiferencia = faltante > 0 || nuevas > 0;
        observacion.required = hayDiferencia;
        observacion.classList.toggle("is-invalid", hayDiferencia && !observacion.value.trim());
      }
    });

    const summary = document.getElementById("return-summary");
    if (summary) {
      const faltantes = Math.max(0, entregadas - recibidas);
      const totalEntregadas = document.getElementById("return-total-delivered");
      const totalRecibidas = document.getElementById("return-total-returned");
      const totalNuevas = document.getElementById("return-total-new");
      const totalFaltantes = document.getElementById("return-total-missing");
      if (totalEntregadas) totalEntregadas.textContent = String(entregadas);
      if (totalRecibidas) totalRecibidas.textContent = String(recibidas + nuevasTotal);
      if (totalNuevas) totalNuevas.textContent = String(nuevasTotal);
      if (totalFaltantes) totalFaltantes.textContent = String(faltantes);
    }

    const formularios = Array.from(document.querySelectorAll("form[data-ajax-return-form]"));
    const todosGuardados = formularios.length > 0 && formularios.every((formulario) => formulario.dataset.saved === "true");
    const registrar = document.getElementById("register-return-button");
    const ayuda = document.getElementById("return-review-hint");
    if (registrar) registrar.disabled = !todosGuardados;
    if (ayuda) {
      if (!todosGuardados) {
        ayuda.textContent = "Guarda la cantidad y observación de todos los grupos primero.";
      } else {
        const faltantes = Math.max(0, entregadas - recibidas - 0);
        ayuda.textContent = (faltantes || nuevasTotal)
          ? `Se registrarán ${recibidas} unidades originales, ${nuevasTotal} nuevas y ${faltantes} faltantes; los faltantes seguirán prestados.`
          : "Todos los grupos están guardados y listos para registrar la devolución.";
      }
    }
  }

  function aplicarFiltrosDevolucion() {
    const filas = Array.from(document.querySelectorAll(".return-group-row"));
    const texto = (document.getElementById("return-search")?.value || "").trim().toLocaleLowerCase("es");
    const filtro = document.getElementById("return-filter")?.value || "all";
    let visibles = 0;
    filas.forEach((fila) => {
      const entregada = Math.max(0, Number.parseInt(fila.dataset.delivered || "0", 10) || 0);
      const campo = fila.querySelector(".return-quantity");
      const encontrada = campo
        ? Math.max(0, Number.parseInt(campo.value || "0", 10) || 0)
        : Math.max(0, Number.parseInt(fila.querySelector("[data-found-value]")?.dataset.foundValue || fila.dataset.found || "0", 10) || 0);
      const faltante = Math.max(0, entregada - encontrada);
      const nuevas = Math.max(0, encontrada - entregada);
      const formulario = fila.querySelector("form[data-ajax-return-form]");
      const guardado = formulario?.dataset.saved === "true";
      const coincideTexto = !texto || (fila.dataset.search || "").toLocaleLowerCase("es").includes(texto);
      let coincideEstado = true;
      if (filtro === "missing") coincideEstado = faltante > 0;
      else if (filtro === "surplus") coincideEstado = nuevas > 0;
      else if (filtro === "difference") coincideEstado = faltante > 0 || nuevas > 0;
      else if (filtro === "balanced") coincideEstado = faltante === 0 && nuevas === 0;
      else if (filtro === "pending") coincideEstado = Boolean(formulario) && !guardado;
      else if (filtro === "saved") coincideEstado = guardado || !formulario;
      const mostrar = coincideTexto && coincideEstado;
      fila.hidden = !mostrar;
      if (mostrar) visibles += 1;
    });
    const contador = document.getElementById("return-filter-count");
    if (contador) contador.textContent = `Mostrando ${visibles} de ${filas.length} grupos`;
  }

  document.getElementById("return-search")?.addEventListener("input", aplicarFiltrosDevolucion);
  document.getElementById("return-filter")?.addEventListener("change", aplicarFiltrosDevolucion);

  document.addEventListener("input", (evento) => {
    const campo = evento.target;
    if (!campo.matches(".return-quantity, .return-observation")) return;
    const fila = campo.closest(".return-group-row");
    const formulario = fila?.querySelector("form[data-ajax-return-form]");
    if (formulario) {
      formulario.dataset.saved = "false";
      const boton = formulario.querySelector("[data-return-save-button]");
      const feedback = formulario.querySelector(".return-feedback");
      if (boton) {
        boton.disabled = false;
        boton.textContent = "Guardar cambios";
        boton.classList.remove("btn-success");
        boton.classList.add("btn-outline-primary");
      }
      if (feedback) {
        feedback.textContent = "Cambios sin guardar";
        feedback.classList.remove("is-error");
      }
    }
    recalcularResumenDevolucion();
    aplicarFiltrosDevolucion();
  });

  document.addEventListener("submit", async (evento) => {
    const formulario = evento.target.closest("form[data-ajax-return-form]");
    if (!formulario) return;
    evento.preventDefault();

    const fila = formulario.closest(".return-group-row");
    const boton = formulario.querySelector("[data-return-save-button]");
    const feedback = formulario.querySelector(".return-feedback");
    if (!fila || !boton || boton.disabled) return;

    const inputCantidad = fila.querySelector(".return-quantity");
    const campoObservacion = fila.querySelector(".return-observation");
    const entregada = Math.max(0, Number.parseInt(fila.dataset.delivered || "0", 10) || 0);
    const recibida = Math.max(0, Number.parseInt(inputCantidad?.value || "0", 10) || 0);
    if (recibida > 5000) {
      if (feedback) {
        feedback.textContent = "La cantidad total no puede superar 5.000.";
        feedback.classList.add("is-error");
      }
      return;
    }
    if (recibida !== entregada && !campoObservacion?.value.trim()) {
      if (campoObservacion) {
        campoObservacion.required = true;
        campoObservacion.classList.add("is-invalid");
        campoObservacion.focus();
      }
      if (feedback) {
        feedback.textContent = "Explica por qué hay unidades faltantes o nuevas.";
        feedback.classList.add("is-error");
      }
      return;
    }

    const textoAnterior = boton.textContent;
    boton.disabled = true;
    boton.textContent = "Guardando…";
    if (feedback) {
      feedback.textContent = "";
      feedback.classList.remove("is-error");
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
      const tipo = (respuesta.headers.get("content-type") || "").toLowerCase();
      if (!respuesta.ok || !tipo.includes("application/json")) {
        let mensaje = "No se pudo guardar la devolución. Comprueba tu sesión e inténtalo de nuevo.";
        if (tipo.includes("application/json")) {
          try {
            const error = await respuesta.json();
            mensaje = error.detail || mensaje;
          } catch (_) { /* conserva el mensaje genérico */ }
        }
        throw new Error(mensaje);
      }
      const resultado = await respuesta.json();
      if (!resultado.ok) throw new Error(resultado.message || "No se pudo guardar la devolución.");

      formulario.dataset.saved = "true";
      boton.textContent = "✓ Guardado";
      boton.classList.remove("btn-outline-primary");
      boton.classList.add("btn-success");
      if (feedback) {
        feedback.textContent = `Guardado · ${resultado.found} encontradas · ${resultado.surplus} nuevas · ${resultado.missing} faltantes`;
        feedback.classList.remove("is-error");
      }
      if (campoObservacion) campoObservacion.classList.remove("is-invalid");
      recalcularResumenDevolucion();
      aplicarFiltrosDevolucion();
    } catch (error) {
      formulario.dataset.saved = "false";
      boton.textContent = textoAnterior;
      if (feedback) {
        feedback.textContent = error.message;
        feedback.classList.add("is-error");
      } else {
        window.alert(error.message);
      }
      recalcularResumenDevolucion();
    } finally {
      boton.disabled = false;
    }
  });

  recalcularResumenDevolucion();
  aplicarFiltrosDevolucion();
})();
