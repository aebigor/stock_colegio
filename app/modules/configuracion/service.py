from sqlalchemy.orm import Session

from .model import Configuracion


class ConfiguracionService:
    def __init__(self, db: Session):
        self.db = db

    def obtener(self):
        """Devuelve solo la configuración de la empresa de la sesión actual."""
        query = self.db.query(Configuracion)
        tenant_id = self.db.info.get("empresa_id")
        if tenant_id is not None:
            query = query.filter(Configuracion.empresa_id == tenant_id)
        return query.order_by(Configuracion.id.asc()).first()

    def crear(self, data):
        configuracion = Configuracion(**data.model_dump())
        tenant_id = self.db.info.get("empresa_id")
        if tenant_id is not None:
            configuracion.empresa_id = tenant_id
        self.db.add(configuracion)
        self.db.commit()
        self.db.refresh(configuracion)
        return configuracion

    def guardar(self, data):
        configuracion = self.obtener()
        if configuracion is None:
            return self.crear(data)
        for campo, valor in data.model_dump().items():
            setattr(configuracion, campo, valor)
        self.db.commit()
        self.db.refresh(configuracion)
        return configuracion
