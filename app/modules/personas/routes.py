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
    PersonaCreate,
    PersonaUpdate
)

from .service import PersonaService


router = APIRouter(
    prefix="/personas",
    tags=["Personas"]
)


# ===================================================
# LISTAR
# ===================================================

@router.get("/")
def index(
    request: Request,
    db: Session = Depends(get_db)
):

    service = PersonaService(db)

    personas = service.listar()

    return templates.TemplateResponse(
        request=request,
        name="personas/index.html",
        context={
            "title": "Personas",
            "personas": personas
        }
    )


# ===================================================
# FORMULARIO CREAR
# ===================================================

@router.get("/crear")
def crear(
    request: Request
):

    return templates.TemplateResponse(
        request=request,
        name="personas/crear.html",
        context={
            "title": "Nueva Persona"
        }
    )


# ===================================================
# GUARDAR
# ===================================================

@router.post("/crear")
def guardar(

    nombre: str = Form(...),

    cargo: str = Form(...),

    area: str = Form(...),

    correo: str = Form(""),

    telefono: str = Form(""),

    sede: str = Form(...),

    activo: bool = Form(False),

    db: Session = Depends(get_db)

):

    service = PersonaService(db)

    datos = PersonaCreate(

        nombre=nombre,

        cargo=cargo,

        area=area,

        correo=correo if correo else None,

        telefono=telefono if telefono else None,

        sede=sede,

        activo=activo

    )

    service.crear(datos)

    return RedirectResponse(
        "/personas",
        status_code=303
    )


# ===================================================
# FORMULARIO EDITAR
# ===================================================

@router.get("/{persona_id}/editar")
def editar(

    persona_id: int,

    request: Request,

    db: Session = Depends(get_db)

):

    service = PersonaService(db)

    persona = service.obtener(persona_id)

    if persona is None:

        raise HTTPException(
            status_code=404,
            detail="Persona no encontrada"
        )

    return templates.TemplateResponse(
        request=request,
        name="personas/editar.html",
        context={
            "title": "Editar Persona",
            "persona": persona
        }
    )


# ===================================================
# ACTUALIZAR
# ===================================================

@router.post("/{persona_id}/editar")
def actualizar(

    persona_id: int,

    nombre: str = Form(...),

    cargo: str = Form(...),

    area: str = Form(...),

    correo: str = Form(""),

    telefono: str = Form(""),

    sede: str = Form(...),

    activo: bool = Form(False),

    db: Session = Depends(get_db)

):

    service = PersonaService(db)

    datos = PersonaUpdate(

        nombre=nombre,

        cargo=cargo,

        area=area,

        correo=correo if correo else None,

        telefono=telefono if telefono else None,

        sede=sede,

        activo=activo

    )

    persona = service.actualizar(
        persona_id,
        datos
    )

    if persona is None:

        raise HTTPException(
            status_code=404,
            detail="Persona no encontrada"
        )

    return RedirectResponse(
        "/personas",
        status_code=303
    )


# ===================================================
# CAMBIAR ESTADO
# ===================================================

@router.get("/{persona_id}/estado")
def cambiar_estado(

    persona_id: int,

    db: Session = Depends(get_db)

):

    service = PersonaService(db)

    persona = service.cambiar_estado(persona_id)

    if persona is None:

        raise HTTPException(
            status_code=404,
            detail="Persona no encontrada"
        )

    return RedirectResponse(
        "/personas",
        status_code=303
    )


# ===================================================
# DETALLE
# ===================================================

@router.get("/{persona_id}")
def detalle(

    persona_id: int,

    request: Request,

    db: Session = Depends(get_db)

):

    service = PersonaService(db)

    persona = service.obtener(persona_id)

    if persona is None:

        raise HTTPException(
            status_code=404,
            detail="Persona no encontrada"
        )

    return templates.TemplateResponse(
        request=request,
        name="personas/detalle.html",
        context={
            "title": "Detalle Persona",
            "persona": persona
        }
    )