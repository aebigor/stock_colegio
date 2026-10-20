from pydantic import BaseModel


class UbicacionBase(BaseModel):

    nombre: str

    codigo: str

    area: str = "Medios"

    curso: str | None = None

    sede: str

    tipo: str

    piso: str | None = None

    descripcion: str | None = None

    activo: bool = True


class UbicacionCreate(UbicacionBase):
    pass


class UbicacionUpdate(UbicacionBase):
    pass


class UbicacionResponse(UbicacionBase):

    id: int

    class Config:

        from_attributes = True