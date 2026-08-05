from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates

from .service import AuthService

router = APIRouter(tags=["Autenticación"])


@router.get("/")
def inicio():
    return RedirectResponse(
        url="/login",
        status_code=302
    )


@router.get("/login")
def login(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={
            "title": "Iniciar Sesión"
        }
    )


@router.post("/login")
def login_post(
    request: Request,
    usuario: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):

    service = AuthService(db)

    token = service.login(
        usuario,
        password
    )

    if token is None:

        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context={
                "title": "Iniciar Sesión",
                "error": "Usuario o contraseña incorrecta"
            }
        )

    response = RedirectResponse(
        url="/dashboard",
        status_code=302
    )

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax"
    )

    return response


@router.get("/dashboard")
def dashboard(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="dashboard/dashboard.html",
        context={
            "title": "Dashboard"
        }
    )