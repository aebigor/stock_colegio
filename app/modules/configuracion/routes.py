from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates
from app.modules.auth.dependencies import get_current_user, require_super_admin
from app.modules.auth.models import Usuario
from .schema import ConfiguracionCreate
from .service import ConfiguracionService

router = APIRouter(
    prefix="/configuracion",
    tags=["Configuración"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/")
def index(
    request: Request,
    _actor: Usuario = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    configuracion = ConfiguracionService(db).obtener()
    return templates.TemplateResponse(
        request=request,
        name="configuracion/index.html",
        context={"title": "Configuración", "configuracion": configuracion},
    )


@router.post("/guardar")
def guardar(
    nombre_colegio: str = Form(...),
    abreviatura: str = Form(...),
    formato_codigo: str = Form("{PREFIJO}_{COLEGIO}_{CONSECUTIVO}"),
    longitud_consecutivo: int = Form(6),
    separador: str = Form("_"),
    _actor: Usuario = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    nombre_colegio = nombre_colegio.strip()
    abreviatura = abreviatura.strip().upper()
    separador = separador.strip() or "_"
    if not nombre_colegio or not abreviatura:
        raise HTTPException(status_code=400, detail="El nombre del colegio y la abreviatura son obligatorios.")
    if not 1 <= longitud_consecutivo <= 12:
        raise HTTPException(status_code=400, detail="La longitud del consecutivo debe estar entre 1 y 12.")
    if len(separador) > 2:
        raise HTTPException(status_code=400, detail="El separador puede tener máximo 2 caracteres.")

    datos = ConfiguracionCreate(
        nombre_colegio=nombre_colegio,
        abreviatura=abreviatura,
        formato_codigo=formato_codigo.strip() or "{PREFIJO}_{COLEGIO}_{CONSECUTIVO}",
        longitud_consecutivo=longitud_consecutivo,
        separador=separador,
    )
    service = ConfiguracionService(db)
    service.guardar(datos)
    return RedirectResponse(url="/configuracion", status_code=303)
