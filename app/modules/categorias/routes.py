from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates
from app.modules.auth.dependencies import get_current_user
from .schema import CategoriaCreate, CategoriaUpdate
from .service import CategoriaService

router = APIRouter(prefix="/categorias", tags=["Categorías"], dependencies=[Depends(get_current_user)])


@router.get("/")
def index(request: Request, q: str = "", estado: str = "Todas", db: Session = Depends(get_db)):
    if estado not in {"Todas", "Activas", "Inactivas"}:
        estado = "Todas"
    categorias = CategoriaService(db).listar(q=q, estado=estado)
    return templates.TemplateResponse(request=request, name="categorias/index.html", context={"title": "Categorías", "categorias": categorias, "q": q, "estado_filtro": estado})


@router.get("/crear")
def crear(request: Request):
    return templates.TemplateResponse(request=request, name="categorias/crear.html", context={"title": "Nueva categoría"})


@router.post("/crear")
def guardar(
    nombre: str = Form(...), prefijo: str = Form(...), descripcion: str = Form(""),
    icono: str = Form("bi-pc-display"), color: str = Form("#00E5FF"),
    permite_prestamo: bool = Form(False), requiere_firma: bool = Form(False),
    requiere_mantenimiento: bool = Form(False), genera_qr: bool = Form(False),
    genera_codigo_barras: bool = Form(False), db: Session = Depends(get_db),
):
    datos = CategoriaCreate(
        nombre=nombre.strip(), prefijo=prefijo.strip().upper(), descripcion=descripcion,
        icono=icono, color=color, permite_prestamo=permite_prestamo,
        requiere_firma=requiere_firma, requiere_mantenimiento=requiere_mantenimiento,
        genera_qr=genera_qr, genera_codigo_barras=genera_codigo_barras,
    )
    try:
        CategoriaService(db).crear(datos)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url="/categorias", status_code=303)


@router.get("/{categoria_id}/editar")
def editar(categoria_id: int, request: Request, db: Session = Depends(get_db)):
    categoria = CategoriaService(db).obtener(categoria_id)
    if categoria is None:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    return templates.TemplateResponse(request=request, name="categorias/editar.html", context={"title": "Editar categoría", "categoria": categoria})


@router.post("/{categoria_id}/editar")
def actualizar(
    categoria_id: int, nombre: str = Form(...), prefijo: str = Form(...),
    descripcion: str = Form(""), icono: str = Form("bi-pc-display"),
    color: str = Form("#00E5FF"), permite_prestamo: bool = Form(False),
    requiere_firma: bool = Form(False), requiere_mantenimiento: bool = Form(False),
    genera_qr: bool = Form(False), genera_codigo_barras: bool = Form(False),
    db: Session = Depends(get_db),
):
    datos = CategoriaUpdate(
        nombre=nombre.strip(), prefijo=prefijo.strip().upper(), descripcion=descripcion,
        icono=icono, color=color, permite_prestamo=permite_prestamo,
        requiere_firma=requiere_firma, requiere_mantenimiento=requiere_mantenimiento,
        genera_qr=genera_qr, genera_codigo_barras=genera_codigo_barras,
    )
    try:
        categoria = CategoriaService(db).actualizar(categoria_id, datos)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if categoria is None:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    return RedirectResponse(url="/categorias", status_code=303)


@router.post("/{categoria_id}/estado")
def cambiar_estado(categoria_id: int, db: Session = Depends(get_db)):
    categoria = CategoriaService(db).cambiar_estado(categoria_id)
    if categoria is None:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    return RedirectResponse(url="/categorias", status_code=303)
