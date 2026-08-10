from sqlalchemy.orm import Session

from app.modules.activos.model import Activo
from app.modules.activos.movimiento_model import Movimiento
from app.modules.mantenimientos.model import Mantenimiento
from app.modules.activos.movimiento_schema import (
    MovimientoCreate
)


class MovimientoService:

    def __init__(self, db: Session):

        self.db = db

    # =======================================
    # CREAR MOVIMIENTO
    # =======================================

    def crear(self, datos: MovimientoCreate):

        activo = (
            self.db.query(Activo)
            .filter(Activo.id == datos.activo_id)
            .first()
        )

        if activo is None:
            return None

        # Actualizar activo
        activo.estado = datos.estado

        if datos.ubicacion_id:
            activo.ubicacion_id = datos.ubicacion_id

        # Guardar movimiento
        movimiento = Movimiento(**datos.model_dump())

        self.db.add(movimiento)

        # ===========================
        # CREAR MANTENIMIENTO
        # ===========================

        if datos.tipo == "Mantenimiento":

            mantenimiento = Mantenimiento(

                activo_id=activo.id,

                estado="En mantenimiento",

                observaciones=datos.observaciones,

                tecnico="",

                empresa="",

                diagnostico="",

                solucion="",

                costo=0

            )

            self.db.add(mantenimiento)

        self.db.commit()

        self.db.refresh(movimiento)

        return movimiento