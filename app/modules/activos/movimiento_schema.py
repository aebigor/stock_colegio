from datetime import datetime
from pydantic import BaseModel


class MovimientoBase(BaseModel):

    activo_id: int

    persona_id: int | None = None

    ubicacion_id: int | None = None

    ubicacion_origen_id: int | None = None

    tipo: str

    estado: str

    estado_entrega: str | None = None

    observaciones: str | None = None

    usuario: str | None = None

    firma: str | None = None

    protocolo_aceptado: bool = False

    liberar_responsable: bool = False

    imagen: str | None = None

    area: str = "Medios"


class MovimientoCreate(MovimientoBase):
    pass


class MovimientoUpdate(MovimientoBase):
    pass


class MovimientoResponse(MovimientoBase):

    id: int

    activo: bool

    created_at: datetime

    class Config:
        from_attributes = True