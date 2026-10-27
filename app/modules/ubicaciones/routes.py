from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates
from app.modules.auth.dependencies import get_current_user, user_area
from app.modules.auth.models import Usuario
from .schema import UbicacionCreate, UbicacionUpdate
from .service import UbicacionService

router = APIRouter(
    prefix="/ubicaciones",
    tags=["Ubicaciones"],
    dependencies=[Depends(get_current_user)],
)


def _scope(user: Usuario, requested_area: str | None = None) -> str:
    own_area = user_area(user)
    if own_area != "Todas":
        return own_area
    if requested_area in {"Medios", "Logística"}:
        return requested_area
    return "Todas"


@router.get("/")
def index(
    request: Request,
    area: str | None = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    scope = "Todas"
    return templates.TemplateResponse(
        request=request,
        name="ubicaciones/index.html",
        context={
            "title": "Bodegas y ubicaciones",
            "ubicaciones": UbicacionService(db).listar(scope, include_inactive=True),
            "area_filtro": scope,
            "puede_ver_areas": True,
        },
    )


@router.get("/crear")
def crear_formulario(request: Request, user: Usuario = Depends(get_current_user),
):
    scope = user_area(user)
    return templates.TemplateResponse(
        request=request,
        name="ubicaciones/crear.html",
        context={
            "title": "Nueva bodega / ubicación",
            "area_inicial": "Medios" if scope == "Todas" else scope,
            "puede_ver_areas": scope == "Todas",
        },
    )


@router.post("/crear")
def guardar(
    nombre: str = Form(...),
    codigo: str = Form(...),
    sede: str = Form(...),
    tipo: str = Form(...),
    curso: str = Form(""),
    piso: str = Form(""),
    descripcion: str = Form(""),
    activo: bool = Form(False),
    area: str | None = Form(None),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),

):
    area_objetivo = area.strip() if area and area.strip() in {"Medios", "Logística"} else user_area(user)
    datos = UbicacionCreate(
        nombre=nombre.strip(), codigo=codigo.strip().upper(), area=area_objetivo,
        curso=curso.strip() or None, sede=sede, tipo=tipo.strip(), piso=piso.strip() or None,
        descripcion=descripcion.strip() or None, activo=activo,
    )
    try:
        UbicacionService(db).crear(datos)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url="/ubicaciones", status_code=303)


@router.get("/{ubicacion_id}/editar")
def editar(
    ubicacion_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),

):
    ubicacion = UbicacionService(db).obtener(ubicacion_id, "Todas")
    if ubicacion is None:
        raise HTTPException(status_code=404, detail="Bodega no encontrada en tu inventario.")
    return templates.TemplateResponse(
        request=request,
        name="ubicaciones/editar.html",
        context={
            "title": "Editar bodega / ubicación", "ubicacion": ubicacion,
            "puede_ver_areas": True,
        },
    )


@router.post("/{ubicacion_id}/editar")
def actualizar(
    ubicacion_id: int,
    nombre: str = Form(...),
    codigo: str = Form(...),
    sede: str = Form(...),
    tipo: str = Form(...),
    curso: str = Form(""),
    piso: str = Form(""),
    descripcion: str = Form(""),
    activo: bool = Form(False),
    area: str | None = Form(None),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),

):
    service = UbicacionService(db)
    actual = service.obtener(ubicacion_id, "Todas")
    if actual is None:
        raise HTTPException(status_code=404, detail="Bodega no encontrada en tu inventario.")
    area_objetivo = area.strip() if area and area.strip() in {"Medios", "Logística"} else actual.area
    datos = UbicacionUpdate(
        nombre=nombre.strip(), codigo=codigo.strip().upper(), area=area_objetivo,
        curso=curso.strip() or None, sede=sede, tipo=tipo.strip(), piso=piso.strip() or None,
        descripcion=descripcion.strip() or None, activo=activo,
    )
    try:
        updated = service.actualizar(ubicacion_id, datos, area_scope="Todas")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Bodega no encontrada en tu inventario.")
    return RedirectResponse(url="/ubicaciones", status_code=303)


@router.get("/{ubicacion_id}/estado")
def cambiar_estado(
    ubicacion_id: int,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),

):
    actualizada = UbicacionService(db).cambiar_estado(ubicacion_id, "Todas")
    if actualizada is None:
        raise HTTPException(status_code=404, detail="Bodega no encontrada en tu inventario.")
    return RedirectResponse(url="/ubicaciones", status_code=303)
