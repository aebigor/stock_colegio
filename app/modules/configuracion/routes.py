from fastapi import (
    APIRouter,
    Depends,
    Request,
)

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates

from .schema import ConfiguracionCreate
from .service import ConfiguracionService


router = APIRouter(
    prefix="/configuracion",
    tags=["Configuración"]
)


@router.get("/")
def index(
    request: Request,
    db: Session = Depends(get_db),
):

    service = ConfiguracionService(db)

    configuracion = service.obtener()

    return templates.TemplateResponse(
        request=request,
        name="configuracion/index.html",
        context={
            "title": "Configuración",
            "configuracion": configuracion
        }
    )


@router.post("/crear")
def crear(
    configuracion: ConfiguracionCreate,
    db: Session = Depends(get_db),
):

    service = ConfiguracionService(db)

    return service.crear(configuracion)