from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from .models import Usuario


class AuthRepository:

    def __init__(self, db: Session):

        self.db = db

    def get_user(self, usuario: str):

        value = usuario.strip()
        return self.db.query(Usuario).options(joinedload(Usuario.empresa), joinedload(Usuario.rol)).filter(
            or_(Usuario.usuario == value, Usuario.correo.ilike(value))
        ).first()