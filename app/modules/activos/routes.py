from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates
from app.modules.auth.dependencies import get_current_user, user_area, area_permitida
from app.modules.auth.models import Usuario
from app.modules.categorias.service import CategoriaService
from app.modules.personas.service import PersonaService
from app.modules.ubicaciones.service import UbicacionService
from .barcode import BarcodeGenerator
from .catalogo_pdf import generar_catalogo_pdf
from .movimiento_service import MovimientoService
from .movimiento_schema import MovimientoCreate
from .qr import QRGenerator
from app.core.config import settings
from .schema import ActivoCreate, ActivoUpdate
from .service import ActivoService

router = APIRouter(prefix="/activos", tags=["Activos"], dependencies=[Depends(get_current_user)])


def _area_filtro(user: Usuario, requested: str | None) -> str:
    own = user_area(user)
    if own != "Todas":
        return own
    return requested if requested in {"Medios", "Logística"} else "Todas"


def _not_found():
    raise HTTPException(status_code=404, detail="Activo no encontrado en tu inventario.")


@router.get("/")
def index(
    request: Request,
    q: str = "",
    categoria_id: str | None = None,
    estado: str = "Todos",
    registro: str = "Todos",
    area: str | None = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    service = ActivoService(db)
    scope_area = _area_filtro(user, area)
    categoria_id_int = None
    if categoria_id is not None and categoria_id.strip():
        try:
            categoria_id_int = int(categoria_id.strip())
        except ValueError:
            categoria_id_int = None
    if estado not in {"Todos", "Disponible", "Prestado", "Mantenimiento", "Baja"}:
        estado = "Todos"
    if registro not in {"Todos", "Activos", "Inactivos"}:
        registro = "Todos"
    activos = service.listar(scope_area, q, categoria_id_int, estado, registro)
    return templates.TemplateResponse(
        request=request,
        name="activos/index.html",
        context={
            "title": "Inventario de activos",
            "activos": activos,
            "disponibles": service.contar_disponibles(scope_area),
            "prestados": service.contar_prestados(scope_area),
            "mantenimiento": service.contar_mantenimiento(scope_area),
            "categorias": CategoriaService(db).listar(estado="Activas"),
            "q": q,
            "categoria_id": categoria_id_int,
            "estado_filtro": estado,
            "registro_filtro": registro,
            "area_filtro": scope_area,
            "puede_ver_areas": user_area(user) == "Todas",
        },
    )


@router.get("/crear")
def crear(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request,
        name="activos/crear.html",
        context={
            "title": "Nuevo activo",
            "categorias": CategoriaService(db).listar(estado="Activas"),
            "ubicaciones": UbicacionService(db).listar("Todas" if user_area(user) == "Todas" else user_area(user)),
            "area_inicial": "Medios" if user_area(user) == "Todas" else user_area(user),
            "puede_ver_areas": user_area(user) == "Todas",
        },
    )


@router.post("/crear")
def guardar(
    nombre: str = Form(...),
    categoria_id: int = Form(...),
    ubicacion_id: int = Form(...),
    marca: str = Form(""),
    modelo: str = Form(""),
    cantidad: int = Form(1),
    estado: str = Form("Disponible"),
    observaciones: str = Form(""),
    area: str | None = Form(None),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    area_objetivo = area_permitida(user, area)
    if estado not in {"Disponible", "Prestado", "Mantenimiento", "Baja"}:
        raise HTTPException(status_code=400, detail="Estado de activo no válido.")
    datos = ActivoCreate(
        nombre=nombre,
        categoria_id=categoria_id,
        ubicacion_id=ubicacion_id,
        marca=marca,
        modelo=modelo,
        cantidad=cantidad,
        estado=estado,
        observaciones=observaciones,
        area=area_objetivo,
    )
    try:
        ActivoService(db).crear(datos, area=area_objetivo, usuario=user.usuario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url="/activos", status_code=303)


@router.get("/{activo_id}/detalle")
def detalle(activo_id: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    activo = ActivoService(db).obtener(activo_id, user_area(user))
    if activo is None:
        _not_found()
    return templates.TemplateResponse(request=request, name="activos/detalle.html", context={"title": "Detalle del activo", "activo": activo})


@router.get("/{activo_id}/editar")
def editar(activo_id: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    service = ActivoService(db)
    activo = service.obtener(activo_id, user_area(user))
    if activo is None:
        _not_found()
    return templates.TemplateResponse(
        request=request,
        name="activos/editar.html",
        context={
            "title": "Editar activo",
            "activo": activo,
            "categorias": service.listar_categorias(),
            "ubicaciones": UbicacionService(db).listar("Todas", include_inactive=True),
            "puede_ver_areas": user_area(user) == "Todas",
        },
    )


@router.post("/{activo_id}/editar")
def actualizar(
    activo_id: int,
    nombre: str = Form(...),
    serial: str = Form(""),
    descripcion: str = Form(""),
    categoria_id: int = Form(...),
    ubicacion_id: int = Form(...),
    marca: str = Form(""),
    modelo: str = Form(""),
    estado: str = Form(...),
    observaciones: str = Form(""),
    area_nueva: str | None = Form(None),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    if estado not in {"Disponible", "Prestado", "Mantenimiento", "Baja"}:
        raise HTTPException(status_code=400, detail="Estado de activo no válido.")
    area = user_area(user)
    service = ActivoService(db)
    existente = service.obtener(activo_id, area)
    if existente is None:
        _not_found()
    target_area = existente.area
    # Solo el Super Admin puede reasignar un registro a otro inventario.
    if user_area(user) == "Todas" and area_nueva in {"Medios", "Logística"}:
        target_area = area_nueva
    datos = ActivoUpdate(
        nombre=nombre,
        serial=serial or None,
        descripcion=descripcion or None,
        categoria_id=categoria_id,
        ubicacion_id=ubicacion_id,
        marca=marca or None,
        modelo=modelo or None,
        estado=estado,
        observaciones=observaciones or None,
        activo=existente.activo,
        area=target_area,
    )
    try:
        actualizado = service.actualizar(activo_id, datos, area=area, usuario=user.usuario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if actualizado is None:
        _not_found()
    return RedirectResponse(url=f"/activos/{activo_id}/detalle", status_code=303)


@router.post("/{activo_id}/estado")
def cambiar_estado_registro(activo_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    updated = ActivoService(db).cambiar_estado_registro(activo_id, user_area(user), user.usuario)
    if updated is None:
        _not_found()
    return RedirectResponse(url="/activos", status_code=303)


@router.get("/codigos/pdf")
def descargar_todos_los_codigos(
    request: Request,
    area: str | None = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    """Descarga etiquetas PDF QR + barras para todos los activos de las áreas permitidas.

    Incluye estados Disponible, Prestado, Mantenimiento y Baja, así como registros
    desactivados. Los usuarios normales solo pueden exportar su propia área.
    """
    scope_area = _area_filtro(user, area)
    activos = ActivoService(db).listar(
        area=scope_area,
        q=None,
        categoria_id=None,
        estado="Todos",
        registro="Todos",
    )
    base_url = (settings.PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")
    pdf = generar_catalogo_pdf(activos, base_url)
    filename_area = "todas" if scope_area == "Todas" else "logistica" if scope_area == "Logística" else "medios"
    return StreamingResponse(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="etiquetas_qr_barras_{filename_area}.pdf"'},
    )


@router.get("/{activo_id}/barcode")
def descargar_codigo_barras(activo_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    activo = ActivoService(db).obtener(activo_id, user_area(user))
    if activo is None:
        _not_found()
    pdf = BarcodeGenerator.generar_pdf(activo.codigo_barras)
    return StreamingResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{activo.codigo_barras}.pdf"'})


@router.get("/{activo_id}/qr")
def descargar_qr(activo_id: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    activo = ActivoService(db).obtener(activo_id, user_area(user))
    if activo is None:
        _not_found()
    base_url = (settings.PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")
    pdf = QRGenerator.generar_pdf(activo, base_url=base_url)
    return StreamingResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{activo.codigo_barras}_QR.pdf"'})


@router.get("/{activo_id}/movimiento", response_class=HTMLResponse)
def movimiento(activo_id: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    activo = ActivoService(db).obtener(activo_id, user_area(user))
    if activo is None:
        _not_found()
    return templates.TemplateResponse(
        request=request,
        name="activos/movimiento.html",
        context={"title": "Registrar movimiento", "activo": activo, "personas": PersonaService(db).listar(), "ubicaciones": UbicacionService(db).listar(activo.area)},
    )


@router.post("/{activo_id}/movimiento")
def guardar_movimiento(
    activo_id: int,
    persona_id: int | None = Form(None),
    ubicacion_id: int | None = Form(None),
    tipo: str = Form(...),
    observaciones: str = Form(""),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    estados = {"Entrega": "Prestado", "Mantenimiento": "Mantenimiento", "Baja": "Baja", "Devolución": "Disponible", "Devolucion": "Disponible", "Ajuste": "Disponible"}
    if tipo not in estados:
        raise HTTPException(status_code=400, detail="Tipo de movimiento no válido.")
    if ActivoService(db).obtener(activo_id, user_area(user)) is None:
        _not_found()
    datos = MovimientoCreate(
        activo_id=activo_id,
        persona_id=persona_id,
        ubicacion_id=ubicacion_id,
        tipo=tipo,
        estado=estados[tipo],
        observaciones=observaciones,
        usuario=user.usuario,
        area=user_area(user) if user_area(user) != "Todas" else "Medios",
    )
    movimiento = MovimientoService(db).crear(datos, area=user_area(user), usuario=user.usuario)
    if movimiento is None:
        _not_found()
    return RedirectResponse(url=f"/activos/{activo_id}/historial", status_code=303)


@router.get("/{activo_id}/historial", response_class=HTMLResponse)
def historial(activo_id: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    area = user_area(user)
    activo = ActivoService(db).obtener(activo_id, area)
    if activo is None:
        _not_found()
    movimientos = MovimientoService(db).listar_por_activo(activo_id, area)
    return templates.TemplateResponse(request=request, name="activos/historial.html", context={"title": "Historial del activo", "activo": activo, "historial": movimientos})
