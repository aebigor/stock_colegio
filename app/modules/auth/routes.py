from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates
from app.modules.auth.models import Usuario
from .service import AuthService

router = APIRouter(tags=["Autenticación"])


@router.get("/")
def inicio():
    return RedirectResponse(url="/dashboard", status_code=303)


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

    response = RedirectResponse(url="/dashboard", status_code=303)
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
