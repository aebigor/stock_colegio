from sqlalchemy.orm import Session

from .model import Configuracion


class ConfiguracionService:

    def __init__(self, db: Session):

        self.db = db

    def obtener(self):

        return self.db.query(
            Configuracion
        ).first()

    def crear(self, data):

        configuracion = Configuracion(
            **data.model_dump()
        )

        self.db.add(configuracion)

        self.db.commit()

        self.db.refresh(configuracion)

        return configuracion