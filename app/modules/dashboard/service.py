from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from app.modules.activos.model import Activo
from app.modules.activos.movimiento_model import Movimiento
from app.modules.categorias.model import Categoria


class DashboardService:

    def __init__(self, db: Session):

        self.db = db

    # =====================================
    # TARJETAS
    # =====================================

    def total(self):

        return self.db.query(Activo).count()

    def disponibles(self):

        return (

            self.db.query(Activo)

            .filter(
                Activo.estado == "Disponible"
            )

            .count()

        )

    def prestados(self):

        return (

            self.db.query(Activo)

            .filter(
                Activo.estado == "Prestado"
            )

            .count()

        )

    def mantenimiento(self):

        return (

            self.db.query(Activo)

            .filter(
                Activo.estado == "Mantenimiento"
            )

            .count()

        )

    def baja(self):

        return (

            self.db.query(Activo)

            .filter(
                Activo.estado == "Baja"
            )

            .count()

        )

    def categorias(self):

        return self.db.query(Categoria).count()

    # =====================================
    # ÚLTIMOS MOVIMIENTOS
    # =====================================

    def ultimos_movimientos(self):

        return (

            self.db.query(Movimiento)

            .options(

                joinedload(Movimiento.activo_rel),

                joinedload(Movimiento.persona),

                joinedload(Movimiento.ubicacion)

            )

            .order_by(

                Movimiento.created_at.desc()

            )

            .limit(10)

            .all()

        )

    # =====================================
    # ACTIVOS EN MANTENIMIENTO
    # =====================================

    def activos_mantenimiento(self):

        return (

            self.db.query(Activo)

            .filter(

                Activo.estado == "Mantenimiento"

            )

            .order_by(

                Activo.nombre.asc()

            )

            .all()

        )