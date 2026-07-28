from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

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

class Usuario(Base):
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

    # Relación bidireccional corregida
    rol = relationship(
        "Rol",
        back_populates="usuarios"
    )
