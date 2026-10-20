from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Integer,
    String,
    Text,
    func,
)

from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.tenancy import TenantScoped


class Activo(TenantScoped, Base):

    __tablename__ = "activos"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    __table_args__ = (
        UniqueConstraint("empresa_id", "codigo", name="uq_activos_empresa_codigo"),
        UniqueConstraint("empresa_id", "codigo_barras", name="uq_activos_empresa_codigo_barras"),
        UniqueConstraint("empresa_id", "serial", name="uq_activos_empresa_serial"),
    )

    # Código interno
    # Ej: PC000001
    codigo = Column(
        String(30),
        nullable=False,
    )

    # Código físico del colegio
    # Ej: TEC-GLS-000001
    codigo_barras = Column(
        String(40),
        nullable=False,
    )

    # Se diligencia después
    serial = Column(
        String(150),
        nullable=True
    )

    nombre = Column(
        String(150),
        nullable=False
    )

    descripcion = Column(
        Text
    )

    categoria_id = Column(
        Integer,
        ForeignKey("categorias.id"),
        nullable=False
    )

    ubicacion_id = Column(
        Integer,
        ForeignKey("ubicaciones.id"),
        nullable=False
    )

    marca = Column(
        String(100)
    )

    modelo = Column(
        String(100)
    )

    estado = Column(
        String(30),
        nullable=False,
        default="Disponible"
    )

    qr = Column(
        String(255)
    )

    observaciones = Column(
        Text
    )

    # Cada artículo pertenece a un único inventario: Medios o Logística.
    area = Column(
        String(50),
        nullable=False,
        default="Medios",
        server_default="Medios",
        index=True,
    )

    activo = Column(
        Boolean,
        default=True
    )

    fecha_ingreso = Column(
        Date,
        server_default=func.current_date()
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

    categoria = relationship(
        "Categoria",
        back_populates="activos"
    )

    ubicacion = relationship(
        "Ubicacion"
    )

    movimientos = relationship(
        "Movimiento",
        back_populates="activo_rel"
    )