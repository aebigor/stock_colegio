from pydantic import BaseModel, EmailStr


class PersonaBase(BaseModel):

    nombre: str

    cargo: str

    area: str

    correo: EmailStr | None = None

    telefono: str | None = None

    sede: str

    activo: bool = True


class PersonaCreate(PersonaBase):
    pass


class PersonaUpdate(PersonaBase):
    pass


class PersonaResponse(PersonaBase):

    id: int

    class Config:

        from_attributes = True