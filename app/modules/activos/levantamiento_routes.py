import re
from datetime import datetime, timezone
from io import BytesIO
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from openpyxl import load_workbook
import pdfplumber
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates
from app.modules.auth.dependencies import get_current_user, user_area, require_roles, LOGISTICA_ROLES, SUPER_ADMIN_ROLES
from app.modules.auth.models import Usuario
from app.modules.categorias.service import CategoriaService
from app.modules.personas.service import PersonaService
from app.modules.ubicaciones.service import UbicacionService
from .levantamiento_service import (
    LevantamientoService,
    cantidad_entregada_detalle,
    cantidad_devuelta_detalle,
    cantidad_sobrante_detalle,
    calcular_diferencias_cantidad,
)
from .model import Activo
from .levantamiento_model import LevantamientoDetalle
from app.modules.categorias.model import Categoria

router = APIRouter(prefix="/activos/inventario-fisico", tags=["Inventario físico"], dependencies=[Depends(get_current_user)])
public_router = APIRouter(prefix="/inventario-fisico-publico", tags=["Inventario físico público"])


def _nombre_usuario(user: Usuario) -> str:
    return " ".join(x for x in [getattr(user, "nombre", ""), getattr(user, "apellido", "")] if x).strip() or user.usuario


def _normalizar(valor):
    if valor is None:
        return ""
    texto = str(valor).strip().lower()
    reemplazos = str.maketrans("áéíóúüñ", "aeiouun")
    texto = texto.translate(reemplazos)
    return re.sub(r"[^a-z0-9]+", "", texto)


def _buscar_encabezados(ws):
    aliases = {
        "nombre": {"elemento", "nombre", "articulo", "item"},
        "referencia": {"referencia", "codigo", "codigobarras", "serial"},
        "cantidad": {"cant", "cantidad", "cantidadsistema"},
        "observacion": {"observacion", "observaciones", "detalle"},
        "estado": {"estado", "estadodelactivo"},
        "categoria": {"categoria"},
        "marca": {"marca"},
        "modelo": {"modelo"},
    }
    for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 30)):
        found = {}
        for cell in row:
            key = _normalizar(cell.value)
            if not key:
                continue
            for campo, opciones in aliases.items():
                if key in {_normalizar(x) for x in opciones}:
                    found[campo] = cell.column
        if "nombre" in found:
            return row[0].row, found
    return None, {}


def _valor_fila(ws, row, col):
    if not col:
        return ""
    return str(ws.cell(row=row, column=col).value or "").strip()


def _parsear_cantidad(valor):
    """Convierte valores como 4, "16 CAJAS", "7 JUEGOS" o "3 UND"."""
    texto = str(valor or "").strip().replace("\ufeff", "")
    match = re.search(r"(\d+(?:[.,]\d+)?)", texto)
    if not match:
        return 0
    try:
        return max(0, int(float(match.group(1).replace(",", "."))))
    except ValueError:
        return 0


def _categoria_prefijo(nombre, db):
    base = re.sub(r"[^A-Za-z0-9]", "", nombre.upper())
    base = (base[:6] or "GEN")
    prefijo = base[:10]
    existente = db.query(Categoria).filter(Categoria.prefijo.ilike(prefijo)).first()
    if not existente:
        return prefijo
    for i in range(2, 1000):
        candidato = (base[:8] + str(i))[:10]
        if not db.query(Categoria).filter(Categoria.prefijo.ilike(candidato)).first():
            return candidato
    raise ValueError(f"No fue posible generar un prefijo para la categoría '{nombre}'.")


def _obtener_o_crear_categoria(nombre, db):
    nombre = re.sub(r"\s+", " ", str(nombre or "").strip()).strip(" .:-")
    if not nombre:
        return None
    categoria = db.query(Categoria).filter(Categoria.nombre.ilike(nombre)).first()
    if categoria:
        return categoria
    categoria = Categoria(
        nombre=nombre[:120],
        prefijo=_categoria_prefijo(nombre, db),
        descripcion="Creada automáticamente durante la importación de inventario físico.",
    )
    db.add(categoria)
    db.flush()
    return categoria


def _reconstruir_categoria_vertical(page, cell):
    """Lee categorías impresas verticalmente dentro de la columna ITEM."""
    crop = page.crop(cell)
    palabras = crop.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not palabras:
        return ""
    # El PDF de inventario usa texto rotado: al extraerlo queda fragmentado
    # de arriba hacia abajo. Invertir el orden reconstruye MOBILIARIO y
    # CAJAS EQUIPOS ROBOTICA correctamente.
    piezas = [p["text"].strip() for p in sorted(palabras, key=lambda x: x["top"]) if p["text"].strip()]
    texto = "".join(piezas)[::-1]
    texto = re.sub(r"[^A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ ]+", " ", texto)
    # Los fragmentos de texto rotado pueden venir pegados. Aplicamos los
    # nombres conocidos del formato y, si no, dejamos el texto reconstruido.
    compact = _normalizar(texto)
    conocidos = {
        "mobiliario": "MOBILIARIO",
        "cajasequiposrobotica": "CAJAS EQUIPOS ROBOTICA",
    }
    if compact in conocidos:
        return conocidos[compact]
    # Intento adicional para separar palabras comunes.
    if "CAJASEQUIPOSROBOTICA" in compact:
        return "CAJAS EQUIPOS ROBOTICA"
    if "MOBILIARIO" in compact:
        return "MOBILIARIO"
    return texto.strip()


