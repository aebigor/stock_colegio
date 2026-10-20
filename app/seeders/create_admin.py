"""Crea roles base y las cuentas iniciales solo cuando hacen falta.

En producción, define las contraseñas iniciales en .env antes del primer arranque.
La contraseña de una cuenta existente nunca se sobrescribe automáticamente.
"""
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.modules.auth.models import Empresa, Rol, Usuario


BASE_ROLES = [
    ("Administrador de Plataforma", "Gestiona empresas y crea sus Super Admin; no administra directamente sus inventarios."),
    ("Super Admin", "Administra el inventario y los usuarios de su propia empresa."),
    ("Administrador de Medios", "Administra únicamente el inventario del área de Medios."),
    ("Administrador de Logística", "Administra únicamente el inventario del área de Logística."),
]


def create_admin(db: Session) -> None:
    # Empresa histórica de instalación: todos los datos preexistentes se
    # mantienen dentro de GIMSAU tras aplicar la migración multiempresa.
    default_company = db.query(Empresa).filter(Empresa.nombre == "GIMSAU").first()
    if default_company is None:
        default_company = Empresa(
            nombre="GIMSAU",
            contacto_nombre="Administración GIMSAU",
            correo_contacto=settings.PLATFORM_ADMIN_EMAIL.lower(),
            estado=True,
        )
        db.add(default_company)
        db.flush()

    roles: dict[str, Rol] = {}
    for nombre, descripcion in BASE_ROLES:
        rol = db.query(Rol).filter(Rol.nombre == nombre).first()
        if rol is None:
            rol = Rol(nombre=nombre, descripcion=descripcion, estado=True)
            db.add(rol)
            db.flush()
        else:
            rol.descripcion = descripcion
            rol.estado = True
        roles[nombre] = rol

    for nombre, descripcion in [
        ("Administrador de Medios", "Administra únicamente el inventario del área de Medios dentro de su empresa."),
        ("Administrador de Logística", "Administra únicamente el inventario del área de Logística dentro de su empresa."),
    ]:
        rol = db.query(Rol).filter(Rol.nombre == nombre).first()
        if rol is None:
            rol = Rol(nombre=nombre, descripcion=descripcion, estado=True)
            db.add(rol)
            db.flush()
        else:
            rol.descripcion = descripcion
            rol.estado = True
        roles[nombre] = rol

    # El correo autorizado siempre pertenece al plano de plataforma, nunca a
    # una empresa, y no se puede promover a esta función desde los formularios.
    email = settings.PLATFORM_ADMIN_EMAIL.strip().lower()
    platform_user = db.query(Usuario).filter(Usuario.correo.ilike(email)).first()
    if platform_user is None and db.query(Usuario).count() == 0:
        platform_user = Usuario(
            nombre="Administrador",
            apellido="de Tecnología",
            correo=email,
            usuario=email.split("@", 1)[0][:50],
            password=hash_password(settings.INITIAL_ADMIN_PASSWORD),
            estado=True,
            rol_id=roles["Administrador de Plataforma"].id,
            area="Plataforma",
            empresa_id=None,
        )
        db.add(platform_user)
    elif platform_user is not None:
        platform_user.rol_id = roles["Administrador de Plataforma"].id
        platform_user.empresa_id = None
        platform_user.area = "Plataforma"
        platform_user.estado = True

    # Compatibilidad con el usuario histórico de logística: conservarlo en la
    # empresa por defecto y no recrear cuentas en cada reinicio.
    bader = db.query(Usuario).filter(Usuario.correo == "bader@inventario.local").first()
    if bader is None and db.query(Usuario).count() == 0:
        db.add(Usuario(
            nombre="Bader",
            apellido="Logística",
            correo="bader@inventario.local",
            usuario="bader",
            password=hash_password(settings.INITIAL_BADER_PASSWORD),
            estado=True,
            rol_id=roles["Administrador de Logística"].id,
            area="Logística",
            empresa_id=default_company.id,
        ))

    # Ningún rol antiguo denominado Administrador puede mantener privilegios
    # ambiguos: los registros existentes pasan a Super Admin de su empresa.
    old_role = db.query(Rol).filter(Rol.nombre == "Administrador").first()
    if old_role is not None and old_role.id != roles["Super Admin"].id:
        db.query(Usuario).filter(Usuario.rol_id == old_role.id).update(
            {Usuario.rol_id: roles["Super Admin"].id}, synchronize_session=False
        )

    db.commit()
