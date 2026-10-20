"""Crea roles base y las cuentas iniciales solo cuando hacen falta.

En producción, define INITIAL_ADMIN_PASSWORD e INITIAL_BADER_PASSWORD en el .env
antes del primer arranque. Las cuentas existentes nunca son sobrescritas.
"""
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.modules.auth.models import Rol, Usuario


BASE_ROLES = [
    ("Super Admin", "Consulta y administra todos los inventarios, usuarios e informes."),
    ("Administrador de Medios", "Administra únicamente el inventario del área de Medios."),
    ("Administrador de Logística", "Administra únicamente el inventario del área de Logística."),
]


def create_admin(db: Session) -> None:
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

    # Compatibilidad: los usuarios que ya tenían el rol general Administrador
    # pasan a tener el rol de Super Admin.
    old_admin_role = db.query(Rol).filter(Rol.nombre == "Administrador").first()
    if old_admin_role is not None and old_admin_role.id != roles["Super Admin"].id:
        db.query(Usuario).filter(Usuario.rol_id == old_admin_role.id).update(
            {Usuario.rol_id: roles["Super Admin"].id}, synchronize_session=False
        )

    # Crear las cuentas iniciales únicamente cuando el sistema no tiene ningún
    # usuario. Si luego el Super Admin cambia el nombre de usuario o el correo
    # de admin/Bader, el siguiente reinicio no debe crear cuentas duplicadas.
    if db.query(Usuario).count() == 0:
        db.add(Usuario(
            nombre="Super",
            apellido="Admin",
            correo="admin@inventario.local",
            usuario="admin",
            password=hash_password(settings.INITIAL_ADMIN_PASSWORD),
            estado=True,
            rol_id=roles["Super Admin"].id,
            area="Todas",
        ))
        db.add(Usuario(
            nombre="Bader",
            apellido="Logística",
            correo="bader@inventario.local",
            usuario="bader",
            password=hash_password(settings.INITIAL_BADER_PASSWORD),
            estado=True,
            rol_id=roles["Administrador de Logística"].id,
            area="Logística",
        ))

    db.commit()
