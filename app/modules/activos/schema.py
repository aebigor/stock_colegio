from pydantic import BaseModel


# ==========================================
# BASE
# ==========================================

class ActivoBase(BaseModel):

    nombre: str

    descripcion: str | None = None

    categoria_id: int

    ubicacion_id: int

    marca: str | None = None

    modelo: str | None = None

    estado: str = "Disponible"

    observaciones: str | None = None

    activo: bool = True

    area: str = "Medios"


# ==========================================
# CREAR
# ==========================================

class ActivoCreate(ActivoBase):

    # Cantidad de activos a generar
    # No se guarda en la BD
    cantidad: int = 1


# ==========================================
# ACTUALIZAR
# ==========================================

class ActivoUpdate(ActivoBase):

    serial: str | None = None


# ==========================================
# REGISTRAR SERIAL
# ==========================================

class SerialUpdate(BaseModel):

    serial: str


# ==========================================
# RESPUESTA
# ==========================================

class ActivoResponse(ActivoBase):

    id: int

    codigo: str

    codigo_barras: str

    serial: str | None = None

    qr: str | None = None

    class Config:

        from_attributes = True