from sqlalchemy.orm import Session

from .model import Configuracion


class ConfiguracionService:
    def __init__(self, db: Session):
        self.db = db

    def obtener(self):
        return self.db.query(Configuracion).order_by(Configuracion.id).first()

    def crear(self, data):
        configuracion = Configuracion(**data.model_dump())
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
