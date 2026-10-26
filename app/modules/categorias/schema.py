from pydantic import BaseModel


# ==========================================
# BASE
# ==========================================

class CategoriaBase(BaseModel):

    nombre: str

    # Prefijo que usará el sistema para generar
    # automáticamente el código del activo.
    # Ej:
    # PC
    # HDMI
    # MON
    # IMP
    prefijo: str

    descripcion: str | None = None

    icono: str = "bi-pc-display"

    color: str = "#00E5FF"

    permite_prestamo: bool = True

    requiere_firma: bool = False

    requiere_protocolo: bool = False

    requiere_mantenimiento: bool = False

    genera_qr: bool = True

    genera_codigo_barras: bool = True


# ==========================================
# CREAR
# ==========================================

class CategoriaCreate(CategoriaBase):
    pass


# ==========================================
# ACTUALIZAR
# ==========================================

class CategoriaUpdate(CategoriaBase):
    pass


# ==========================================
# RESPUESTA
# ==========================================

class CategoriaResponse(CategoriaBase):

    id: int

    activo: bool

    class Config:
        from_attributes = True