from pydantic import BaseModel


class ConfiguracionCreate(BaseModel):

    nombre_colegio: str

    abreviatura: str

    formato_codigo: str

    longitud_consecutivo: int

    separador: str


class ConfiguracionResponse(BaseModel):

    id: int

    nombre_colegio: str

    abreviatura: str

    formato_codigo: str

    longitud_consecutivo: int

    separador: str

    class Config:

        from_attributes = True