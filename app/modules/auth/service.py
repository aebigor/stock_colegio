from datetime import datetime

from app.core.security import create_access_token, verify_password
from .repository import AuthRepository


class AuthService:
    def __init__(self, db):
        self.db = db
        self.repository = AuthRepository(db)

    def login(self, usuario: str, password: str):
        user = self.repository.get_user(usuario)
        if not user or not user.estado:
            return None, None
        if user.empresa_id is not None and (user.empresa is None or not user.empresa.estado):
            return None, None
        if not verify_password(password, user.password):
            return None, None

        user.ultimo_acceso = datetime.utcnow()
        self.db.commit()
        token = create_access_token({"sub": user.usuario})
        return user, token