def _filas_pdf(contenido):
    """Extrae el inventario de todas las páginas del PDF.

    Conserva la estructura de columnas de la primera tabla que tenga encabezados,
    para poder leer páginas de continuación que no repiten ELEMENTO/CANTIDAD.
    Si detecta páginas con tabla/elementos que no pudo leer, falla explícitamente
    y evita crear un levantamiento incompleto.
    """
    filas = []
    columnas_heredadas = None
    categoria_heredada = ""
    paginas_sin_tabla_detectable = []
    paginas_sin_encabezado = []
    paginas_escaneadas = []

    def detectar_encabezado(matriz):
        for idx, row in enumerate(matriz[:15]):
            encontrados = {}
            for col_idx, valor in enumerate(row or []):
                clave = _normalizar(valor)
                if clave in {"elemento", "nombre", "articulo", "item", "descripcionarticulo"}:
                    encontrados["nombre"] = col_idx
                elif clave in {"cant", "cantidad", "cantidadsistema", "unidades"}:
                    encontrados["cantidad"] = col_idx
                elif clave in {"referencia", "codigo", "codigobarras", "codigoactivo"}:
                    encontrados["referencia"] = col_idx
                elif clave == "serial":
                    encontrados["serial"] = col_idx
                elif clave == "marca":
                    encontrados["marca"] = col_idx
                elif clave == "modelo":
                    encontrados["modelo"] = col_idx
                elif clave in {"observacion", "observaciones", "detalle"}:
                    encontrados["observacion"] = col_idx
                elif clave in {"categoria", "clase", "tipodeelemento"}:
                    encontrados["categoria"] = col_idx
                elif clave in {"estado", "estadodelactivo"}:
                    encontrados["estado"] = col_idx
            if "nombre" in encontrados and "cantidad" in encontrados:
                return idx, encontrados
        return None, None

    def obtener_tablas(page):
        """Usa primero la detección normal y después una estrategia por texto."""
        try:
            tablas = page.find_tables() or []
        except Exception:
            tablas = []
        if tablas:
            return tablas

        estrategias = (
            {
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
                "min_words_vertical": 2,
                "min_words_horizontal": 1,
                "text_tolerance": 3,
                "intersection_tolerance": 5,
            },
            {
                "vertical_strategy": "lines",
                "horizontal_strategy": "text",
                "min_words_horizontal": 1,
                "text_tolerance": 3,
                "intersection_tolerance": 5,
            },
        )
        for configuracion in estrategias:
            try:
                tablas = page.find_tables(table_settings=configuracion) or []
            except Exception:
                tablas = []
            if tablas:
                return tablas
        return []

    with pdfplumber.open(BytesIO(contenido)) as pdf:
        for numero_pagina, page in enumerate(pdf.pages, start=1):
            tablas = obtener_tablas(page)
            if not tablas:
                texto_pagina = (page.extract_text() or "").strip()
                if not texto_pagina and getattr(page, "images", []):
                    paginas_escaneadas.append(numero_pagina)
                elif texto_pagina:
                    texto_norm = _normalizar(texto_pagina)
                    parece_tabla = (
                        any(x in texto_norm for x in ("elemento", "articulo", "item"))
                        and any(x in texto_norm for x in ("cant", "cantidad", "unidades"))
                    )
                    if parece_tabla:
                        paginas_sin_tabla_detectable.append(numero_pagina)
                continue

            filas_pagina = 0
            for tabla in tablas:
                try:
                    matriz = tabla.extract() or []
                except Exception:
                    matriz = []
                if not matriz:
                    continue

                encabezado_idx, columnas_detectadas = detectar_encabezado(matriz)
                if columnas_detectadas:
                    columnas_heredadas = columnas_detectadas
                    columnas = columnas_detectadas
                    primera_fila = encabezado_idx + 1
                elif columnas_heredadas:
                    # Las páginas de continuación suelen omitir los encabezados.
                    columnas = columnas_heredadas
                    primera_fila = 0
                else:
                    paginas_sin_encabezado.append(numero_pagina)
                    continue

                rangos_categoria = []
                try:
                    for cell in (getattr(tabla, "cells", None) or []):
                        if not cell:
                            continue
                        x0, top, x1, bottom = cell
                        if x0 <= tabla.bbox[0] + 1 and (bottom - top) >= 25 and top > tabla.bbox[1] + 40:
                            nombre_cat = _reconstruir_categoria_vertical(page, cell)
                            if nombre_cat and len(_normalizar(nombre_cat)) >= 4:
                                rangos_categoria.append((top, bottom, nombre_cat))
                except (AttributeError, IndexError, TypeError, ValueError):
                    rangos_categoria = []

                for row_idx in range(primera_fila, len(matriz)):
                    row = matriz[row_idx] or []
                    nombre_idx = columnas["nombre"]
                    cantidad_idx = columnas["cantidad"]
                    nombre = str(row[nombre_idx] or "").strip() if nombre_idx < len(row) else ""
                    if not nombre:
                        continue
                    nombre_norm = _normalizar(nombre)
                    if nombre_norm in {
                        "elemento", "nombre", "articulo", "item", "observaciones",
                        "observacion", "total", "subtotal", "b", "r", "m",
                    }:
                        continue

                    cantidad_txt = row[cantidad_idx] if cantidad_idx < len(row) else ""
                    cantidad = _parsear_cantidad(cantidad_txt)
                    if cantidad <= 0:
                        continue

                    def valor_columna(campo):
                        col = columnas.get(campo)
                        return str(row[col] or "").strip() if col is not None and col < len(row) else ""

                    estado = valor_columna("estado") or "Bueno"
                    if not columnas.get("estado"):
                        # Formato habitual del colegio: X en B/R/M después de CANT.
                        try:
                            celdas = tabla.rows[row_idx].cells
                            if len(celdas) >= 8:
                                for estado_idx, estado_nombre in ((5, "Bueno"), (6, "Regular"), (7, "Malo")):
                                    celda = celdas[estado_idx]
                                    if celda:
                                        x0, top, x1, bottom = celda
                                        marcas = [
                                            w for w in page.extract_words(use_text_flow=False, keep_blank_chars=False)
                                            if x0 <= w["x0"] < x1 and top <= w["top"] < bottom
                                            and w["text"].strip().upper() == "X"
                                        ]
                                        if marcas:
                                            estado = estado_nombre
                                            break
                        except (AttributeError, IndexError, TypeError, ValueError):
                            pass

                    categoria = valor_columna("categoria")
                    if not categoria:
                        try:
                            celdas = tabla.rows[row_idx].cells
                            celda_elemento = celdas[nombre_idx] if nombre_idx < len(celdas) else None
                            if celda_elemento:
                                y = (celda_elemento[1] + celda_elemento[3]) / 2
                                categoria = next(
                                    (cat for top, bottom, cat in rangos_categoria if top - 1 <= y <= bottom + 1),
                                    "",
                                )
                        except (AttributeError, IndexError, TypeError, ValueError):
                            pass
                    if categoria:
                        categoria_heredada = categoria
                    elif categoria_heredada:
                        categoria = categoria_heredada

                    filas.append({
                        "nombre": re.sub(r"\s+", " ", nombre).strip(),
                        "referencia": valor_columna("referencia"),
                        "serial": valor_columna("serial"),
                        "cantidad": cantidad,
                        "categoria": categoria,
                        "estado": estado,
                        "observacion": valor_columna("observacion"),
                        "marca": valor_columna("marca"),
                        "modelo": valor_columna("modelo"),
                        "pagina_pdf": numero_pagina,
                    })
                    filas_pagina += 1

            if filas_pagina == 0 and tablas and not columnas_heredadas:
                paginas_sin_encabezado.append(numero_pagina)

    paginas_problematicas = sorted(set(
        paginas_sin_tabla_detectable + paginas_sin_encabezado + paginas_escaneadas
    ))
    if paginas_problematicas:
        detalle = ", ".join(str(n) for n in paginas_problematicas)
        causas = []
        if paginas_escaneadas:
            causas.append("contienen páginas escaneadas sin texto seleccionable")
        if paginas_sin_tabla_detectable:
            causas.append("tienen encabezados de inventario pero no se pudo detectar su tabla")
        if paginas_sin_encabezado:
            causas.append("no repiten encabezados y no fue posible heredar las columnas")
        causa = "; ".join(causas) or "no se pudieron interpretar completamente"
        raise ValueError(
            f"No se importó el PDF para evitar una carga incompleta. Revisa las páginas {detalle}: {causa}. "
            "Si son páginas escaneadas, se requiere un PDF con texto seleccionable u OCR."
        )

    if not filas:
        raise ValueError("No se encontraron artículos con nombre y cantidad en ninguna página del PDF.")
    return filas

