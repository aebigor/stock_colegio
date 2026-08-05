from sqlalchemy.orm import Session

from app.modules.activos.model import Activo
from app.modules.activos.movimiento_model import Movimiento
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

        # -----------------------------
        # ACTUALIZAR ACTIVO
        # -----------------------------

        activo.estado = datos.estado

        if datos.ubicacion_id:

            activo.ubicacion_id = datos.ubicacion_id

        movimiento = Movimiento(

            **datos.model_dump()

        )

        self.db.add(movimiento)

        self.db.commit()

        self.db.refresh(movimiento)

        return movimiento

    # =======================================

    def listar_por_activo(

        self,

        activo_id: int

    ):

        return (

            self.db.query(Movimiento)

            .filter(

                Movimiento.activo_id == activo_id

            )

            .order_by(

                Movimiento.created_at.desc()

            )

            .all()

        )