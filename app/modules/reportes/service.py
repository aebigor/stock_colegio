from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.activos.model import Activo
from app.modules.categorias.model import Categoria


class ReporteService:

    def __init__(self, db: Session):
        self.db = db

    # ==========================================
    # TARJETAS
    # ==========================================

    def total_activos(self):
        return self.db.query(Activo).count()

    def disponibles(self):
        return (
            self.db.query(Activo)
            .filter(Activo.estado == "Disponible")
            .count()
        )

    def prestados(self):
        return (
            self.db.query(Activo)
            .filter(Activo.estado == "Prestado")
            .count()
        )

    def mantenimiento(self):
        return (
            self.db.query(Activo)
            .filter(Activo.estado == "Mantenimiento")
            .count()
        )

    def baja(self):
        return (
            self.db.query(Activo)
            .filter(Activo.estado == "Baja")
            .count()
        )

    # ==========================================
    # RESUMEN POR CATEGORÍAS
    # ==========================================

    def categorias(self):

        return (

            self.db.query(

                Categoria.nombre,

                func.count(Activo.id)

            )

            .join(Activo)

            .group_by(Categoria.nombre)

            .all()

        )

    # ==========================================
    # EXPORTAR INVENTARIO
    # ==========================================

    def exportar_inventario(self):

        return (

            self.db.query(Activo)

            .order_by(Activo.nombre)

            .all()

        )