def _agrupar_detalles_vista(detalles):
    """Agrupa solo para presentar; conserva cada detalle/activo en la base de datos."""
    grupos = {}
    individuales = []
    for d in detalles:
        # Serial real significa identidad individual: nunca se agrupa.
        if d.serial:
            key = ("individual", d.id)
        else:
            key = (
                _normalizar(d.nombre), d.categoria_id or 0,
                _normalizar(d.marca), _normalizar(d.modelo),
                bool(d.es_nuevo), bool(getattr(d, "alta_logistica", False)),
                (d.estado_fisico or "").strip().casefold(),
                (d.observacion or "").strip().casefold(),
            )
        grupos.setdefault(key, []).append(d)

    resultado = []
    for detalles_grupo in grupos.values():
        primero = detalles_grupo[0]
        referencias = sorted(
            {str(d.referencia).strip() for d in detalles_grupo if d.referencia},
            key=lambda x: (re.sub(r"\d+", lambda m: m.group().zfill(12), x), x.casefold()),
        )
        if len(referencias) > 1:
            rango = f"Desde {referencias[0]} hasta {referencias[-1]}"
        elif referencias:
            rango = referencias[0]
        else:
            rango = "—"
        resultado.append({
            "detalles": detalles_grupo,
            "ids": ",".join(str(d.id) for d in detalles_grupo),
            "nombre": primero.nombre,
            "categoria": primero.categoria,
            "cantidad_sistema": sum(int(d.cantidad_sistema or 0) for d in detalles_grupo),
            "cantidad_encontrada": sum(int(d.cantidad_encontrada or 0) for d in detalles_grupo),
            "referencia_rango": rango,
            "estado_fisico": primero.estado_fisico,
            "observacion": primero.observacion,
            "es_nuevo": primero.es_nuevo,
            "alta_logistica": bool(getattr(primero, "alta_logistica", False)),
            "descripcion": getattr(primero, "descripcion", None),
            "cantidad": len(detalles_grupo),
            "cantidad_entregada": sum(cantidad_entregada_detalle(d) for d in detalles_grupo),
            "cantidad_devuelta": sum(cantidad_devuelta_detalle(d) for d in detalles_grupo),
            "cantidad_sobrante": sum(cantidad_sobrante_detalle(d) for d in detalles_grupo),
            "cantidad_encontrada_devolucion": sum(cantidad_devuelta_detalle(d) + cantidad_sobrante_detalle(d) for d in detalles_grupo),
            "cantidad_faltante": max(0, sum(cantidad_entregada_detalle(d) for d in detalles_grupo) - sum(cantidad_devuelta_detalle(d) for d in detalles_grupo)),
            "observacion_devolucion": next((d.observacion_devolucion for d in detalles_grupo if d.observacion_devolucion), None),
            "devolucion_revisada_por": next((d.devolucion_revisada_por for d in detalles_grupo if d.devolucion_revisada_por), None),
            "devolucion_revisada_at": next((d.devolucion_revisada_at for d in detalles_grupo if d.devolucion_revisada_at), None),
            "todos_verificados": all(d.verificado_logistica for d in detalles_grupo),
            "todos_revisados_devolucion": all(getattr(d, "revisado_devolucion", False) for d in detalles_grupo),
            "alguno_verificado": any(d.verificado_logistica for d in detalles_grupo),
            "activo": primero.activo,
        })
    return sorted(resultado, key=lambda g: (str(g["nombre"] or "").casefold(), g["referencia_rango"]))


def _agrupar_detalles_devolucion(detalles):
    """Las altas hechas por Logística no forman parte de los artículos prestados al docente."""
    return [g for g in _agrupar_detalles_vista(detalles) if not g.get("alta_logistica")]


