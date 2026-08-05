from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    func,
)

from app.core.database import Base


class Configuracion(Base):

    __tablename__ = "configuracion"

    id = Column(Integer, primary_key=True, index=True)

    nombre_colegio = Column(String(150), nullable=False)

    abreviatura = Column(String(10), nullable=False)

    formato_codigo = Column(
        String(100),
        default="{PREFIJO}_{COLEGIO}_{CONSECUTIVO}"
    )

    longitud_consecutivo = Column(Integer, default=6)

    separador = Column(String(2), default="_")

    logo = Column(String(255))

    activo = Column(Boolean, default=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )