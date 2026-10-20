from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.modules.activos.model import Activo
from app.modules.activos.movimiento_model import Movimiento
from app.modules.categorias.model import Categoria


class ReporteService:
    def __init__(self, db: Session, area: str = "Todas"):
        self.db = db
        self.area = area

    def _activos(self):
        query = self.db.query(Activo)
        if self.area != "Todas":
            query = query.filter(Activo.area == self.area)
        return query

    def _movimientos(self):
        query = self.db.query(Movimiento).options(joinedload(Movimiento.activo_rel))
        if self.area != "Todas":
            query = query.filter(Movimiento.area == self.area)
        return query

    def total_activos(self):
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
        query = self.db.query(Categoria.nombre, func.count(Activo.id))
        if self.area == "Todas":
            query = query.outerjoin(Activo, Activo.categoria_id == Categoria.id)
        else:
            query = query.outerjoin(Activo, (Activo.categoria_id == Categoria.id) & (Activo.area == self.area))
        return query.group_by(Categoria.nombre).order_by(Categoria.nombre).all()

    def activos_mantenimiento(self):
        return self._activos().filter(Activo.estado == "Mantenimiento").order_by(Activo.nombre.asc()).all()

    def cambios_recientes(self, limite: int = 30):
        return self._movimientos().order_by(Movimiento.created_at.desc()).limit(limite).all()

    def exportar_inventario(self):
        return self._activos().options(joinedload(Activo.categoria), joinedload(Activo.ubicacion)).order_by(Activo.area, Activo.nombre).all()
