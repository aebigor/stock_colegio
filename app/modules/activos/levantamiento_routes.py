import re
from io import BytesIO
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from openpyxl import load_workbook
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
    area = "Todas"
    service = LevantamientoService(db)
    es_logistica = _es_logistica(user)
    if es_logistica:
        levantamientos = service.listar("Todas")
    else:
        todos = service.listar("Todas")
        nombre_actual = _nombre_usuario(user)
        levantamientos = [x for x in todos if x.creado_por == nombre_actual]
    levantamiento = service.obtener(levantamiento_id, "Todas") if levantamiento_id else None
    if levantamiento and not es_logistica and levantamiento.creado_por != _nombre_usuario(user):
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
            "es_logistica": es_logistica,
            "es_super_admin": bool(user.rol and user.rol.nombre in SUPER_ADMIN_ROLES),
        },
    )


@router.post("/crear")
def crear(ubicacion_id: int = Form(...), responsable_id: int | None = Form(None), db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    try:
        lev = LevantamientoService(db).crear_borrador(ubicacion_id, responsable_id, "Todas", _nombre_usuario(user))
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
    if not archivo.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Sube un archivo Excel .xlsx o .xlsm.")
    try:
        contenido = await archivo.read()
        wb = load_workbook(BytesIO(contenido), data_only=True)
        ws = wb.active
        header_row, cols = _buscar_encabezados(ws)
        if not header_row:
            raise ValueError("No encontré una fila de encabezados. Usa columnas como ELEMENTO, REFERENCIA, CANT., ESTADO y OBSERVACIÓN.")
        area = "Todas"
        service = LevantamientoService(db)
        lev = service.crear_borrador(ubicacion_id, responsable_id, area, _nombre_usuario(user))
        creados = 0
        for row in range(header_row + 1, ws.max_row + 1):
            nombre = _valor_fila(ws, row, cols.get("nombre"))
            if not nombre or _normalizar(nombre) in {"primero", "segundo", "tercero", "cuarto", "quinto", "sexto", "septimo", "octavo", "noveno", "decimo", "once"}:
                continue
            referencia = _valor_fila(ws, row, cols.get("referencia"))
            marca = _valor_fila(ws, row, cols.get("marca"))
            modelo = _valor_fila(ws, row, cols.get("modelo"))
            serial = _valor_fila(ws, row, cols.get("serial"))
            obs = _valor_fila(ws, row, cols.get("observacion"))
            estado = _valor_fila(ws, row, cols.get("estado")) or "Bueno"
            try:
                cantidad = int(float(_valor_fila(ws, row, cols.get("cantidad")) or 1))
            except ValueError:
                cantidad = 1
            categoria_id = categoria_por_defecto
            categoria_texto = _valor_fila(ws, row, cols.get("categoria"))
            if categoria_texto:
                cat = CategoriaService(db).buscar_nombre(categoria_texto)
                if cat:
                    categoria_id = cat.id
            # Si la referencia coincide con un activo que ya está en esa ubicación,
            # se vincula al levantamiento en vez de crear un duplicado.
            existente = None
            if referencia:
                existente = db.query(Activo).filter(
                    Activo.ubicacion_id == ubicacion_id,
                    Activo.activo.is_(True),
                    (Activo.codigo == referencia) | (Activo.codigo_barras == referencia) | (Activo.serial == referencia),
                ).first()
            if existente:
                service.agregar_existente(lev.id, existente, min(1, max(0, cantidad)), estado, obs)
                creados += 1
                continue
            if not categoria_id:
                continue
            service.agregar_hallazgo(lev.id, nombre, categoria_id, max(1, cantidad), estado, obs, referencia, marca, modelo, serial)
            creados += 1
        if not creados:
            raise ValueError("El Excel no produjo filas válidas. Revisa que tenga ELEMENTO y una categoría por defecto o una columna CATEGORÍA.")
    except Exception as exc:
        db.rollback()
        if isinstance(exc, ValueError):
            raise HTTPException(status_code=400, detail=str(exc))
        raise HTTPException(status_code=400, detail=f"No se pudo leer el Excel: {exc}")
    return RedirectResponse(url=f"/activos/inventario-fisico/?levantamiento_id={lev.id}", status_code=303)


@router.get("/{levantamiento_id}/revisar", response_class=HTMLResponse)
def revisar(levantamiento_id: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(require_roles("Super Admin", "Superadministrador", "Administrador de Logística", "Admin de Logística"))):
    lev = LevantamientoService(db).obtener(levantamiento_id, "Todas")
    if not lev:
        raise HTTPException(status_code=404, detail="Levantamiento no encontrado.")
    return templates.TemplateResponse(request=request, name="activos/inventario_fisico.html", context={
        "title": "Revisar inventario físico", "levantamientos": LevantamientoService(db).listar("Todas"),
        "levantamiento": lev, "ubicaciones": UbicacionService(db).listar("Todas"),
        "personas": PersonaService(db).listar(), "categorias": CategoriaService(db).listar(estado="Activas"),
        "area": "Todas", "usuario_actual": _nombre_usuario(user), "es_logistica": True, "modo_revision": True,
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


@router.post("/{levantamiento_id}/enviar")
def enviar(levantamiento_id: int, firma: str = Form(""), db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    try:
        lev = LevantamientoService(db).obtener(levantamiento_id, user_area(user))
        if not lev:
            raise ValueError("Levantamiento no encontrado.")
        if not _es_logistica(user) and lev.creado_por != _nombre_usuario(user):
            raise ValueError("No puedes enviar el levantamiento de otro usuario.")
        LevantamientoService(db).enviar(levantamiento_id, firma=firma)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/activos/inventario-fisico/?levantamiento_id={levantamiento_id}", status_code=303)


@router.post("/{levantamiento_id}/aprobar")
def aprobar(levantamiento_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_roles("Super Admin", "Superadministrador", "Administrador de Logística", "Admin de Logística"))):
    area = "Todas"
    lev = LevantamientoService(db).obtener(levantamiento_id, area)
    if not lev:
        raise HTTPException(status_code=404, detail="Levantamiento no encontrado.")
    try:
        creados = LevantamientoService(db).aprobar(levantamiento_id, _nombre_usuario(user))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/activos/inventario-fisico/?levantamiento_id={levantamiento_id}", status_code=303)


@router.post("/{levantamiento_id}/devolver-todo")
def devolver_todo(levantamiento_id: int, db: Session = Depends(get_db), user: Usuario = Depends(require_roles("Super Admin", "Superadministrador", "Administrador de Logística", "Admin de Logística"))):
    try:
        devueltos = LevantamientoService(db).devolver_todo(levantamiento_id, _nombre_usuario(user))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/activos/inventario-fisico/?levantamiento_id={levantamiento_id}", status_code=303)
