from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates
from app.modules.auth.dependencies import get_current_user, user_area, SUPER_ADMIN_ROLES
from app.modules.auth.models import Usuario
from .service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"], dependencies=[Depends(get_current_user)])


@router.get("")
def dashboard(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    es_super_admin = bool(user.rol and user.rol.nombre in SUPER_ADMIN_ROLES)
    scope_area = "Todas" if es_super_admin else user_area(user)
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
            "es_super_admin": es_super_admin,
            "levantamientos": service.levantamientos_recientes(),
        },
    )
