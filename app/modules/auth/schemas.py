from pydantic import BaseModel


class LoginSchema(BaseModel):

    usuario: str

    password: str