def _es_logistica(user: Usuario) -> bool:
    return bool(user.rol and user.rol.nombre in (LOGISTICA_ROLES | SUPER_ADMIN_ROLES))


@public_router.get("/{token}", response_class=HTMLResponse)
def docente(token: str, request: Request, db: Session = Depends(get_db)):
    service = LevantamientoService(db)
    lev = service.obtener_por_token(token)
    if not lev:
        raise HTTPException(status_code=404, detail="Enlace de inventario no encontrado.")
    # Fijamos el tenant antes de consultar categorías para mantener aislamiento.
    db.info["empresa_id"] = lev.empresa_id
    categorias = CategoriaService(db).listar(estado="Activas")
    return templates.TemplateResponse(request=request, name="activos/inventario_fisico_publico.html", context={
        "title": "Verificación de inventario", "levantamiento": lev, "categorias": categorias, "token": token
    })


@public_router.post("/{token}/detalle/{detalle_id}")
def docente_actualizar(token: str, detalle_id: int, cantidad_encontrada: int = Form(...), estado_fisico: str = Form(...), observacion: str = Form(""), db: Session = Depends(get_db)):
    lev = LevantamientoService(db).obtener_por_token(token)
    if not lev:
        raise HTTPException(status_code=404, detail="Enlace de inventario no encontrado.")
    db.info["empresa_id"] = lev.empresa_id
    try:
        LevantamientoService(db).actualizar_detalle_publico(token, detalle_id, cantidad_encontrada, estado_fisico, observacion)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/inventario-fisico-publico/{token}", status_code=303)


@public_router.post("/{token}/hallazgo")
def docente_hallazgo(token: str, nombre: str = Form(...), categoria_id: int = Form(...), cantidad: int = Form(1), estado_fisico: str = Form("Bueno"), referencia: str = Form(""), marca: str = Form(""), modelo: str = Form(""), serial: str = Form(""), observacion: str = Form(""), db: Session = Depends(get_db)):
    lev = LevantamientoService(db).obtener_por_token(token)
    if not lev:
        raise HTTPException(status_code=404, detail="Enlace de inventario no encontrado.")
    db.info["empresa_id"] = lev.empresa_id
    try:
        LevantamientoService(db).agregar_hallazgo_publico(token, nombre, categoria_id, cantidad, estado_fisico, observacion, referencia, marca, modelo, serial)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/inventario-fisico-publico/{token}", status_code=303)


@public_router.post("/{token}/enviar")
def docente_enviar(token: str, firma: str = Form(""), db: Session = Depends(get_db)):
    lev = LevantamientoService(db).obtener_por_token(token)
    if not lev:
        raise HTTPException(status_code=404, detail="Enlace de inventario no encontrado.")
    db.info["empresa_id"] = lev.empresa_id
    try:
        LevantamientoService(db).enviar(lev.id, firma=firma)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/inventario-fisico-publico/{token}", status_code=303)


