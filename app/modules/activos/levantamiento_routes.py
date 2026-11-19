import re
import base64
import unicodedata
from datetime import datetime, timezone
from io import BytesIO
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.drawing.image import Image as XLImage
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
from .levantamiento_model import LevantamientoDetalle, LevantamientoDevolucion
from app.modules.categorias.model import Categoria

router = APIRouter(prefix="/activos/inventario-fisico", tags=["Inventario físico"], dependencies=[Depends(get_current_user)])
public_router = APIRouter(prefix="/inventario-fisico-publico", tags=["Inventario físico público"])


def _nombre_archivo_excel(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or "inventario"))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^A-Za-z0-9_-]+", "_", texto).strip("_")
    return (texto or "inventario")[:60]


def _estilizar_hoja_excel(ws, titulo: str, lev, subtitulo: str):
    ws.sheet_view.showGridLines = False
    ws.merge_cells("A1:L1")
    celda = ws["A1"]
    celda.value = titulo
    celda.font = Font(name="Calibri", size=16, bold=True, color="FFFFFF")
    celda.fill = PatternFill("solid", fgColor="17365D")
    celda.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 28
    ws.merge_cells("A2:L2")
    ws["A2"] = subtitulo
    ws["A2"].font = Font(name="Calibri", size=10, italic=True, color="44546A")
    ws["A3"] = "Ubicación"
    ws["B3"] = lev.ubicacion.nombre if lev.ubicacion else "—"
    ws["D3"] = "Área"
    ws["E3"] = lev.area or "—"
    ws["G3"] = "Responsable"
    ws["H3"] = lev.responsable.nombre if lev.responsable else "—"
    ws["A4"] = "Levantamiento"
    ws["B4"] = f"#{lev.id}"
    ws["D4"] = "Empresa ID"
    ws["E4"] = lev.empresa_id
    ws["G4"] = "Fecha"
    ws["H4"] = (lev.created_at.strftime("%d/%m/%Y %H:%M") if lev.created_at else "—")
    for row in (3, 4):
        for cell in ws[row]:
            if cell.column in (1, 4, 7):
                cell.font = Font(bold=True, color="17365D")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[3].height = 22
    ws.row_dimensions[4].height = 22


def _estilizar_encabezado(ws, fila: int, columnas: list[str]):
    borde = Side(style="thin", color="D9E2F3")
    for idx, nombre in enumerate(columnas, start=1):
        c = ws.cell(fila, idx, nombre)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F4E78")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = Border(bottom=borde)
    ws.row_dimensions[fila].height = 32


def _insertar_firma_excel(ws, firma_data_uri: str | None, fila: int, etiqueta: str, persona: str | None, fecha):
    ws.cell(fila, 1, etiqueta).font = Font(bold=True, color="17365D", size=11)
    ws.cell(fila + 1, 1, persona or "Docente / responsable").font = Font(italic=True, color="44546A")
    if fecha:
        ws.cell(fila + 2, 1, fecha.strftime("%d/%m/%Y %H:%M") if hasattr(fecha, "strftime") else str(fecha))
    if firma_data_uri and ";base64," in firma_data_uri:
        try:
            payload = firma_data_uri.split(",", 1)[1]
            imagen = XLImage(BytesIO(base64.b64decode(payload, validate=True)))
            factor = min(1.0, 340 / max(imagen.width, 1), 100 / max(imagen.height, 1))
            imagen.width = int(imagen.width * factor)
            imagen.height = int(imagen.height * factor)
            ws.add_image(imagen, f"A{fila + 3}")
            ws.row_dimensions[fila + 3].height = 78
        except Exception:
            ws.cell(fila + 3, 1, "Firma digital registrada; no se pudo insertar la imagen en este Excel.")
    else:
        ws.cell(fila + 3, 1, "No hay imagen de firma registrada.")


def _respuesta_excel(wb: Workbook, filename: str):
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


def _agrupar_palabras_en_lineas(palabras, tolerancia_y=3.2):
    """Agrupa palabras del PDF por renglón usando su coordenada vertical."""
    lineas = []
    for palabra in sorted(palabras or [], key=lambda p: (p.get("top", 0), p.get("x0", 0))):
        top = float(palabra.get("top", 0))
        destino = next((linea for linea in reversed(lineas[-3:])
                        if abs(linea["top"] - top) <= tolerancia_y), None)
        if destino is None:
            lineas.append({"top": top, "palabras": [palabra]})
        else:
            destino["palabras"].append(palabra)
            destino["top"] = sum(float(w.get("top", top)) for w in destino["palabras"]) / len(destino["palabras"])
    for linea in lineas:
        linea["palabras"].sort(key=lambda p: p.get("x0", 0))
    return lineas


