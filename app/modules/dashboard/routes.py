from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates

from .service import DashboardService


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"]
)


@router.get("")
def dashboard(
    request: Request,
    db: Session = Depends(get_db)
):

    dashboard = DashboardService(db)

    return templates.TemplateResponse(

        request=request,

        name="dashboard/dashboard.html",

        context={

            "total": dashboard.total(),

            "disponibles": dashboard.disponibles(),

            "prestados": dashboard.prestados(),

            "mantenimiento": dashboard.mantenimiento(),

            "baja": dashboard.baja(),

            "categorias": dashboard.categorias(),

            "movimientos": dashboard.ultimos_movimientos(),

            "activos_mantenimiento": dashboard.activos_mantenimiento(),

        }

    )