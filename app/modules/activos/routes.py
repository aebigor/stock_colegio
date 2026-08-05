from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request
)

from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates

from .schema import (
    ActivoCreate,
    ActivoUpdate
)

from .service import ActivoService

from app.modules.categorias.service import CategoriaService
from app.modules.ubicaciones.service import UbicacionService
from fastapi.responses import StreamingResponse
from .qr import QRGenerator
from app.modules.personas.service import PersonaService
from fastapi.responses import RedirectResponse, HTMLResponse
from app.modules.activos.movimiento_service import MovimientoService
from app.modules.activos.movimiento_schema import MovimientoCreate

from .barcode import BarcodeGenerator


router = APIRouter(
    prefix="/activos",
    tags=["Activos"]
)


# ==========================================
# LISTAR
# ==========================================

@router.get("/")
def index(
    request: Request,
    db: Session = Depends(get_db)
):

    service = ActivoService(db)

    activos = service.listar()

    return templates.TemplateResponse(
        request=request,
        name="activos/index.html",
        context={
            "title": "Activos",
            "activos": activos,
            "disponibles": service.contar_disponibles(),
            "prestados": service.contar_prestados(),
            "mantenimiento": service.contar_mantenimiento()
        }
    )


# ==========================================
# FORMULARIO CREAR
# ==========================================

@router.get("/crear")
def crear(
    request: Request,
    db: Session = Depends(get_db)
):

    categorias = CategoriaService(db).listar()

    ubicaciones = UbicacionService(db).listar()

    return templates.TemplateResponse(
        request=request,
        name="activos/crear.html",
        context={
            "title": "Nuevo Activo",
            "categorias": categorias,
            "ubicaciones": ubicaciones
        }
    )


# ==========================================
# GUARDAR
# ==========================================

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

    db: Session = Depends(get_db)

):

    service = ActivoService(db)

    datos = ActivoCreate(

        nombre=nombre,

        categoria_id=categoria_id,

        ubicacion_id=ubicacion_id,

        marca=marca,

        modelo=modelo,

        cantidad=cantidad,

        estado=estado,

        observaciones=observaciones

    )

    service.crear(datos)

    return RedirectResponse(
        url="/activos",
        status_code=303
    )


# ==========================================
# DETALLE
# ==========================================

@router.get("/{activo_id}/detalle")
def detalle(

    activo_id: int,

    request: Request,

    db: Session = Depends(get_db)

):

    service = ActivoService(db)

    activo = service.obtener(activo_id)

    if activo is None:

        raise HTTPException(
            status_code=404,
            detail="Activo no encontrado"
        )

    return templates.TemplateResponse(
        request=request,
        name="activos/detalle.html",
        context={
            "title": "Detalle del Activo",
            "activo": activo
        }
    )


# ==========================================
# FORMULARIO EDITAR
# ==========================================

@router.get("/{activo_id}/editar")
def editar(

    activo_id: int,

    request: Request,

    db: Session = Depends(get_db)

):

    service = ActivoService(db)

    activo = service.obtener(activo_id)

    if activo is None:

        raise HTTPException(
            status_code=404,
            detail="Activo no encontrado"
        )

    return templates.TemplateResponse(

        request=request,

        name="activos/editar.html",

        context={

            "title": "Editar Activo",

            "activo": activo,

            "categorias": service.listar_categorias(),

            "ubicaciones": service.listar_ubicaciones()

        }

    )

# ==========================================
# ACTUALIZAR
# ==========================================

@router.post("/{activo_id}/editar")
def actualizar(

    activo_id: int,

    nombre: str = Form(...),

    serial: str = Form(""),

    categoria_id: int = Form(...),

    ubicacion_id: int = Form(...),

    marca: str = Form(""),

    modelo: str = Form(""),

    estado: str = Form(...),

    observaciones: str = Form(""),

    db: Session = Depends(get_db)

):

    service = ActivoService(db)

    datos = ActivoUpdate(

        nombre=nombre,

        serial=serial,

        categoria_id=categoria_id,

        ubicacion_id=ubicacion_id,

        marca=marca,

        modelo=modelo,

        estado=estado,

        observaciones=observaciones

    )

    service.actualizar(

        activo_id,

        datos

    )

    return RedirectResponse(

        "/activos",

        status_code=303

    )

# ==========================================
# DESCARGAR CODIGO DE BARRAS
# ==========================================

@router.get("/{activo_id}/barcode")
def descargar_codigo_barras(

    activo_id: int,

    db: Session = Depends(get_db)

):

    service = ActivoService(db)

    activo = service.obtener(activo_id)

    if activo is None:

        raise HTTPException(

            status_code=404,

            detail="Activo no encontrado"

        )

    pdf = BarcodeGenerator.generar_pdf(

        activo.codigo_barras

    )

    return StreamingResponse(

        pdf,

        media_type="application/pdf",

        headers={

            "Content-Disposition":
            f'attachment; filename="{activo.codigo_barras}.pdf"'

        }

    )

# ==========================================
# DESCARGAR QR
# ==========================================

@router.get("/{activo_id}/qr")
def descargar_qr(

    activo_id: int,

    db: Session = Depends(get_db)

):

    service = ActivoService(db)

    activo = service.obtener(activo_id)

    if activo is None:

        raise HTTPException(
            status_code=404,
            detail="Activo no encontrado"
        )

    pdf = QRGenerator.generar_pdf(activo)

    return StreamingResponse(

        pdf,

        media_type="application/pdf",

        headers={
            "Content-Disposition":
            f'attachment; filename="{activo.codigo_barras}_QR.pdf"'
        }

    )

@router.get(
    "/{activo_id}/movimiento",
    response_class=HTMLResponse
)
def movimiento(
    request: Request,
    activo_id: int,
    db: Session = Depends(get_db)
):

    activo = ActivoService(db).obtener(activo_id)

    if activo is None:
        return RedirectResponse(
            url="/activos",
            status_code=303
        )

    return templates.TemplateResponse(
        request=request,
        name="activos/movimiento.html",
        context={
            "title": "Registrar Movimiento",
            "activo": activo,
            "personas": PersonaService(db).listar(),
            "ubicaciones": UbicacionService(db).listar()
        }
    )

@router.post("/{activo_id}/movimiento")
def guardar_movimiento(

    activo_id: int,

    persona_id: int | None = Form(None),

    ubicacion_id: int | None = Form(None),

    tipo: str = Form(...),

    observaciones: str = Form(""),

    db: Session = Depends(get_db)

):

    estado = "Disponible"

    if tipo == "Entrega":
        estado = "Prestado"

    elif tipo == "Mantenimiento":
        estado = "Mantenimiento"

    elif tipo == "Baja":
        estado = "Baja"

    datos = MovimientoCreate(

        activo_id=activo_id,

        persona_id=persona_id,

        ubicacion_id=ubicacion_id,

        tipo=tipo,

        estado=estado,

        observaciones=observaciones,

        usuario="Administrador"

    )

    MovimientoService(db).crear(datos)

    return RedirectResponse(

        "/activos",

        status_code=303

    )


@router.get(
    "/{activo_id}/historial",
    response_class=HTMLResponse
)
def historial(
    request: Request,
    activo_id: int,
    db: Session = Depends(get_db)
):

    activo = ActivoService(db).obtener(activo_id)

    historial = MovimientoService(db).listar_por_activo(activo_id)

    return templates.TemplateResponse(
        request=request,
        name="activos/historial.html",
        context={
            "title": "Historial",
            "activo": activo,
            "historial": historial
        }
    )