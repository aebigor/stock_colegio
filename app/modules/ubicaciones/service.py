from sqlalchemy.orm import Session

from .model import Ubicacion
from .schema import (
    UbicacionCreate,
    UbicacionUpdate
)


class UbicacionService:

    def __init__(self, db: Session):
        self.db = db

    # ==========================================
    # LISTAR
    # ==========================================

    def listar(self):

        return (
            self.db.query(Ubicacion)
            .order_by(Ubicacion.nombre)
            .all()
        )

    # ==========================================
    # OBTENER
    # ==========================================

    def obtener(self, ubicacion_id: int):

        return (
            self.db.query(Ubicacion)
            .filter(Ubicacion.id == ubicacion_id)
            .first()
        )

    # ==========================================
    # CREAR
    # ==========================================

    def crear(self, datos: UbicacionCreate):

        ubicacion = Ubicacion(
            **datos.model_dump()
        )

        self.db.add(ubicacion)

        self.db.commit()

        self.db.refresh(ubicacion)

        return ubicacion

    # ==========================================
    # ACTUALIZAR
    # ==========================================

    def actualizar(
        self,
        ubicacion_id: int,
        datos: UbicacionUpdate
    ):

        ubicacion = self.obtener(ubicacion_id)

        if ubicacion is None:
            return None

        for campo, valor in datos.model_dump().items():

            setattr(
                ubicacion,
                campo,
                valor
            )

        self.db.commit()

        self.db.refresh(ubicacion)

        return ubicacion

    # ==========================================
    # CAMBIAR ESTADO
    # ==========================================

    def cambiar_estado(
        self,
        ubicacion_id: int
    ):

        ubicacion = self.obtener(ubicacion_id)

        if ubicacion is None:
            return None

        ubicacion.activo = not ubicacion.activo

        self.db.commit()

        self.db.refresh(ubicacion)

        return ubicacion