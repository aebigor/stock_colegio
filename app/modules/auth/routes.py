from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates
from app.modules.auth.models import Usuario
from app.core.config import settings
from .service import AuthService
from app.modules.auth.dependencies import get_current_user

router = APIRouter(tags=["Autenticación"])


@router.get("/")
def inicio(user: Usuario = Depends(get_current_user)):
    if user.rol and user.rol.nombre in {"Super Admin", "Superadministrador"}:
        return RedirectResponse(url="/dashboard", status_code=303)
    return RedirectResponse(url="/activos", status_code=303)

@router.get("/login")
def login(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={"title": "Iniciar sesión"},
    )


@router.post("/login")
def login_post(
    request: Request,
    usuario: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    service = AuthService(db)
    user, token = service.login(usuario.strip(), password)

    if user is None or token is None:
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={
                "title": "Iniciar sesión",
                "error": "Usuario o contraseña incorrectos, o cuenta desactivada.",
            },
            status_code=401,
        )

    is_platform = (user.correo.strip().lower() == settings.PLATFORM_ADMIN_EMAIL.strip().lower() and user.rol and user.rol.nombre == "Administrador de Plataforma" and user.empresa_id is None)
    response = RedirectResponse(url="/empresas" if is_platform else ("/dashboard" if user.rol and user.rol.nombre in {"Super Admin", "Superadministrador"} else "/activos"), status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,  # En local HTTP; activar Secure detrás de HTTPS en producción.
        max_age=60 * 60 * 8,
    )
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response
