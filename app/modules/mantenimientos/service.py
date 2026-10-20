from sqlalchemy.orm import Session, joinedload

from .model import Mantenimiento
from app.modules.activos.model import Activo


class MantenimientoService:
    def __init__(self, db: Session):
        self.db = db

    def _query(self, area: str = "Todas"):
        query = self.db.query(Mantenimiento).options(joinedload(Mantenimiento.activo_rel))
        if area != "Todas":
            query = query.filter(Mantenimiento.activo_rel.has(Activo.area == area))
        return query

    def listar(self, area: str = "Todas"):
        return self._query(area).order_by(Mantenimiento.created_at.desc()).all()

    def obtener(self, id: int, area: str = "Todas"):
        return self._query(area).filter(Mantenimiento.id == id).first()

    def en_mantenimiento(self, area: str = "Todas"):
        return self._query(area).filter(Mantenimiento.estado == "En mantenimiento").count()

    def finalizados(self, area: str = "Todas"):
        return self._query(area).filter(Mantenimiento.estado == "Finalizado").count()
