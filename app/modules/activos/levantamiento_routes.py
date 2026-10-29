import re
from io import BytesIO
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
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
from .levantamiento_service import LevantamientoService
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
        "referencia": {"referencia", "codigo", "codigobarras"},
        "serial": {"serial", "numerodeserie"},
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



def _agrupar_filas_importadas(filas):
    """Agrupa únicamente filas genéricas compatibles; nunca fusiona identificadores individuales.

    El nombre original se conserva. Seriales o referencias impiden agrupar porque
    pueden identificar una unidad física o un registro del inventario maestro.
    Los estados y observaciones también forman parte de la clave para no ocultar
    diferencias entre unidades.
    """
    agrupadas = []
    indices = {}
    for fila in filas:
        fila = dict(fila)
        nombre = str(fila.get("nombre") or "").strip()
        referencia = str(fila.get("referencia") or "").strip()
        serial = str(fila.get("serial") or "").strip()
        cantidad = max(0, int(fila.get("cantidad") or 0))
        if not nombre or cantidad < 1:
            continue

        puede_agrupar = not referencia and not serial
        clave = (
            _normalizar(fila.get("nombre")),
            _normalizar(fila.get("categoria")),
            _normalizar(fila.get("marca")),
            _normalizar(fila.get("modelo")),
            " ".join(str(fila.get("estado") or "").casefold().split()),
            " ".join(str(fila.get("observacion") or "").casefold().split()),
        )
        if puede_agrupar and clave in indices:
            agrupadas[indices[clave]]["cantidad"] += cantidad
            continue

        fila["nombre"] = nombre
        fila["cantidad"] = cantidad
        agrupadas.append(fila)
        if puede_agrupar:
            indices[clave] = len(agrupadas) - 1
    return agrupadas

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
    """Extrae filas del formato PDF real usado por Logística."""
    filas = []
    with pdfplumber.open(BytesIO(contenido)) as pdf:
        for page in pdf.pages:
            tablas = page.find_tables()
            if not tablas:
                continue
            tabla = tablas[0]
            # Las celdas altas de la primera columna son las categorías
            # verticales/agrupadoras del formato.
            rangos_categoria = []
            for cell in tabla.cells:
                x0, top, x1, bottom = cell
                if x0 <= tabla.bbox[0] + 1 and (bottom - top) >= 25 and top > tabla.bbox[1] + 90:
                    nombre_cat = _reconstruir_categoria_vertical(page, cell)
                    if nombre_cat and len(_normalizar(nombre_cat)) >= 4:
                        rangos_categoria.append((top, bottom, nombre_cat))

            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            # Agrupar palabras por línea dentro de la columna ELEMENTO.
            lineas = {}
            for w in words:
                x0, x1, top = w["x0"], w["x1"], w["top"]
                if x0 < 245 or x0 >= 398 or top < 175:
                    continue
                key = round(top / 2) * 2
                lineas.setdefault(key, []).append(w)

            for top_key, ws in sorted(lineas.items()):
                ws = sorted(ws, key=lambda w: w["x0"])
                nombre = " ".join(w["text"] for w in ws).strip()
                if not nombre or _normalizar(nombre) in {"elemento", "observaciones", "observacion"}:
                    continue

                # Buscar cantidad y referencia en la misma línea por posición.
                cantidad_txt = "".join(w["text"] for w in words if 450 <= w["x0"] < 515 and abs(w["top"] - top_key) <= 2)
                referencia = " ".join(w["text"] for w in words if 398 <= w["x0"] < 453 and abs(w["top"] - top_key) <= 2).strip()
                observacion = " ".join(w["text"] for w in words if 619 <= w["x0"] < 790 and abs(w["top"] - top_key) <= 2).strip()
                estados = {
                    "Bueno": any(w["text"].strip().upper() == "B" for w in words if 515 <= w["x0"] < 550 and abs(w["top"] - top_key) <= 2),
                    "Regular": any(w["text"].strip().upper() == "R" for w in words if 550 <= w["x0"] < 585 and abs(w["top"] - top_key) <= 2),
                    "Malo": any(w["text"].strip().upper() == "M" for w in words if 585 <= w["x0"] < 620 and abs(w["top"] - top_key) <= 2),
                }
                estado = next((k for k, v in estados.items() if v), "Bueno")
                cantidad = _parsear_cantidad(cantidad_txt)
                if cantidad <= 0:
                    continue
                y = top_key
                categoria = next((cat for top, bottom, cat in rangos_categoria if top - 1 <= y <= bottom + 1), "")
                filas.append({
                    "nombre": nombre,
                    "referencia": referencia,
                    "cantidad": cantidad,
                    "categoria": categoria,
                    "estado": estado,
                    "observacion": observacion,
                })
    return filas


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

        # Consolidar filas repetidas antes de escribir detalles. Las filas con
        # referencia/serial permanecen individuales para no perder identidad.
        filas = _agrupar_filas_importadas(filas)

        area = user_area(user)
        service = LevantamientoService(db)
        lev = service.crear_borrador(ubicacion_id, responsable_id, area, user.id)
        creados = 0
        activos_existentes_agregados = set()
        categoria_defecto = db.query(Categoria).filter(Categoria.id == categoria_por_defecto).first() if categoria_por_defecto else None

        for fila in filas:
            nombre = str(fila.get("nombre") or "").strip()
            if not nombre:
                continue
            # En el formato actual, los renglones de PRIMERO...ONCE sí son
            # inventario real (son cajas), por lo que ya no se descartan.
            referencia = str(fila.get("referencia") or "").strip()
            obs = str(fila.get("observacion") or "").strip()
            estado = str(fila.get("estado") or "Bueno").strip() or "Bueno"
            cantidad = int(fila.get("cantidad") or 0)
            if cantidad < 1:
                continue

            categoria_id = None
            categoria_texto = str(fila.get("categoria") or "").strip()
            if categoria_texto:
                categoria = _obtener_o_crear_categoria(categoria_texto, db)
                categoria_id = categoria.id if categoria else None
            elif categoria_defecto:
                categoria_id = categoria_defecto.id
            else:
                # Filas que quedan fuera de una celda de categoría vertical
                # se agrupan en una categoría explícita para no perderlas.
                categoria = _obtener_o_crear_categoria("GENERAL", db)
                categoria_id = categoria.id

            existente = None
            serial_importado = str(fila.get("serial") or "").strip()
            if referencia or serial_importado:
                condiciones = []
                if referencia:
                    condiciones.extend([Activo.codigo == referencia, Activo.codigo_barras == referencia, Activo.serial == referencia])
                if serial_importado:
                    condiciones.append(Activo.serial == serial_importado)
                from sqlalchemy import or_
                existente = db.query(Activo).filter(
                    Activo.ubicacion_id == ubicacion_id,
                    Activo.activo.is_(True),
                    or_(*condiciones),
                ).first()
            if existente:
                if existente.id not in activos_existentes_agregados:
                    detalle_existente = db.query(LevantamientoDetalle).filter(
                        LevantamientoDetalle.levantamiento_id == lev.id,
                        LevantamientoDetalle.activo_id == existente.id,
                    ).first()
                    if detalle_existente:
                        detalle_existente.cantidad_encontrada = 1 if cantidad > 0 else 0
                        detalle_existente.estado_fisico = estado
                        detalle_existente.observacion = obs or detalle_existente.observacion
                    else:
                        service.agregar_existente(lev.id, existente, min(1, max(0, cantidad)), estado, obs)
                    activos_existentes_agregados.add(existente.id)
                    creados += 1
                continue

            marca = str(fila.get("marca") or "").strip()
            modelo = str(fila.get("modelo") or "").strip()
            serial = str(fila.get("serial") or "").strip()
            cantidad_restante = cantidad

            # Para artículos genéricos sin serial/código, aprovechar primero
            # los activos que ya aparecen en el borrador para esa ubicación.
            # Cada coincidencia actualiza un detalle individual; el sobrante
            # queda como hallazgo nuevo y se aprobará por unidad.
            if not referencia and not serial:
                existentes_genericos = db.query(LevantamientoDetalle).filter(
                    LevantamientoDetalle.levantamiento_id == lev.id,
                    LevantamientoDetalle.activo_id.isnot(None),
                    LevantamientoDetalle.categoria_id == categoria_id,
                ).all()
                compatibles = []
                for detalle_existente in existentes_genericos:
                    activo = detalle_existente.activo
                    if not activo or activo.id in activos_existentes_agregados:
                        continue
                    if _normalizar(detalle_existente.nombre) != _normalizar(nombre):
                        continue
                    if _normalizar(detalle_existente.marca) != _normalizar(marca):
                        continue
                    if _normalizar(detalle_existente.modelo) != _normalizar(modelo):
                        continue
                    compatibles.append(detalle_existente)

                # La cantidad importada representa lo encontrado: dejar a cero
                # los demás registros compatibles conserva la diferencia como
                # faltante, sin borrar ni dar de baja activos automáticamente.
                for detalle_existente in compatibles:
                    detalle_existente.cantidad_encontrada = 0
                    detalle_existente.estado_fisico = estado
                    detalle_existente.observacion = obs or detalle_existente.observacion
                for detalle_existente in compatibles[:cantidad_restante]:
                    detalle_existente.cantidad_encontrada = 1
                    activos_existentes_agregados.add(detalle_existente.activo_id)
                    cantidad_restante -= 1

            if cantidad_restante > 0:
                service.agregar_hallazgo(
                    lev.id, nombre, categoria_id, cantidad_restante, estado, obs,
                    referencia, marca, modelo, serial,
                )
                creados += 1
            elif cantidad > 0:
                creados += 1

        if not creados:
            # crear_borrador hace commit inicial; si no se extrajo ninguna fila válida,
            # borrar ese borrador vacío para no dejar pruebas huérfanas.
            db.delete(lev)
            db.commit()
            raise ValueError("El archivo no produjo filas válidas. Revisa que existan elementos con cantidad.")
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
        "levantamiento": lev, "ubicaciones": UbicacionService(db).listar("Todas"),
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
