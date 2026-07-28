from sqlalchemy.orm import Session

from app.modules.auth.models import Rol
from app.modules.auth.models import Usuario

from app.core.security import hash_password


def create_admin(db: Session):

    rol = db.query(Rol).filter(
        Rol.nombre == "Administrador"
    ).first()

    if not rol:

        rol = Rol(
            nombre="Administrador",
            descripcion="Acceso Total",
            estado=True
        )

        db.add(rol)
        db.commit()
        db.refresh(rol)

    usuario = db.query(Usuario).filter(
        Usuario.usuario == "admin"
    ).first()

    if usuario:

        return

    usuario = Usuario(

        nombre="Administrador",

        apellido="Sistema",

        correo="tecnologia@gimsau.edu.co",

        usuario="admin",

        password=hash_password("Gimsau2026"),

        estado=True,

        rol_id=rol.id

    )

    db.add(usuario)

    db.commit()