@router.get("/", response_class=HTMLResponse)
def index(request: Request, levantamiento_id: int | None = None, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    # El control físico debe permitir revisar cualquier ubicación de la empresa,
    # independientemente del área del usuario que está diligenciando.
    area = user_area(user)
    es_super_admin = bool(user.rol and user.rol.nombre in SUPER_ADMIN_ROLES)
    es_logistica = _es_logistica(user)
    service = LevantamientoService(db)
    # Solo Super Admin ve ambas áreas. Logística y Medios ven su propio inventario.
    area_consulta = "Todas" if es_super_admin else area
    levantamientos = service.listar(area_consulta)
    levantamiento = service.obtener(levantamiento_id, area_consulta) if levantamiento_id else None
    if levantamiento and not es_super_admin and levantamiento.area != area:
        levantamiento = None
    ubicaciones = UbicacionService(db).listar("Todas")
    personas = PersonaService(db).listar()
    categorias = CategoriaService(db).listar(estado="Activas")
    return templates.TemplateResponse(
        request=request,
        name="activos/inventario_fisico.html",
        context={
            "title": "Inventario físico",
            "levantamientos": levantamientos,
            "levantamiento": levantamiento,
            "grupos_detalles": _agrupar_detalles_vista(levantamiento.detalles) if levantamiento else [],
            "grupos_devolucion": _agrupar_detalles_devolucion(levantamiento.detalles) if levantamiento else [],
            "ubicaciones": ubicaciones,
            "personas": personas,
            "categorias": categorias,
            "area": area,
            "usuario_actual": _nombre_usuario(user),
            "current_user_id": user.id,
            "es_logistica": es_logistica,
            "es_super_admin": es_super_admin,
        },
    )


@router.post("/crear")
def crear(ubicacion_id: int = Form(...), responsable_id: int | None = Form(None), db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    try:
        lev = LevantamientoService(db).crear_borrador(ubicacion_id, responsable_id, user_area(user), user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/activos/inventario-fisico/?levantamiento_id={lev.id}", status_code=303)


@router.post("/detalle")
def agregar_detalle(
    levantamiento_id: int = Form(...),
    nombre: str = Form(...),
    categoria_id: int = Form(...),
    cantidad: int = Form(1),
    estado_fisico: str = Form("Bueno"),
    referencia: str = Form(""),
    marca: str = Form(""),
    modelo: str = Form(""),
    serial: str = Form(""),
    observacion: str = Form(""),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    try:
        LevantamientoService(db).agregar_hallazgo(levantamiento_id, nombre, categoria_id, cantidad, estado_fisico, observacion, referencia, marca, modelo, serial)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/activos/inventario-fisico/?levantamiento_id={levantamiento_id}", status_code=303)


@router.post("/detalle/{detalle_id}")
def editar_detalle(detalle_id: int, cantidad_encontrada: int = Form(...), estado_fisico: str = Form(...), observacion: str = Form(""), levantamiento_id: int = Form(...), db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    try:
        LevantamientoService(db).actualizar_detalle(detalle_id, cantidad_encontrada, estado_fisico, observacion)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/activos/inventario-fisico/?levantamiento_id={levantamiento_id}", status_code=303)


@router.post("/{levantamiento_id}/alta-nueva")
def agregar_alta_nueva_logistica(
    levantamiento_id: int,
    nombre: str = Form(...),
    categoria_id: int = Form(...),
    cantidad: int = Form(1),
    marca: str = Form(""),
    modelo: str = Form(""),
    serial: str = Form(""),
    referencia: str = Form(""),
    descripcion: str = Form(""),
    estado_fisico: str = Form("Bueno"),
    observacion: str = Form(""),
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_roles("Super Admin", "Superadministrador", "Administrador de Logística", "Admin de Logística")),
):
    area = user_area(user)
    service = LevantamientoService(db)
    lev = service.obtener(levantamiento_id, area)
    if not lev or lev.estado not in {"Pendiente de aprobación", "Aprobado", "Devuelto parcialmente"}:
        raise HTTPException(status_code=404, detail="No se encontró un levantamiento abierto para agregar activos en tu área.")
    try:
        service.agregar_alta_logistica(
            levantamiento_id=levantamiento_id,
            usuario_nombre=_nombre_usuario(user),
            nombre=nombre,
            categoria_id=categoria_id,
            cantidad=cantidad,
            marca=marca,
            modelo=modelo,
            serial=serial,
            referencia=referencia,
            descripcion=descripcion,
            estado_fisico=estado_fisico,
            observacion=observacion,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(
        url=f"/activos/inventario-fisico/?levantamiento_id={levantamiento_id}&nuevo_activo=1&activo_agregado=1#return-review-section",
        status_code=303,
    )


@router.post("/importar-excel")
async def importar_excel(
    ubicacion_id: int = Form(...),
    responsable_id: int | None = Form(None),
    categoria_por_defecto: int | None = Form(None),
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    extension = (archivo.filename or "").lower().rsplit(".", 1)[-1]
    if extension not in {"xlsx", "xlsm", "pdf"}:
        raise HTTPException(status_code=400, detail="Sube un archivo Excel (.xlsx/.xlsm) o PDF (.pdf).")

    try:
        contenido = await archivo.read()
        if not contenido:
            raise ValueError("El archivo está vacío.")

        filas = []
        if extension in {"xlsx", "xlsm"}:
            wb = load_workbook(BytesIO(contenido), data_only=True)
            ws = wb.active
            header_row, cols = _buscar_encabezados(ws)
            if not header_row:
                raise ValueError("No encontré una fila de encabezados. Usa columnas como ELEMENTO, REFERENCIA, CANT., ESTADO y OBSERVACIÓN.")
            for row in range(header_row + 1, ws.max_row + 1):
                nombre = _valor_fila(ws, row, cols.get("nombre"))
                if not nombre:
                    continue
                filas.append({
                    "nombre": nombre,
                    "referencia": _valor_fila(ws, row, cols.get("referencia")),
                    "cantidad": _parsear_cantidad(_valor_fila(ws, row, cols.get("cantidad")) or "1"),
                    "categoria": _valor_fila(ws, row, cols.get("categoria")),
                    "estado": _valor_fila(ws, row, cols.get("estado")) or "Bueno",
                    "observacion": _valor_fila(ws, row, cols.get("observacion")),
                    "marca": _valor_fila(ws, row, cols.get("marca")),
                    "modelo": _valor_fila(ws, row, cols.get("modelo")),
                    "serial": _valor_fila(ws, row, cols.get("serial")),
                })
        else:
            filas = _filas_pdf(contenido)

        if not filas:
            raise ValueError("El archivo no produjo filas válidas. En el PDF se esperan elementos con cantidad; en Excel, una columna ELEMENTO y CANT.")

        area = user_area(user)
        service = LevantamientoService(db)
        lev = service.crear_borrador(ubicacion_id, responsable_id, area, user.id)
        creados = 0
        categoria_defecto = db.query(Categoria).filter(Categoria.id == categoria_por_defecto).first() if categoria_por_defecto else None

        # El borrador ya contiene un detalle por cada activo activo de la ubicación.
        # Indexamos esos detalles para comparar el Excel contra el inventario real,
        # no para convertir cada fila del archivo en un hallazgo nuevo.
        from collections import defaultdict
        detalles_existentes = [d for d in lev.detalles if d.activo_id and not d.es_nuevo]
        por_clave = defaultdict(list)
        por_identificador = {}
        for detalle in detalles_existentes:
            activo = detalle.activo
            clave = (
                _normalizar(detalle.nombre), detalle.categoria_id or 0,
                _normalizar(detalle.marca), _normalizar(detalle.modelo),
            )
            por_clave[clave].append(detalle)
            for identificador in (getattr(activo, "codigo", None), getattr(activo, "codigo_barras", None), getattr(activo, "serial", None)):
                if identificador:
                    por_identificador[_normalizar(identificador)] = detalle
        usados = set()

        # Consolidar renglones repetidos del archivo por características compatibles.
        grupos = {}
        for fila in filas:
            nombre = str(fila.get("nombre") or "").strip()
            if not nombre:
                continue
            referencia = str(fila.get("referencia") or "").strip()
            serial = str(fila.get("serial") or "").strip()
            marca = str(fila.get("marca") or "").strip()
            modelo = str(fila.get("modelo") or "").strip()
            obs = str(fila.get("observacion") or "").strip()
            estado = str(fila.get("estado") or "Bueno").strip() or "Bueno"
            cantidad = int(fila.get("cantidad") or 0)
            if cantidad < 1:
                continue

            categoria_texto = str(fila.get("categoria") or "").strip()
            if categoria_texto:
                categoria = _obtener_o_crear_categoria(categoria_texto, db)
                categoria_id = categoria.id if categoria else None
            elif categoria_defecto:
                categoria_id = categoria_defecto.id
            else:
                # Si el archivo no especifica categoría, primero comparar por nombre,
                # marca y modelo sin forzar una categoría GENERAL que impediría coincidir.
                categoria_id = None

            # Un serial real o código de activo identifica una unidad; una referencia
            # descriptiva/modelo común se compara por características del artículo.
            identificador = serial or referencia
            detalle_id = por_identificador.get(_normalizar(identificador)) if identificador else None
            detalle_identificado = next((d for d in detalles_existentes if d.id == detalle_id), None)
            if detalle_identificado:
                if detalle_identificado.id not in usados:
                    detalle_identificado.cantidad_encontrada = 1
                    detalle_identificado.estado_fisico = estado
                    if obs:
                        detalle_identificado.observacion = obs
                    usados.add(detalle_identificado.id)
                continue

            clave = (_normalizar(nombre), categoria_id or 0, _normalizar(marca), _normalizar(modelo))
            grupo_key = (clave, _normalizar(serial), _normalizar(referencia), _normalizar(estado), _normalizar(obs))
            if grupo_key not in grupos:
                grupos[grupo_key] = {
                    "nombre": nombre, "categoria_id": categoria_id, "referencia": referencia,
                    "serial": serial, "marca": marca, "modelo": modelo, "estado": estado,
                    "observacion": obs, "cantidad": 0, "clave": clave,
                }
            grupos[grupo_key]["cantidad"] += cantidad

        for grupo in grupos.values():
            cantidad_archivo = grupo["cantidad"]
            if grupo["clave"][1] == 0:
                candidatos = [d for d in detalles_existentes
                              if d.id not in usados
                              and _normalizar(d.nombre) == grupo["clave"][0]
                              and _normalizar(d.marca) == grupo["clave"][2]
                              and _normalizar(d.modelo) == grupo["clave"][3]]
            else:
                candidatos = [d for d in por_clave.get(grupo["clave"], []) if d.id not in usados]
            # Las unidades existentes se cuentan primero. Solo el excedente del Excel
            # se registra como hallazgo nuevo; nunca se duplica la cantidad ya registrada.
            existentes_a_contar = min(cantidad_archivo, len(candidatos))
            for detalle in candidatos[:existentes_a_contar]:
                detalle.cantidad_encontrada = 1
                detalle.estado_fisico = grupo["estado"]
                if grupo["observacion"]:
                    detalle.observacion = grupo["observacion"]
                usados.add(detalle.id)
            diferencia = max(0, cantidad_archivo - existentes_a_contar)
            if diferencia:
                categoria_nueva_id = grupo["categoria_id"]
                if not categoria_nueva_id:
                    categoria_general = _obtener_o_crear_categoria("GENERAL", db)
                    categoria_nueva_id = categoria_general.id if categoria_general else None
                service.agregar_hallazgo(
                    lev.id, grupo["nombre"], categoria_nueva_id, diferencia,
                    grupo["estado"], grupo["observacion"], grupo["referencia"],
                    grupo["marca"], grupo["modelo"], grupo["serial"],
                )
                creados += 1

        # Los activos de la ubicación que no aparecieron en el archivo quedan con
        # cantidad encontrada 0 para que Logística pueda revisar el faltante.
        for detalle in detalles_existentes:
            if detalle.id not in usados:
                detalle.cantidad_encontrada = 0
        db.commit()
        # Una importación puede coincidir completamente con activos existentes y, por
        # tanto, no generar hallazgos nuevos. Eso NO significa que el archivo sea inválido:
        # el borrador sirve para verificar existentes y registrar faltantes.
        if not usados and not creados:
            # Solo eliminar el borrador recién creado si realmente no se pudo asociar
            # ninguna fila válida a activos existentes ni crear hallazgos.
            db.delete(lev)
            db.commit()
            raise ValueError("No se pudo asociar ninguna fila del archivo con activos existentes ni crear hallazgos. Revisa nombres, referencias y cantidades.")
    except Exception as exc:
        db.rollback()
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=400, detail=str(exc))
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo: {exc}")
    return RedirectResponse(url=f"/activos/inventario-fisico/?levantamiento_id={lev.id}", status_code=303)


@router.get("/{levantamiento_id}/revisar", response_class=HTMLResponse)
def revisar(levantamiento_id: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(require_roles("Super Admin", "Superadministrador", "Administrador de Logística", "Admin de Logística"))):
    area_consulta = user_area(user)
    lev = LevantamientoService(db).obtener(levantamiento_id, area_consulta)
    if not lev:
        raise HTTPException(status_code=404, detail="Levantamiento no encontrado en tu área.")
    return templates.TemplateResponse(request=request, name="activos/inventario_fisico.html", context={
        "title": "Revisar inventario físico", "levantamientos": LevantamientoService(db).listar("Todas"),
        "levantamiento": lev, "grupos_detalles": _agrupar_detalles_vista(lev.detalles),
        "grupos_devolucion": _agrupar_detalles_devolucion(lev.detalles), "ubicaciones": UbicacionService(db).listar("Todas"),
        "personas": PersonaService(db).listar(), "categorias": CategoriaService(db).listar(estado="Activas"),
        "area": area_consulta, "usuario_actual": _nombre_usuario(user), "es_logistica": True, "modo_revision": True,
        "es_super_admin": bool(user.rol and user.rol.nombre in SUPER_ADMIN_ROLES), "current_user_id": user.id,
    })


@router.post("/detalle/{detalle_id}/verificar")
def verificar_detalle(detalle_id: int, levantamiento_id: int = Form(...), db: Session = Depends(get_db), user: Usuario = Depends(require_roles("Super Admin", "Superadministrador", "Administrador de Logística", "Admin de Logística"))):
    try:
        LevantamientoService(db).verificar_detalle(detalle_id, _nombre_usuario(user))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/activos/inventario-fisico/{levantamiento_id}/revisar", status_code=303)


@router.post("/detalle/{detalle_id}/desverificar")
def desverificar_detalle(detalle_id: int, levantamiento_id: int = Form(...), db: Session = Depends(get_db), user: Usuario = Depends(require_roles("Super Admin", "Superadministrador", "Administrador de Logística", "Admin de Logística"))):
    try:
        LevantamientoService(db).desverificar_detalle(detalle_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/activos/inventario-fisico/{levantamiento_id}/revisar", status_code=303)


@router.post("/{levantamiento_id}/grupo/verificar")
def verificar_grupo(levantamiento_id: int, request: Request, detalle_ids_csv: str = Form(...), db: Session = Depends(get_db), user: Usuario = Depends(require_roles("Super Admin", "Superadministrador", "Administrador de Logística", "Admin de Logística"))):
    lev = LevantamientoService(db).obtener(levantamiento_id, user_area(user))
    if not lev or lev.estado != "Pendiente de aprobación":
        raise HTTPException(status_code=404, detail="Levantamiento pendiente no encontrado en tu área.")
    try:
        ids = {int(x) for x in detalle_ids_csv.split(",") if x.strip()}
    except ValueError:
        raise HTTPException(status_code=400, detail="La selección de elementos no es válida.")
    if not ids:
        raise HTTPException(status_code=400, detail="No se seleccionaron elementos.")
    detalles = db.query(LevantamientoDetalle).filter(
        LevantamientoDetalle.levantamiento_id == lev.id,
        LevantamientoDetalle.empresa_id == lev.empresa_id,
        LevantamientoDetalle.id.in_(ids),
    ).all()
    if len(detalles) != len(ids):
        raise HTTPException(status_code=400, detail="Uno o más elementos no pertenecen a este levantamiento.")
    marcar = not all(d.verificado_logistica for d in detalles)
    for d in detalles:
        d.verificado_logistica = marcar
        d.revisado_por = _nombre_usuario(user) if marcar else None
        d.revisado_at = datetime.now(timezone.utc) if marcar else None
    db.commit()

    # Los navegadores pueden omitir X-Requested-With en algunos escenarios.
    # El encabezado Accept: application/json también identifica la petición AJAX.
    requested_with = (request.headers.get("x-requested-with") or "").strip().lower()
    accept = (request.headers.get("accept") or "").lower()
    wants_json = requested_with == "xmlhttprequest" or "application/json" in accept
    if wants_json:
        return JSONResponse({
            "ok": True,
            "verified": marcar,
            "count": len(detalles),
            "message": "Grupo marcado como verificado." if marcar else "Verificación del grupo retirada.",
        })
    return RedirectResponse(url=f"/activos/inventario-fisico/{levantamiento_id}/revisar", status_code=303)


@router.post("/{levantamiento_id}/grupo/revisar-devolucion")
def revisar_grupo_devolucion(
    levantamiento_id: int,
    request: Request,
    detalle_ids_csv: str = Form(...),
    cantidad_devuelta: int = Form(...),
    observacion_devolucion: str = Form(""),
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_roles("Super Admin", "Superadministrador", "Administrador de Logística", "Admin de Logística")),
):
    area = user_area(user)
    lev = LevantamientoService(db).obtener(levantamiento_id, area)
    if not lev or lev.estado not in {"Aprobado", "Devuelto parcialmente"}:
        raise HTTPException(status_code=404, detail="No se encontró un levantamiento aprobado en tu área.")
    try:
        ids = {int(x) for x in detalle_ids_csv.split(",") if x.strip()}
    except ValueError:
        raise HTTPException(status_code=400, detail="La selección de elementos no es válida.")
    if not ids:
        raise HTTPException(status_code=400, detail="No se seleccionaron elementos del grupo.")
    detalles = db.query(LevantamientoDetalle).filter(
        LevantamientoDetalle.levantamiento_id == lev.id,
        LevantamientoDetalle.empresa_id == lev.empresa_id,
        LevantamientoDetalle.id.in_(ids),
    ).all()
    if len(detalles) != len(ids):
        raise HTTPException(status_code=400, detail="Uno o más elementos no pertenecen a este levantamiento.")

    cantidad_entregada = sum(cantidad_entregada_detalle(d) for d in detalles)
    if cantidad_devuelta < 0 or cantidad_devuelta > 5000:
        raise HTTPException(
            status_code=400,
            detail="La cantidad encontrada debe estar entre 0 y 5.000 unidades.",
        )
    recibidas_originales, nuevas_unidades, faltantes = calcular_diferencias_cantidad(
        cantidad_entregada, cantidad_devuelta
    )
    if lev.estado == "Devuelto parcialmente":
        cantidad_ya_registrada = sum(cantidad_devuelta_detalle(d) for d in detalles)
        nuevas_ya_registradas = sum(cantidad_sobrante_detalle(d) for d in detalles)
        if recibidas_originales < cantidad_ya_registrada:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Ya se registraron {cantidad_ya_registrada} unidades originales devueltas de este grupo. "
                    "No se puede reducir esa cantidad porque esos activos ya regresaron a bodega."
                ),
            )
        if nuevas_unidades < nuevas_ya_registradas:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Ya se incorporaron {nuevas_ya_registradas} unidades nuevas de este grupo. "
                    "No se puede reducir esa cantidad porque ya forman parte del inventario."
                ),
            )
    observacion_limpia = observacion_devolucion.strip()
    if (faltantes > 0 or nuevas_unidades > 0) and not observacion_limpia:
        raise HTTPException(
            status_code=400,
            detail="Escribe una observación para explicar las unidades faltantes o las unidades nuevas encontradas.",
        )
    if len(observacion_limpia) > 2000:
        raise HTTPException(status_code=400, detail="La observación no puede superar 2.000 caracteres.")

    # Distribuir primero las unidades originalmente entregadas entre sus activos.
    # La diferencia positiva se almacena aparte y se incorpora como nuevos activos
    # disponibles en bodega al confirmar la devolución general.
    detalles_ordenados = sorted(detalles, key=lambda d: (str(d.referencia or "").casefold(), d.id))
    restante = recibidas_originales
    for indice, detalle in enumerate(detalles_ordenados):
        capacidad = cantidad_entregada_detalle(detalle)
        asignada = min(capacidad, restante)
        detalle.cantidad_devuelta = asignada
        detalle.cantidad_sobrante = nuevas_unidades if indice == 0 else 0
        detalle.observacion_devolucion = observacion_limpia or None
        detalle.revisado_devolucion = True
        detalle.devolucion_revisada_por = _nombre_usuario(user)
        detalle.devolucion_revisada_at = datetime.now(timezone.utc)
        restante -= asignada

    db.commit()
    observacion = observacion_limpia or ""
    requested_with = (request.headers.get("x-requested-with") or "").strip().lower()
    accept = (request.headers.get("accept") or "").lower()
    wants_json = requested_with == "xmlhttprequest" or "application/json" in accept
    resultado = {
        "ok": True,
        "delivered": cantidad_entregada,
        "returned": recibidas_originales,
        "found": cantidad_devuelta,
        "surplus": nuevas_unidades,
        "missing": faltantes,
        "observation": observacion,
        "reviewed_by": _nombre_usuario(user),
        "message": "Devolución guardada correctamente.",
    }
    if wants_json:
        return JSONResponse(resultado)
    return RedirectResponse(url=f"/activos/inventario-fisico/?levantamiento_id={levantamiento_id}", status_code=303)


@router.post("/{levantamiento_id}/eliminar")
def eliminar(levantamiento_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    """Elimina pruebas/borradores sin tocar activos del inventario maestro."""
    service = LevantamientoService(db)
    lev = service.obtener(levantamiento_id, "Todas")
    if not lev:
        raise HTTPException(status_code=404, detail="Levantamiento no encontrado.")
    if not _es_logistica(user) and lev.creado_por != user.id:
        raise HTTPException(status_code=403, detail="No puedes eliminar el levantamiento de otro usuario.")
    try:
        service.eliminar(levantamiento_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/activos/inventario-fisico/", status_code=303)


@router.post("/{levantamiento_id}/enviar")
def enviar(levantamiento_id: int, firma: str = Form(""), db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    try:
        lev = LevantamientoService(db).obtener(levantamiento_id, user_area(user))
        if not lev:
            raise ValueError("Levantamiento no encontrado.")
        if not _es_logistica(user) and lev.creado_por != user.id:
            raise ValueError("No puedes enviar el levantamiento de otro usuario.")
        LevantamientoService(db).enviar(levantamiento_id, firma=firma)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/activos/inventario-fisico/?levantamiento_id={levantamiento_id}", status_code=303)


@router.post("/{levantamiento_id}/devolver-docente")
def devolver_docente(
    levantamiento_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_roles("Super Admin", "Superadministrador", "Administrador de Logística", "Admin de Logística")),
):
    """Devuelve al docente un levantamiento enviado que sigue pendiente de aprobación."""
    area = user_area(user)
    service = LevantamientoService(db)
    lev = service.obtener(levantamiento_id, area)
    if not lev:
        raise HTTPException(status_code=404, detail="Levantamiento no encontrado en tu área.")
    try:
        service.devolver_a_docente(levantamiento_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(
        url=f"/activos/inventario-fisico/?levantamiento_id={levantamiento_id}",
        status_code=303,
    )


@router.post("/{levantamiento_id}/reabrir-aprobado")
def reabrir_aprobado_para_docente(
    levantamiento_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_roles("Super Admin", "Superadministrador", "Administrador de Logística", "Admin de Logística")),
):
    """Devuelve el mismo enlace al docente sin borrar activos ni movimientos aprobados."""
    area = user_area(user)
    service = LevantamientoService(db)
    lev = service.obtener(levantamiento_id, area)
    if not lev:
        raise HTTPException(status_code=404, detail="Levantamiento no encontrado en tu área.")
    try:
        service.reabrir_aprobado_para_docente(levantamiento_id, _nombre_usuario(user))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(
        url=f"/activos/inventario-fisico/?levantamiento_id={levantamiento_id}",
        status_code=303,
    )


@router.post("/{levantamiento_id}/anular-aprobacion-reimportar")
def cancelar_aprobacion_reimportar(
    levantamiento_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_roles("Super Admin", "Superadministrador", "Administrador de Logística", "Admin de Logística")),
):
    """Anula la entrega de un levantamiento aprobado para permitir cargar un PDF corregido."""
    area = user_area(user)
    service = LevantamientoService(db)
    lev = service.obtener(levantamiento_id, area)
    if not lev:
        raise HTTPException(status_code=404, detail="Levantamiento no encontrado en tu área.")
    try:
        service.cancelar_aprobacion_para_reimportar(levantamiento_id, _nombre_usuario(user))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(
        url="/activos/inventario-fisico/?aprobacion_anulada=1",
        status_code=303,
    )


@router.post("/{levantamiento_id}/aprobar")
def aprobar(levantamiento_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_roles("Super Admin", "Superadministrador", "Administrador de Logística", "Admin de Logística"))):
    area = user_area(user)
    if area == "Todas":
        area = "Todas"
    lev = LevantamientoService(db).obtener(levantamiento_id, area)
    if not lev:
        raise HTTPException(status_code=404, detail="Levantamiento no encontrado.")
    try:
        creados = LevantamientoService(db).aprobar(levantamiento_id, user.id, _nombre_usuario(user))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/activos/inventario-fisico/?levantamiento_id={levantamiento_id}", status_code=303)


@router.post("/{levantamiento_id}/devolver-todo")
def devolver_todo(levantamiento_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_roles("Super Admin", "Superadministrador", "Administrador de Logística", "Admin de Logística"))):
    area = user_area(user)
    lev = LevantamientoService(db).obtener(levantamiento_id, area)
    if not lev:
        raise HTTPException(status_code=404, detail="Levantamiento no encontrado en tu área.")
    try:
        devueltos = LevantamientoService(db).devolver_todo(levantamiento_id, _nombre_usuario(user))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/activos/inventario-fisico/?levantamiento_id={levantamiento_id}", status_code=303)
