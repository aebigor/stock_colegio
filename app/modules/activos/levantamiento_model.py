from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.tenancy import TenantScoped


class LevantamientoInventario(TenantScoped, Base):
    __tablename__ = "levantamientos_inventario"

    id = Column(Integer, primary_key=True, index=True)
    ubicacion_id = Column(Integer, ForeignKey("ubicaciones.id"), nullable=False)
    responsable_id = Column(Integer, ForeignKey("personas.id"), nullable=True)
    estado = Column(String(30), nullable=False, default="Borrador")
    observaciones = Column(Text)
    creado_por = Column(String(120), nullable=False)
    aprobado_por = Column(String(120))
    enviado_at = Column(DateTime(timezone=True))
    aprobado_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    area = Column(String(50), nullable=False, default="Medios", server_default="Medios", index=True)
    public_token = Column(String(96), nullable=False, unique=True, index=True)
    # Firma del docente/responsable que diligencia el levantamiento.
    firma = Column(Text, nullable=True)

    ubicacion = relationship("Ubicacion")
    responsable = relationship("Persona")
    detalles = relationship("LevantamientoDetalle", back_populates="levantamiento", cascade="all, delete-orphan")


class LevantamientoDetalle(TenantScoped, Base):
    __tablename__ = "levantamientos_inventario_detalle"

    id = Column(Integer, primary_key=True, index=True)
    levantamiento_id = Column(Integer, ForeignKey("levantamientos_inventario.id", ondelete="CASCADE"), nullable=False, index=True)
    activo_id = Column(Integer, ForeignKey("activos.id"), nullable=True)
    categoria_id = Column(Integer, ForeignKey("categorias.id"), nullable=True)
    nombre = Column(String(180), nullable=False)
    referencia = Column(String(180))
    serial = Column(String(150))
    marca = Column(String(100))
    modelo = Column(String(100))
    cantidad_sistema = Column(Integer, nullable=False, default=0)
    cantidad_encontrada = Column(Integer, nullable=False, default=1)
    estado_fisico = Column(String(40), nullable=False, default="Bueno")
    observacion = Column(Text)
    es_nuevo = Column(Boolean, nullable=False, default=False)
    verificado_logistica = Column(Boolean, nullable=False, default=False)
    revisado_por = Column(String(120))
    revisado_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    levantamiento = relationship("LevantamientoInventario", back_populates="detalles")
    activo = relationship("Activo")
    categoria = relationship("Categoria")
