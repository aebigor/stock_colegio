from sqlalchemy.orm import Session, joinedload

from app.modules.activos.model import Activo
from app.modules.activos.movimiento_model import Movimiento
from app.modules.categorias.model import Categoria


class DashboardService:
    def __init__(self, db: Session, area: str = "Todas"):
        self.db = db
        self.area = area

    def _activos(self):
        query = self.db.query(Activo)
        if self.area != "Todas":
            query = query.filter(Activo.area == self.area)
        return query

    def total(self):
        return self._activos().count()

    def disponibles(self):
        return self._activos().filter(Activo.estado == "Disponible", Activo.activo.is_(True)).count()

    def prestados(self):
        return self._activos().filter(Activo.estado == "Prestado", Activo.activo.is_(True)).count()

    def mantenimiento(self):
        return self._activos().filter(Activo.estado == "Mantenimiento", Activo.activo.is_(True)).count()

    def baja(self):
        return self._activos().filter(Activo.estado == "Baja").count()

    def categorias(self):
        return self.db.query(Categoria).filter(Categoria.activo.is_(True)).count()

    def ultimos_movimientos(self):
        query = self.db.query(Movimiento).options(joinedload(Movimiento.activo_rel))
        if self.area != "Todas":
            query = query.filter(Movimiento.area == self.area)
        return query.order_by(Movimiento.created_at.desc()).limit(10).all()

    def activos_mantenimiento(self):
        return self._activos().filter(Activo.estado == "Mantenimiento").order_by(Activo.nombre.asc()).all()
