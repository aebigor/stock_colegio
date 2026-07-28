from sqlalchemy.orm import Session

from .models import Usuario


class AuthRepository:

    def __init__(self, db: Session):

        self.db = db

    def get_user(self, usuario: str):

        return self.db.query(Usuario).filter(
            Usuario.usuario == usuario
        ).first()