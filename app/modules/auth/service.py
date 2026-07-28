from app.core.security import verify_password

from app.core.security import create_access_token

from .repository import AuthRepository


class AuthService:

    def __init__(self, db):

        self.repository = AuthRepository(db)

    def login(

        self,

        usuario,

        password

    ):

        user = self.repository.get_user(usuario)

        if not user:

            return None

        if not verify_password(
            password,
            user.password
        ):

            return None

        token = create_access_token(
            {
                "sub": user.usuario
            }
        )

        return token