from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request
from fastapi.responses import HTMLResponse

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates

from .service import MantenimientoService


router = APIRouter(

    prefix="/mantenimientos",

    tags=["Mantenimientos"]

)


@router.get(
    "/",
    response_class=HTMLResponse
)
def index(

    request: Request,

    db: Session = Depends(get_db)

):

    service = MantenimientoService(db)

    return templates.TemplateResponse(

        request=request,

        name="mantenimientos/index.html",

        context={

            "title": "Mantenimientos",

            "mantenimientos": service.listar(),

            "activos": service.en_mantenimiento(),

            "finalizados": service.finalizados()

        }

    )


@router.get(
    "/{id}",
    response_class=HTMLResponse
)
def detalle(

    id: int,

    request: Request,

    db: Session = Depends(get_db)

):

    mantenimiento = MantenimientoService(db).obtener(id)

    return templates.TemplateResponse(

        request=request,

        name="mantenimientos/detalle.html",

        context={

            "title": "Detalle",

            "mantenimiento": mantenimiento

        }

    )