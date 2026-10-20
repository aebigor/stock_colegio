"""Dependencias de autenticación y permisos del sistema."""
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from jose import JWTError, jwt
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth.models import Usuario


SUPER_ADMIN_ROLES = {"Super Admin", "Superadministrador", "Administrador"}
LOGISTICA_ROLES = {"Administrador de Logística", "Admin de Logística"}
MEDIOS_ROLES = {"Administrador de Medios", "Admin de Medios"}


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Usuario:
    """Valida la cookie JWT y devuelve el usuario activo."""
    cached_user = getattr(request.state, "user", None)
    if cached_user is not None:
        return cached_user

    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=303, headers={"Location": "/login"})

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        username = payload.get("sub")
        if not username:
            raise JWTError("Token sin usuario")
    except JWTError:
        raise HTTPException(
            status_code=303,
            headers={"Location": "/login"},
        )

    user = (
        db.query(Usuario)
        .options(joinedload(Usuario.rol))
        .filter(Usuario.usuario == username, Usuario.estado.is_(True))
        .first()
    )
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})

    request.state.user = user
    return user


def require_roles(*roles: str) -> Callable:
    def dependency(user: Usuario = Depends(get_current_user)) -> Usuario:
        role_name = user.rol.nombre if user.rol else ""
        if role_name not in roles:
            raise HTTPException(status_code=403, detail="No tienes permisos para realizar esta acción")
        return user
    return dependency


def require_super_admin(user: Usuario = Depends(get_current_user)) -> Usuario:
    role_name = user.rol.nombre if user.rol else ""
    if role_name not in SUPER_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Solo el Super Admin puede gestionar usuarios y consultar todos los inventarios")
    return user


def user_area(user: Usuario) -> str:
    """Devuelve 'Todas' para el Super Admin o el área asignada al usuario."""
    role_name = user.rol.nombre if user.rol else ""
    if role_name in SUPER_ADMIN_ROLES:
        return "Todas"
    if role_name in LOGISTICA_ROLES:
        return "Logística"
    if role_name in MEDIOS_ROLES:
        return "Medios"
    return user.area or "Medios"


def area_permitida(user: Usuario, requested_area: str | None = None) -> str:
    """El área de un usuario normal no puede ser alterada desde el formulario."""
    own_area = user_area(user)
    if own_area != "Todas":
        return own_area
    if requested_area in {"Medios", "Logística"}:
        return requested_area
    return "Medios"
