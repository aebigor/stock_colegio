from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates
from app.modules.auth.dependencies import get_current_user, user_area
from app.modules.auth.models import Usuario
from .service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"], dependencies=[Depends(get_current_user)])


@router.get("")
def dashboard(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    scope_area = user_area(user)
    service = DashboardService(db, scope_area)
    return templates.TemplateResponse(
        request=request,
        name="dashboard/dashboard.html",
        context={
            "title": "Panel principal",
            "total": service.total(),
            "disponibles": service.disponibles(),
            "prestados": service.prestados(),
            "mantenimiento": service.mantenimiento(),
            "baja": service.baja(),
            "categorias": service.categorias(),
            "movimientos": service.ultimos_movimientos(),
            "activos_mantenimiento": service.activos_mantenimiento(),
            "area_filtro": scope_area,
        },
    )
