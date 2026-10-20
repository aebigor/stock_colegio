"""Dependencias de autenticación y permisos del sistema."""
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from jose import JWTError, jwt
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth.models import Rol, Usuario


SUPER_ADMIN_ROLES = {"Super Admin", "Superadministrador"}
PLATFORM_ADMIN_ROLE = "Administrador de Plataforma"
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
        .options(joinedload(Usuario.rol), joinedload(Usuario.empresa))
        .filter(Usuario.usuario == username, Usuario.estado.is_(True))
        .first()
    )
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})

    role_name = user.rol.nombre if user.rol else ""
    is_platform = (
        user.correo.strip().lower() == settings.PLATFORM_ADMIN_EMAIL.strip().lower()
        and role_name == PLATFORM_ADMIN_ROLE
        and user.empresa_id is None
    )
    # La cuenta de tecnología solo puede navegar por la gestión de empresas.
    # No debe terminar dentro de un inventario ni obtener una vista global.
    if role_name == PLATFORM_ADMIN_ROLE:
        if not is_platform:
            raise HTTPException(status_code=403, detail="Cuenta de plataforma no autorizada.")
        if not (request.url.path.startswith("/empresas") or request.url.path == "/logout"):
            raise HTTPException(status_code=303, headers={"Location": "/empresas"})
    else:
        if user.empresa_id is None or (user.empresa is not None and not user.empresa.estado):
            raise HTTPException(status_code=303, headers={"Location": "/login"})
        db.info["empresa_id"] = user.empresa_id

    # El Super Admin principal es el primer Super Admin asociado a la empresa.
    # No requiere una columna nueva ni migrar la base de datos existente.
    request.state.es_superadmin_principal = False
    if user.empresa_id is not None and role_name in SUPER_ADMIN_ROLES:
        principal = (
            db.query(Usuario.id)
            .filter(
                Usuario.empresa_id == user.empresa_id,
                Usuario.rol.has(Rol.nombre.in_(tuple(SUPER_ADMIN_ROLES))),
            )
            .order_by(Usuario.id.asc())
            .first()
        )
        request.state.es_superadmin_principal = bool(principal and principal[0] == user.id)

    # Branding por empresa: usa el nombre del instituto configurado en su
    # propio tenant y recurre al nombre de la empresa si aún no hay configuración.
    if role_name == PLATFORM_ADMIN_ROLE:
        request.state.brand_name = "GESTIÓN DE EMPRESAS"
    else:
        request.state.brand_name = user.empresa.nombre if user.empresa else "Inventario"
        from app.modules.configuracion.model import Configuracion

        # Filtrar explícitamente por la empresa actual, además del filtro
        # global de tenancy. Así el nombre del lateral nunca depende de la
        # configuración de otra empresa aunque cambie la implementación ORM.
        configuracion_empresa = (
            db.query(Configuracion)
            .filter(Configuracion.empresa_id == user.empresa_id)
            .order_by(Configuracion.id.asc())
            .first()
        )
        if configuracion_empresa and configuracion_empresa.abreviatura and configuracion_empresa.abreviatura.strip():
            # La marca visible usa la abreviatura configurada por esa empresa:
            # GIMSAU Inventario, PEPITO Inventario, etc.
            request.state.brand_name = configuracion_empresa.abreviatura.strip().upper()
        elif configuracion_empresa and configuracion_empresa.nombre_colegio and configuracion_empresa.nombre_colegio.strip():
            request.state.brand_name = configuracion_empresa.nombre_colegio.strip()

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
        raise HTTPException(status_code=403, detail="Solo el Super Admin puede gestionar los usuarios y el inventario de su propia empresa")
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


def require_platform_admin(user: Usuario = Depends(get_current_user)) -> Usuario:
    role_name = user.rol.nombre if user.rol else ""
    if (role_name != PLATFORM_ADMIN_ROLE or
        user.correo.strip().lower() != settings.PLATFORM_ADMIN_EMAIL.strip().lower() or
        user.empresa_id is not None):
        raise HTTPException(status_code=403, detail="Solo el administrador principal de tecnología puede gestionar empresas.")
    return user


def require_empresa_superadmin_principal(
    user: Usuario = Depends(require_super_admin),
    db: Session = Depends(get_db),
) -> Usuario:
    """Autoriza funciones reservadas al Super Admin inicial de su empresa."""
    if user.empresa_id is None:
        raise HTTPException(status_code=403, detail="Esta función requiere una cuenta de empresa.")
    principal = (
        db.query(Usuario.id)
        .filter(
            Usuario.empresa_id == user.empresa_id,
            Usuario.rol.has(Rol.nombre.in_(tuple(SUPER_ADMIN_ROLES))),
        )
        .order_by(Usuario.id.asc())
        .first()
    )
    if principal is None or principal[0] != user.id:
        raise HTTPException(status_code=403, detail="Solo el Super Admin principal de esta empresa puede realizar esta acción.")
    return user
