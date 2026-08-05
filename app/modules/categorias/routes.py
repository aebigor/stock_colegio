from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates

from .schema import CategoriaCreate, CategoriaUpdate
from .service import CategoriaService

router = APIRouter(
    prefix="/categorias",
    tags=["Categorías"]
)


# ==========================================
# LISTAR
# ==========================================

@router.get("/")
def index(
    request: Request,
    db: Session = Depends(get_db)
):

    service = CategoriaService(db)

    categorias = service.listar()

    return templates.TemplateResponse(
        request=request,
        name="categorias/index.html",
        context={
            "title": "Categorías",
            "categorias": categorias
        }
    )


# ==========================================
# FORMULARIO CREAR
# ==========================================

@router.get("/crear")
def crear(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="categorias/crear.html",
        context={
            "title": "Nueva Categoría"
        }
    )


# ==========================================
# GUARDAR
# ==========================================

@router.post("/crear")
def guardar(

    nombre: str = Form(...),

    prefijo: str = Form(...),

    descripcion: str = Form(""),

    icono: str = Form("bi-pc-display"),

    color: str = Form("#00E5FF"),

    permite_prestamo: bool = Form(False),

    requiere_firma: bool = Form(False),

    requiere_mantenimiento: bool = Form(False),

    genera_qr: bool = Form(True),

    genera_codigo_barras: bool = Form(True),

    db: Session = Depends(get_db)

):

    service = CategoriaService(db)

    categoria = CategoriaCreate(

        nombre=nombre,

        prefijo=prefijo.upper(),

        descripcion=descripcion,

        icono=icono,

        color=color,

        permite_prestamo=permite_prestamo,

        requiere_firma=requiere_firma,

        requiere_mantenimiento=requiere_mantenimiento,

        genera_qr=genera_qr,

        genera_codigo_barras=genera_codigo_barras

    )

    service.crear(categoria)

    return RedirectResponse(
        url="/categorias",
        status_code=303
    )


# ==========================================
# EDITAR
# ==========================================

@router.get("/{categoria_id}/editar")
def editar(

    categoria_id: int,

    request: Request,

    db: Session = Depends(get_db)

):

    service = CategoriaService(db)

    categoria = service.obtener(categoria_id)

    if categoria is None:

        raise HTTPException(
            status_code=404,
            detail="Categoría no encontrada"
        )

    return templates.TemplateResponse(
        request=request,
        name="categorias/editar.html",
        context={
            "title": "Editar Categoría",
            "categoria": categoria
        }
    )


# ==========================================
# ACTUALIZAR
# ==========================================

@router.post("/{categoria_id}/editar")
def actualizar(

    categoria_id: int,

    nombre: str = Form(...),

    prefijo: str = Form(...),

    descripcion: str = Form(""),

    icono: str = Form(...),

    color: str = Form(...),

    permite_prestamo: bool = Form(False),

    requiere_firma: bool = Form(False),

    requiere_mantenimiento: bool = Form(False),

    genera_qr: bool = Form(True),

    genera_codigo_barras: bool = Form(True),

    db: Session = Depends(get_db)

):

    service = CategoriaService(db)

    datos = CategoriaUpdate(

        nombre=nombre,

        prefijo=prefijo.upper(),

        descripcion=descripcion,

        icono=icono,

        color=color,

        permite_prestamo=permite_prestamo,

        requiere_firma=requiere_firma,

        requiere_mantenimiento=requiere_mantenimiento,

        genera_qr=genera_qr,

        genera_codigo_barras=genera_codigo_barras

    )

    service.actualizar(categoria_id, datos)

    return RedirectResponse(
        url="/categorias",
        status_code=303
    )


# ==========================================
# CAMBIAR ESTADO
# ==========================================

@router.get("/{categoria_id}/estado")
def cambiar_estado(

    categoria_id: int,

    db: Session = Depends(get_db)

):

    service = CategoriaService(db)

    service.cambiar_estado(categoria_id)

    return RedirectResponse(
        url="/categorias",
        status_code=303
    )