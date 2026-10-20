"""Gestión de empresas: acceso reservado al administrador principal de tecnología."""
import re

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.core.templates import templates
from app.modules.auth.dependencies import SUPER_ADMIN_ROLES, require_platform_admin
from app.modules.auth.models import Empresa, Rol, Usuario
from app.modules.configuracion.model import Configuracion

router = APIRouter(prefix="/empresas", tags=["Empresas"])


def _crear_abreviatura(nombre: str) -> str:
    """Genera una abreviatura inicial para la configuración de cada empresa."""
    import unicodedata

    normalizado = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii")
    palabras = re.findall(r"[A-Za-z0-9]+", normalizado.upper())
    if not palabras:
        return "INV"
    if len(palabras) == 1:
        return palabras[0][:10] or "INV"
    return "".join(palabra[0] for palabra in palabras)[:10] or "INV"


@router.get("/configuracion")
def configuracion_plataforma(
    request: Request,
    actor: Usuario = Depends(require_platform_admin),
):
    """Configuración de acceso del administrador que gestiona las empresas."""
    return templates.TemplateResponse(
        request=request,
        name="empresas/configuracion.html",
        context={
            "title": "Configuraciones de plataforma",
            "actor": actor,
        },
    )


@router.post("/configuracion/guardar-acceso")
def guardar_configuracion_plataforma(
    request: Request,
    nombre: str = Form(...),
    apellido: str = Form(...),
    usuario_login: str = Form(...),
    password_actual: str = Form(...),
    password_nueva: str = Form(""),
    confirmar_password: str = Form(""),
    actor: Usuario = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Permite al administrador principal cambiar nombre, usuario y contraseña."""
    nombre = " ".join(nombre.split())
    apellido = " ".join(apellido.split())
    username = usuario_login.strip()

    def volver(error: str):
        return RedirectResponse(url=f"/empresas/configuracion?error={error}", status_code=303)

    if len(nombre) < 2 or len(nombre) > 100 or len(apellido) < 2 or len(apellido) > 100:
        return volver("nombre")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,50}", username):
        return volver("usuario_formato")
    if not verify_password(password_actual, actor.password):
        return volver("password_actual")

    en_uso = (
        db.query(Usuario.id)
        .filter(func.lower(Usuario.usuario) == username.lower(), Usuario.id != actor.id)
        .first()
    )
    if en_uso:
        return volver("usuario_ocupado")

    cambiar_password = bool(password_nueva or confirmar_password)
    if cambiar_password:
        if len(password_nueva) < 10:
            return volver("password_corta")
        if password_nueva != confirmar_password:
            return volver("password_confirmacion")
        if verify_password(password_nueva, actor.password):
            return volver("password_igual")

    actor.nombre = nombre
    actor.apellido = apellido
    actor.usuario = username
    if cambiar_password:
        actor.password = hash_password(password_nueva)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return volver("usuario_ocupado")

    # Si se cambió el usuario de acceso, renovar la cookie para no cerrar la sesión actual.
    token = create_access_token({"sub": actor.usuario})
    response = RedirectResponse(url="/empresas/configuracion?guardado=1", status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=60 * 60 * 8,
    )
    return response


@router.get("/")
def listar_empresas(
    request: Request,
    actor: Usuario = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    empresas = db.query(Empresa).order_by(Empresa.created_at.desc(), Empresa.nombre).all()
    administradores = (
        db.query(Usuario)
        .options(joinedload(Usuario.rol))
        .filter(Usuario.rol.has(Rol.nombre.in_(tuple(SUPER_ADMIN_ROLES))), Usuario.empresa_id.is_not(None))
        .order_by(Usuario.id.asc())
        .all()
    )
    admin_por_empresa = {}
    for admin in administradores:
        admin_por_empresa.setdefault(admin.empresa_id, admin)

    return templates.TemplateResponse(
        request=request,
        name="empresas/index.html",
        context={
            "title": "Gestión de empresas",
            "empresas": empresas,
            "admin_por_empresa": admin_por_empresa,
            "correo_plataforma": actor.correo,
        },
    )


@router.post("/crear")
def crear_empresa_y_superadmin(
    nombre_persona: str = Form(...),
    correo: str = Form(...),
    nombre_empresa: str = Form(...),
    password: str = Form(...),
    actor: Usuario = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Crea en una transacción la empresa y su Super Admin inicial."""
    nombre_completo = " ".join(nombre_persona.split())
    email = correo.strip().lower()
    company_name = " ".join(nombre_empresa.split())

    if len(nombre_completo) < 3:
        raise HTTPException(status_code=400, detail="Escribe el nombre completo de la persona.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=400, detail="Escribe un correo electrónico válido.")
    if len(company_name) < 2:
        raise HTTPException(status_code=400, detail="Escribe el nombre de la empresa o instituto.")
    if len(password) < 10:
        raise HTTPException(status_code=400, detail="La contraseña debe tener al menos 10 caracteres.")

    if db.query(Usuario.id).filter(Usuario.correo.ilike(email)).first():
        raise HTTPException(status_code=400, detail="Ese correo ya está asociado a una cuenta.")

    role = db.query(Rol).filter(Rol.nombre == "Super Admin", Rol.estado.is_(True)).first()
    if role is None:
        raise HTTPException(status_code=500, detail="No existe el rol Super Admin. Reinicia la aplicación para actualizar los roles base.")

    parts = nombre_completo.split(" ", maxsplit=1)
    nombre = parts[0][:100]
    apellido = (parts[1] if len(parts) > 1 else "Sin apellido")[:100]

    # El campo usuario sigue siendo identificador global por el método de login
    # histórico; se genera desde el correo y evita colisiones con cuentas previas.
    local_part = email.split("@", 1)[0]
    base = re.sub(r"[^a-zA-Z0-9_.-]", "", local_part).lower()[:42] or "admin"
    username = base
    suffix = 2
    while db.query(Usuario.id).filter(Usuario.usuario == username).first():
        tail = f"{suffix}"
        username = f"{base[:50-len(tail)]}{tail}"
        suffix += 1

    try:
        # Si la empresa ya existe (por ejemplo, GIMSAU tras migrar los activos
        # históricos), se asigna el primer Super Admin a ese tenant en lugar de
        # crear una segunda empresa vacía con el mismo nombre.
        empresa = db.query(Empresa).filter(func.lower(Empresa.nombre) == company_name.lower()).first()
        if empresa is not None:
            if not empresa.estado:
                raise HTTPException(status_code=400, detail="La empresa ya existe, pero está suspendida. Actívala antes de asignar su Super Admin.")
            existente = db.query(Usuario.id).filter(
                Usuario.empresa_id == empresa.id,
                Usuario.rol.has(Rol.nombre.in_(tuple(SUPER_ADMIN_ROLES))),
            ).first()
            if existente:
                raise HTTPException(status_code=400, detail="Esa empresa ya tiene un Super Admin. Cambia el nombre o administra el usuario existente.")
            empresa.contacto_nombre = nombre_completo[:180]
            empresa.correo_contacto = email
        else:
            empresa = Empresa(
                nombre=company_name,
                contacto_nombre=nombre_completo[:180],
                correo_contacto=email,
                estado=True,
            )
            db.add(empresa)
            db.flush()

        # Cada empresa tiene su propia configuración visual. Si se está
        # recuperando una empresa existente, se conserva el nombre configurado
        # (por ejemplo, "Gimnasio de los Sauces") y solo se crea si falta.
        configuracion_empresa = (
            db.query(Configuracion)
            .filter(Configuracion.empresa_id == empresa.id)
            .order_by(Configuracion.id.asc())
            .first()
        )
        if configuracion_empresa is None:
            db.add(Configuracion(
                empresa_id=empresa.id,
                nombre_colegio=company_name[:150],
                abreviatura=_crear_abreviatura(company_name),
                formato_codigo="{PREFIJO}_{COLEGIO}_{CONSECUTIVO}",
                longitud_consecutivo=6,
                separador="_",
                activo=True,
            ))

        superadmin = Usuario(
            nombre=nombre,
            apellido=apellido,
            correo=email,
            usuario=username,
            password=hash_password(password),
            estado=True,
            rol_id=role.id,
            empresa_id=empresa.id,
            area="Todas",
        )
        db.add(superadmin)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="No fue posible crear la cuenta. Revisa que el nombre de empresa y el correo no estén repetidos.") from exc
    except Exception:
        db.rollback()
        raise

    return RedirectResponse(url="/empresas?creada=1", status_code=303)


@router.get("/{empresa_id}/superadmin")
def formulario_superadmin(
    empresa_id: int,
    request: Request,
    actor: Usuario = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Permite editar el acceso actual o recuperar uno cuando la empresa no lo tiene."""
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if empresa is None:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")

    superadmin = (
        db.query(Usuario)
        .options(joinedload(Usuario.rol))
        .filter(
            Usuario.empresa_id == empresa.id,
            Usuario.rol.has(Rol.nombre.in_(tuple(SUPER_ADMIN_ROLES))),
        )
        .order_by(Usuario.id.asc())
        .first()
    )
    return templates.TemplateResponse(
        request=request,
        name="empresas/editar_superadmin.html",
        context={
            "title": "Editar Super Admin",
            "empresa": empresa,
            "superadmin": superadmin,
            "correo_plataforma": actor.correo,
        },
    )


@router.post("/{empresa_id}/superadmin/guardar")
def guardar_superadmin(
    empresa_id: int,
    nombre_persona: str = Form(...),
    correo: str = Form(...),
    usuario_login: str = Form(...),
    password: str = Form(""),
    actor: Usuario = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    """Actualiza credenciales sin tocar los activos ni los demás usuarios.

    Si la empresa quedó sin Super Admin, crea una cuenta nueva para recuperarlo.
    """
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if empresa is None:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")

    nombre_completo = " ".join(nombre_persona.split())
    email = correo.strip().lower()
    username = usuario_login.strip()
    if len(nombre_completo) < 3:
        return RedirectResponse(url=f"/empresas/{empresa.id}/superadmin?error=nombre", status_code=303)
    if len(email) > 150 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return RedirectResponse(url=f"/empresas/{empresa.id}/superadmin?error=correo", status_code=303)
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,50}", username):
        return RedirectResponse(url=f"/empresas/{empresa.id}/superadmin?error=usuario_formato", status_code=303)
    if password and len(password) < 10:
        return RedirectResponse(url=f"/empresas/{empresa.id}/superadmin?error=password", status_code=303)

    superadmin = (
        db.query(Usuario)
        .filter(
            Usuario.empresa_id == empresa.id,
            Usuario.rol.has(Rol.nombre.in_(tuple(SUPER_ADMIN_ROLES))),
        )
        .order_by(Usuario.id.asc())
        .first()
    )
    if superadmin is None and not password:
        return RedirectResponse(url=f"/empresas/{empresa.id}/superadmin?error=password_requerida", status_code=303)

    email_in_use = db.query(Usuario.id).filter(func.lower(Usuario.correo) == email)
    username_in_use = db.query(Usuario.id).filter(func.lower(Usuario.usuario) == username.lower())
    if superadmin is not None:
        email_in_use = email_in_use.filter(Usuario.id != superadmin.id)
        username_in_use = username_in_use.filter(Usuario.id != superadmin.id)
    if email_in_use.first():
        return RedirectResponse(url=f"/empresas/{empresa.id}/superadmin?error=correo_ocupado", status_code=303)
    if username_in_use.first():
        return RedirectResponse(url=f"/empresas/{empresa.id}/superadmin?error=usuario_ocupado", status_code=303)

    role = db.query(Rol).filter(Rol.nombre == "Super Admin", Rol.estado.is_(True)).first()
    if role is None:
        raise HTTPException(status_code=500, detail="No existe el rol Super Admin. Reinicia la aplicación para actualizar los roles base.")

    parts = nombre_completo.split(" ", maxsplit=1)
    nombre = parts[0][:100]
    apellido = (parts[1] if len(parts) > 1 else "Sin apellido")[:100]

    try:
        if superadmin is None:
            superadmin = Usuario(
                nombre=nombre,
                apellido=apellido,
                correo=email,
                usuario=username,
                password=hash_password(password),
                estado=True,
                rol_id=role.id,
                empresa_id=empresa.id,
                area="Todas",
            )
            db.add(superadmin)
        else:
            superadmin.nombre = nombre
            superadmin.apellido = apellido
            superadmin.correo = email
            superadmin.usuario = username
            if password:
                superadmin.password = hash_password(password)

        empresa.contacto_nombre = nombre_completo[:180]
        empresa.correo_contacto = email
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(url=f"/empresas/{empresa.id}/superadmin?error=duplicado", status_code=303)

    return RedirectResponse(url=f"/empresas/{empresa.id}/superadmin?guardado=1", status_code=303)


@router.post("/{empresa_id}/estado")
def cambiar_estado_empresa(
    empresa_id: int,
    actor: Usuario = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if empresa is None:
        raise HTTPException(status_code=404, detail="Empresa no encontrada.")
    empresa.estado = not empresa.estado
    db.commit()
    return RedirectResponse(url="/empresas", status_code=303)
