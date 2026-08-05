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
    UbicacionCreate,
    UbicacionUpdate
)

from .service import UbicacionService


router = APIRouter(
    prefix="/ubicaciones",
    tags=["Ubicaciones"]
)


# ==========================================
# LISTAR
# ==========================================

@router.get("/")
def index(
    request: Request,
    db: Session = Depends(get_db)
):

    service = UbicacionService(db)

    return templates.TemplateResponse(
        request=request,
        name="ubicaciones/index.html",
        context={
            "title": "Ubicaciones",
            "ubicaciones": service.listar()
        }
    )


# ==========================================
# FORMULARIO CREAR
# ==========================================

@router.get("/crear")
def crear(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="ubicaciones/crear.html",
        context={
            "title": "Nueva Ubicación"
        }
    )


# ==========================================
# GUARDAR
# ==========================================

@router.post("/crear")
def guardar(

    nombre: str = Form(...),

    codigo: str = Form(...),

    curso: str = Form(""),

    sede: str = Form(...),

    tipo: str = Form(...),

    piso: str = Form(""),

    descripcion: str = Form(""),

    activo: bool = Form(False),

    db: Session = Depends(get_db)

):

    service = UbicacionService(db)

    datos = UbicacionCreate(

        nombre=nombre,

        codigo=codigo.upper(),

        curso=curso,

        sede=sede,

        tipo=tipo,

        piso=piso,

        descripcion=descripcion,

        activo=activo

    )

    service.crear(datos)

    return RedirectResponse(
        url="/ubicaciones",
        status_code=303
    )


# ==========================================
# FORMULARIO EDITAR
# ==========================================

@router.get("/{ubicacion_id}/editar")
def editar(
    ubicacion_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    service = UbicacionService(db)

    ubicacion = service.obtener(ubicacion_id)

    if ubicacion is None:

        raise HTTPException(
            status_code=404,
            detail="Ubicación no encontrada"
        )

    return templates.TemplateResponse(
        request=request,
        name="ubicaciones/editar.html",
        context={
            "title": "Editar Ubicación",
            "ubicacion": ubicacion
        }
    )


# ==========================================
# ACTUALIZAR
# ==========================================

@router.post("/{ubicacion_id}/editar")
def actualizar(

    ubicacion_id: int,

    nombre: str = Form(...),

    codigo: str = Form(...),

    curso: str = Form(""),

    sede: str = Form(...),

    tipo: str = Form(...),

    piso: str = Form(""),

    descripcion: str = Form(""),

    activo: bool = Form(False),

    db: Session = Depends(get_db)

):

    service = UbicacionService(db)

    datos = UbicacionUpdate(

        nombre=nombre,

        codigo=codigo.upper(),

        curso=curso,

        sede=sede,

        tipo=tipo,

        piso=piso,

        descripcion=descripcion,

        activo=activo

    )

    service.actualizar(
        ubicacion_id,
        datos
    )

    return RedirectResponse(
        url="/ubicaciones",
        status_code=303
    )

# ==========================================
# CAMBIAR ESTADO
# ==========================================

@router.get("/{ubicacion_id}/estado")
def cambiar_estado(

    ubicacion_id: int,

    db: Session = Depends(get_db)

):

    service = UbicacionService(db)

    service.cambiar_estado(
        ubicacion_id
    )

    return RedirectResponse(
        url="/ubicaciones",
        status_code=303
    )