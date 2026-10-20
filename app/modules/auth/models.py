from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.core.tenancy import TenantScoped


class Empresa(Base):
    __tablename__ = "empresas"
    __table_args__ = (UniqueConstraint("nombre", name="uq_empresas_nombre"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    contacto_nombre: Mapped[str] = mapped_column(String(180), nullable=False)
    correo_contacto: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    estado: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    usuarios = relationship("Usuario", back_populates="empresa")


class Rol(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )
    nombre: Mapped[str] = mapped_column(
        String(100),
        unique=True
    )
    descripcion: Mapped[str] = mapped_column(
        String(255)
    )
    estado: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )

    # Relación inversa limpia
    usuarios = relationship(
        "Usuario",
        back_populates="rol"
    )

class Usuario(TenantScoped, Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True
    )
    nombre: Mapped[str] = mapped_column(
        String(100)
    )
    apellido: Mapped[str] = mapped_column(
        String(100)
    )
    correo: Mapped[str] = mapped_column(
        String(150),
        unique=True
    )
    usuario: Mapped[str] = mapped_column(
        String(50),
        unique=True
    )
    password: Mapped[str] = mapped_column(
        String(255)
    )
    estado: Mapped[bool] = mapped_column(
        Boolean,
        default=True
    )
    ultimo_acceso: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow
    )
    rol_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id")
    )
    # Es NULL únicamente para el administrador de la plataforma.
    empresa_id: Mapped[int | None] = mapped_column(
        ForeignKey("empresas.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    area: Mapped[str] = mapped_column(
        String(50),
        default="Medios",
        server_default="Medios",
        nullable=False,
    )

    # Relación bidireccional corregida
    rol = relationship(
        "Rol",
        back_populates="usuarios"
    )
    empresa = relationship("Empresa", back_populates="usuarios")
