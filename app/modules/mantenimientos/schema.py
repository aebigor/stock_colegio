from datetime import date, datetime

from pydantic import BaseModel


class MantenimientoBase(BaseModel):

    activo_id: int

    tecnico: str | None = None

    empresa: str | None = None

    diagnostico: str | None = None

    solucion: str | None = None

    costo: int | None = None

    fecha_salida: date | None = None

    estado: str = "En mantenimiento"

    observaciones: str | None = None


class MantenimientoCreate(MantenimientoBase):
    pass


class MantenimientoUpdate(MantenimientoBase):
    pass


class MantenimientoResponse(MantenimientoBase):

    id: int

    fecha_ingreso: date

    activo: bool

    created_at: datetime

    class Config:

        from_attributes = True