def _filas_pdf_por_columnas_de_texto(page, layout_anterior=None, categoria_anterior="", numero_pagina=1):
    """Lee renglones por coordenadas aunque la página no tenga bordes de tabla.

    El mapa de columnas se detecta en los encabezados de la primera página y se
    reutiliza en las páginas que continúan la tabla sin repetir encabezados.
    """
    try:
        palabras = page.extract_words(use_text_flow=False, keep_blank_chars=False, x_tolerance=1.5, y_tolerance=3)
    except Exception:
        palabras = []
    lineas = _agrupar_palabras_en_lineas(palabras)
    if not lineas:
        return [], layout_anterior, categoria_anterior

    aliases = {
        "nombre": {"elemento", "nombre", "articulo", "item", "descripcionarticulo"},
        "referencia": {"referencia", "codigo", "codigobarras", "codigoactivo", "ref"},
        "cantidad": {"cant", "cantidad", "cantidadsistema", "unidades", "existencia"},
        "serial": {"serial", "serie"},
        "marca": {"marca"},
        "modelo": {"modelo"},
        "observacion": {"observacion", "observaciones", "detalle"},
        "categoria": {"categoria", "clase", "tipodeelemento"},
        "estado": {"estado", "estadodelactivo"},
        "estado_b": {"b"}, "estado_r": {"r"}, "estado_m": {"m"},
    }
    layout = layout_anterior
    encabezado_bottom = -1.0
    for linea in lineas[:80]:
        encontrados = {}
        for palabra in linea["palabras"]:
            clave = _normalizar(palabra.get("text", ""))
            for campo, opciones in aliases.items():
                if clave in opciones:
                    encontrados[campo] = (float(palabra.get("x0", 0)) + float(palabra.get("x1", 0))) / 2
        if "nombre" in encontrados and "cantidad" in encontrados:
            layout = {campo: centro / max(float(page.width), 1.0) for campo, centro in encontrados.items()}
            encabezado_bottom = max(float(p.get("bottom", p.get("top", 0))) for p in linea["palabras"])
            break

    if not layout or "nombre" not in layout or "cantidad" not in layout:
        return [], layout, categoria_anterior

    columnas = sorted((float(posicion), campo) for campo, posicion in layout.items())
    limites = [(columnas[i][0] + columnas[i + 1][0]) / 2 for i in range(len(columnas) - 1)]

    def campo_de_palabra(palabra):
        centro = ((float(palabra.get("x0", 0)) + float(palabra.get("x1", 0))) / 2) / max(float(page.width), 1.0)
        for indice, limite in enumerate(limites):
            if centro < limite:
                return columnas[indice][1]
        return columnas[-1][1]

    filas_texto = []
    for linea in lineas:
        if linea["top"] <= encabezado_bottom + 1:
            continue
        celdas = {campo: [] for _, campo in columnas}
        for palabra in linea["palabras"]:
            campo = campo_de_palabra(palabra)
            celdas.setdefault(campo, []).append(str(palabra.get("text", "")).strip())
        texto = {campo: re.sub(r"\s+", " ", " ".join(partes)).strip() for campo, partes in celdas.items()}
        nombre = texto.get("nombre", "")
        cantidad = _parsear_cantidad(texto.get("cantidad", ""))
        nombre_norm = _normalizar(nombre)
        if not nombre or cantidad <= 0 or nombre_norm in {
            "elemento", "nombre", "articulo", "item", "observaciones", "observacion",
            "total", "subtotal", "b", "r", "m", "pagina", "pag",
        }:
            continue

        estado = texto.get("estado", "").strip()
        if not estado:
            if any(_normalizar(x) == "x" for x in celdas.get("estado_m", [])):
                estado = "Malo"
            elif any(_normalizar(x) == "x" for x in celdas.get("estado_r", [])):
                estado = "Regular"
            else:
                estado = "Bueno"
        categoria = texto.get("categoria", "").strip()
        if categoria:
            categoria_anterior = categoria
        elif categoria_anterior:
            categoria = categoria_anterior

        filas_texto.append({
            "nombre": re.sub(r"\s+", " ", nombre).strip(),
            "referencia": texto.get("referencia", ""),
            "serial": texto.get("serial", ""),
            "cantidad": cantidad,
            "categoria": categoria,
            "estado": estado,
            "observacion": texto.get("observacion", ""),
            "marca": texto.get("marca", ""),
            "modelo": texto.get("modelo", ""),
            "pagina_pdf": numero_pagina,
        })
    return filas_texto, layout, categoria_anterior


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
    layout_texto_heredado = None

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
            texto_pagina = (page.extract_text() or "").strip()
            if not tablas:
                if not texto_pagina and getattr(page, "images", []):
                    paginas_escaneadas.append(numero_pagina)
                elif texto_pagina:
                    texto_norm = _normalizar(texto_pagina)
                    parece_tabla = (
                        any(x in texto_norm for x in ("elemento", "articulo", "item"))
                        and any(x in texto_norm for x in ("cant", "cantidad", "unidades"))
                    )
                    if parece_tabla and not layout_texto_heredado:
                        paginas_sin_tabla_detectable.append(numero_pagina)

            filas_tabla_pagina = []
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

                    filas_tabla_pagina.append({
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

            filas_texto_pagina, layout_texto_heredado, categoria_texto_heredada = _filas_pdf_por_columnas_de_texto(
                page, layout_texto_heredado, categoria_heredada, numero_pagina
            )
            if categoria_texto_heredada:
                categoria_heredada = categoria_texto_heredada

            # PDFPlumber a veces detecta la tabla pero omite renglones que no
            # coinciden con las líneas/bordes. Comparamos ambas extracciones y
            # usamos la que recupera más filas válidas de esta misma página.
            filas_elegidas = filas_texto_pagina if len(filas_texto_pagina) > len(filas_tabla_pagina) else filas_tabla_pagina
            filas.extend(filas_elegidas)
            if filas_elegidas:
                paginas_sin_tabla_detectable = [p for p in paginas_sin_tabla_detectable if p != numero_pagina]
                paginas_sin_encabezado = [p for p in paginas_sin_encabezado if p != numero_pagina]

            if filas_pagina == 0 and tablas and not columnas_heredadas and not filas_texto_pagina and not filas_tabla_pagina:
                paginas_sin_encabezado.append(numero_pagina)
            if not filas_elegidas and layout_texto_heredado and texto_pagina:
                # Página de continuación con texto, pero sin filas interpretables:
                # no se omite silenciosamente como si estuviera vacía.
                texto_norm = _normalizar(texto_pagina)
                if re.search(r"\b\d+\b", texto_pagina) and any(palabra in texto_norm for palabra in ("aro", "pila", "mesa", "silla", "elemento", "articulo", "inventario", "tec")):
                    paginas_sin_tabla_detectable.append(numero_pagina)

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
            "cantidad_en_bodega": sum(
                int(d.cantidad_encontrada or 0) for d in detalles_grupo
                if getattr(d, "alta_logistica", False)
            ),
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
    """Incluye préstamos y activos ya existentes en bodega.

    Las altas logísticas se muestran como revisadas/disponibles, pero sus cantidades
    no se suman a la devolución porque no fueron entregadas al docente.
    """
    return _agrupar_detalles_vista(detalles)


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
    detalles_publicos = [d for d in lev.detalles if not getattr(d, "alta_logistica", False)]
    return templates.TemplateResponse(request=request, name="activos/inventario_fisico_publico.html", context={
        "title": "Verificación de inventario", "levantamiento": lev, "categorias": categorias,
        "token": token, "grupos_detalles": _agrupar_detalles_vista(detalles_publicos),
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



@public_router.post("/{token}/grupo")
def docente_actualizar_grupo(
    token: str,
    detalle_ids_csv: str = Form(...),
    cantidad_encontrada: int = Form(...),
    estado_fisico: str = Form("Bueno"),
    observacion: str = Form(""),
    db: Session = Depends(get_db),
):
    service = LevantamientoService(db)
    lev = service.obtener_por_token(token)
    if not lev:
        raise HTTPException(status_code=404, detail="Enlace de inventario no encontrado.")
    db.info["empresa_id"] = lev.empresa_id
    try:
        service.actualizar_grupo_publico(
            token, detalle_ids_csv.split(","), cantidad_encontrada, estado_fisico, observacion
        )
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
    if levantamiento and es_logistica and levantamiento.estado in {"Aprobado", "Devuelto parcialmente"}:
        # Mostrar en la devolución cualquier activo agregado manualmente a la misma
        # ubicación y área desde que se creó el levantamiento. Es idempotente.
        service.sincronizar_activos_devolucion(levantamiento, _nombre_usuario(user), commit=True)
        levantamiento = service.obtener(levantamiento_id, area_consulta)
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
            "ultima_devolucion": (levantamiento.devoluciones[-1] if levantamiento and levantamiento.devoluciones else None),
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



@router.post("/{levantamiento_id}/grupo/actualizar")
def actualizar_grupo_borrador(
    levantamiento_id: int,
    detalle_ids_csv: str = Form(...),
    cantidad_encontrada: int = Form(...),
    estado_fisico: str = Form("Bueno"),
    observacion: str = Form(""),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    area = "Todas" if user.rol and user.rol.nombre in SUPER_ADMIN_ROLES else user_area(user)
    try:
        LevantamientoService(db).actualizar_grupo(
            levantamiento_id, detalle_ids_csv.split(","), cantidad_encontrada,
            estado_fisico, observacion, area=area,
        )
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
def devolver_todo(
    levantamiento_id: int,
    firma_docente: str = Form(""),
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_roles("Super Admin", "Superadministrador", "Administrador de Logística", "Admin de Logística")),
):
    area = user_area(user)
    lev = LevantamientoService(db).obtener(levantamiento_id, area)
    if not lev:
        raise HTTPException(status_code=404, detail="Levantamiento no encontrado en tu área.")
    try:
        LevantamientoService(db).devolver_todo(
            levantamiento_id,
            _nombre_usuario(user),
            firma_docente=firma_docente,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/activos/inventario-fisico/?levantamiento_id={levantamiento_id}", status_code=303)


@router.get("/{levantamiento_id}/excel/entrega")
def descargar_excel_entrega(
    levantamiento_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    area = user_area(user)
    lev = LevantamientoService(db).obtener(levantamiento_id, area)
    if not lev:
        raise HTTPException(status_code=404, detail="Levantamiento no encontrado en tu área.")
    if not lev.firma:
        raise HTTPException(status_code=409, detail="Este levantamiento todavía no tiene firma de entrega del docente.")

    wb = Workbook()
    ws = wb.active
    ws.title = "Entrega"
    fecha = lev.enviado_at or lev.aprobado_at or lev.created_at
    _estilizar_hoja_excel(ws, "ACTA DE ENTREGA DE INVENTARIO", lev, "Constancia de los elementos revisados y entregados al responsable.")
    ws["A5"] = "Fecha de firma"
    ws["B5"] = fecha.strftime("%d/%m/%Y %H:%M") if fecha else "—"
    ws["D5"] = "Aprobado por"
    ws["E5"] = (
        " ".join(x for x in [getattr(lev.aprobador, "nombre", ""), getattr(lev.aprobador, "apellido", "")] if x).strip()
        if lev.aprobador else "—"
    )
    columnas = ["Elemento", "Categoría", "Referencia / rango", "Cantidad sistema", "Cantidad entregada", "Marca", "Modelo", "Serial", "Estado físico", "Observación del docente"]
    fila_header = 7
    _estilizar_encabezado(ws, fila_header, columnas)
    detalles = [d for d in lev.detalles if not getattr(d, "alta_logistica", False)]
    grupos = _agrupar_detalles_vista(detalles)
    fila = fila_header + 1
    total = 0
    for g in grupos:
        grupo_detalles = g.get("detalles", [])
        primero = grupo_detalles[0] if grupo_detalles else None
        seriales = ", ".join(sorted({d.serial for d in grupo_detalles if d.serial}))
        valores = [
            g.get("nombre", ""),
            g["categoria"].nombre if g.get("categoria") else "",
            g.get("referencia_rango", "—"),
            g.get("cantidad_sistema", 0),
            sum(cantidad_entregada_detalle(d) for d in grupo_detalles),
            getattr(primero, "marca", "") or "",
            getattr(primero, "modelo", "") or "",
            seriales,
            g.get("estado_fisico", ""),
            g.get("observacion", "") or "",
        ]
        total += int(valores[4] or 0)
        for col, valor in enumerate(valores, start=1):
            ws.cell(fila, col, valor)
            ws.cell(fila, col).alignment = Alignment(vertical="top", wrap_text=True)
        fila += 1
    ws.cell(fila, 1, "TOTAL DE UNIDADES ENTREGADAS").font = Font(bold=True)
    ws.cell(fila, 5, total).font = Font(bold=True)
    ws.auto_filter.ref = f"A{fila_header}:J{max(fila - 1, fila_header)}"
    ws.freeze_panes = f"A{fila_header + 1}"
    widths = [30, 22, 30, 16, 18, 18, 18, 24, 18, 42]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + idx)].width = width
    firma_row = fila + 3
    _insertar_firma_excel(ws, lev.firma, firma_row, "FIRMA DEL DOCENTE / RESPONSABLE — ENTREGA", lev.responsable.nombre if lev.responsable else None, fecha)
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    filename = f"entrega_{_nombre_archivo_excel(lev.ubicacion.nombre if lev.ubicacion else 'ubicacion')}_levantamiento_{lev.id}.xlsx"
    return _respuesta_excel(wb, filename)


@router.get("/{levantamiento_id}/excel/devolucion")
def descargar_excel_devolucion(
    levantamiento_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    area = user_area(user)
    lev = LevantamientoService(db).obtener(levantamiento_id, area)
    if not lev:
        raise HTTPException(status_code=404, detail="Levantamiento no encontrado en tu área.")
    actas = db.query(LevantamientoDevolucion).filter(
        LevantamientoDevolucion.empresa_id == lev.empresa_id,
        LevantamientoDevolucion.levantamiento_id == lev.id,
    ).order_by(LevantamientoDevolucion.created_at.asc(), LevantamientoDevolucion.id.asc()).all()
    if not actas:
        raise HTTPException(status_code=409, detail="Este levantamiento todavía no tiene una devolución firmada.")

    wb = Workbook()
    wb.remove(wb.active)
    for numero, acta in enumerate(actas, start=1):
        ws = wb.create_sheet(title=f"Devolucion {numero:02d}"[:31])
        _estilizar_hoja_excel(ws, f"ACTA DE DEVOLUCIÓN #{numero}", lev, "Constancia firmada de los elementos recibidos de vuelta.")
        ws["A5"] = "Fecha de devolución"
        ws["B5"] = acta.created_at.strftime("%d/%m/%Y %H:%M") if acta.created_at else "—"
        ws["D5"] = "Recibió / registró"
        ws["E5"] = acta.registrado_por or "—"
        ws["G5"] = "Docente que entrega"
        ws["H5"] = acta.docente_nombre or "—"
        columnas = ["Elemento", "Categoría", "Referencia", "Marca", "Modelo", "Serial", "Entregadas", "Recibidas en esta acta", "Nuevas en esta acta", "Faltantes pendientes", "Estado físico", "Observación"]
        fila_header = 7
        _estilizar_encabezado(ws, fila_header, columnas)
        fila = fila_header + 1
        for dato in (acta.detalles_resumen or []):
            valores = [
                dato.get("nombre", ""), dato.get("categoria", ""), dato.get("referencia", ""),
                dato.get("marca", ""), dato.get("modelo", ""), dato.get("serial", ""),
                dato.get("cantidad_entregada", 0), dato.get("devueltas_esta_acta", 0),
                dato.get("nuevas_esta_acta", 0), dato.get("faltantes_pendientes", 0),
                dato.get("estado_fisico", ""), dato.get("observacion", ""),
            ]
            for col, valor in enumerate(valores, start=1):
                ws.cell(fila, col, valor)
                ws.cell(fila, col).alignment = Alignment(vertical="top", wrap_text=True)
            fila += 1
        ws.cell(fila, 1, "TOTALES DEL ACTA").font = Font(bold=True)
        ws.cell(fila, 7, acta.total_entregadas).font = Font(bold=True)
        ws.cell(fila, 8, acta.total_recibidas).font = Font(bold=True)
        ws.cell(fila, 9, acta.total_nuevas).font = Font(bold=True)
        ws.cell(fila, 10, acta.total_faltantes).font = Font(bold=True)
        ws.auto_filter.ref = f"A{fila_header}:L{max(fila - 1, fila_header)}"
        ws.freeze_panes = f"A{fila_header + 1}"
        widths = [28, 20, 25, 18, 18, 22, 13, 21, 18, 20, 17, 42]
        for idx, width in enumerate(widths, start=1):
            ws.column_dimensions[chr(64 + idx) if idx <= 26 else "A"].width = width
        firma_row = fila + 3
        _insertar_firma_excel(
            ws, acta.firma_docente, firma_row,
            "FIRMA DEL DOCENTE / RESPONSABLE — DEVOLUCIÓN",
            acta.docente_nombre, acta.created_at,
        )
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0

    filename = f"devoluciones_{_nombre_archivo_excel(lev.ubicacion.nombre if lev.ubicacion else 'ubicacion')}_levantamiento_{lev.id}.xlsx"
    return _respuesta_excel(wb, filename)
