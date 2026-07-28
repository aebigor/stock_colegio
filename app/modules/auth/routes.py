from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates
from .service import AuthService

# Unificamos el enrutador con sus etiquetas correspondientes
router = APIRouter(tags=["Autenticación"])

@router.get("/")
def inicio():
    return RedirectResponse("/login")

@router.get("/login")
def login(request: Request):
    # Formato moderno corregido para Python 3.14+
    return templates.TemplateResponse(
        request=request,
        name="login.html"
    )

@router.post("/login")
def login_post(
    request: Request,
    usuario: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    service = AuthService(db)
    token = service.login(usuario, password)

    if token is None:
        # Formato moderno corregido para el caso de error de credenciales
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "title": "Iniciar Sesión",
                "error": "Usuario o contraseña incorrecta"
            }
        )

    response = RedirectResponse(
        "/dashboard",
        status_code=302
    )

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True
    )

    return response

@router.get("/dashboard")
def dashboard(request: Request):
    # Formato moderno corregido para la vista del panel principal
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "title": "Dashboard"
        }
    )
