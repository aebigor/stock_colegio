from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates
from app.modules.auth.dependencies import get_current_user, user_area
from app.modules.auth.models import Usuario
from .service import MantenimientoService

router = APIRouter(prefix="/mantenimientos", tags=["Mantenimientos"], dependencies=[Depends(get_current_user)])


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    service = MantenimientoService(db)
    area = user_area(user)
    return templates.TemplateResponse(
        request=request,
        name="mantenimientos/index.html",
        context={
            "title": "Mantenimientos",
            "mantenimientos": service.listar(area),
            "activos": service.en_mantenimiento(area),
            "finalizados": service.finalizados(area),
        },
    )


@router.get("/{id}", response_class=HTMLResponse)
def detalle(id: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    mantenimiento = MantenimientoService(db).obtener(id, user_area(user))
    if mantenimiento is None:
        raise HTTPException(status_code=404, detail="Mantenimiento no encontrado en tu inventario.")
    return templates.TemplateResponse(request=request, name="mantenimientos/detalle.html", context={"title": "Detalle de mantenimiento", "mantenimiento": mantenimiento})
