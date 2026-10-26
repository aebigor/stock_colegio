from sqlalchemy import func, case
from sqlalchemy.orm import Session, joinedload

from app.modules.activos.model import Activo
from app.modules.activos.movimiento_model import Movimiento
from app.modules.categorias.model import Categoria
from app.modules.ubicaciones.model import Ubicacion


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
        return self._activos().filter(Activo.activo.is_(True)).count()

    def disponibles(self):
        return self._activos().filter(Activo.estado == "Disponible", Activo.activo.is_(True)).count()

    def prestados(self):
        return self._activos().filter(Activo.estado == "Prestado", Activo.activo.is_(True)).count()

    def mantenimiento(self):
        return self._activos().filter(Activo.estado == "Mantenimiento", Activo.activo.is_(True)).count()

    def baja(self):
        return self._activos().filter(Activo.estado == "Baja", Activo.activo.is_(True)).count()

    def categorias(self):
        query = self.db.query(
            Categoria.nombre,
            func.count(Activo.id),
            func.sum(case((Activo.estado == "Disponible", 1), else_=0)),
            func.sum(case((Activo.estado == "Prestado", 1), else_=0)),
            func.sum(case((Activo.estado == "Mantenimiento", 1), else_=0)),
            func.sum(case((Activo.estado == "Baja", 1), else_=0)),
        )
        join_condition = (Activo.categoria_id == Categoria.id) & (Activo.activo.is_(True))
        if self.area != "Todas":
            join_condition = join_condition & (Activo.area == self.area)
        query = query.outerjoin(Activo, join_condition)
        return query.group_by(Categoria.nombre).order_by(Categoria.nombre).all()

    def resumen_ubicaciones(self):
        """Resume la ubicación física de los activos y conserva los prestados
        bajo su bodega de origen para que el inventario pueda responder:
        'Sala 103 tiene 15 equipos, 13 disponibles y 2 prestados'.
        """
        activos = self._activos().filter(Activo.activo.is_(True)).options(joinedload(Activo.ubicacion)).all()
        ubicaciones = {u.id: u for u in self.db.query(Ubicacion).all()}
        acumulado = {}

        for activo in activos:
            ubicacion_id = activo.ubicacion_id
            if ubicacion_id is None and activo.estado == "Prestado":
                ultima_entrega = (self.db.query(Movimiento)
                    .filter(Movimiento.activo_id == activo.id, Movimiento.tipo == "Entrega")
                    .order_by(Movimiento.created_at.desc(), Movimiento.id.desc())
                    .first())
                ubicacion_id = ultima_entrega.ubicacion_id if ultima_entrega else None

            clave = ubicacion_id or 0
            if clave not in acumulado:
                u = ubicaciones.get(ubicacion_id)
                acumulado[clave] = {
                    "nombre": u.nombre if u else "Sin ubicación",
                    "area": u.area if u else activo.area,
                    "total": 0,
                    "disponibles": 0,
                    "prestados": 0,
                    "mantenimiento": 0,
                    "baja": 0,
                }
            fila = acumulado[clave]
            fila["total"] += 1
            if activo.estado == "Disponible":
                fila["disponibles"] += 1
            elif activo.estado == "Prestado":
                fila["prestados"] += 1
            elif activo.estado == "Mantenimiento":
                fila["mantenimiento"] += 1
            elif activo.estado == "Baja":
                fila["baja"] += 1

        return sorted(acumulado.values(), key=lambda x: (x["area"], x["nombre"]))

    def activos_mantenimiento(self):
        return self._activos().filter(Activo.estado == "Mantenimiento", Activo.activo.is_(True)).order_by(Activo.nombre.asc()).all()

    def cambios_recientes(self, limite: int = 30):
        return self._movimientos().order_by(Movimiento.created_at.desc()).limit(limite).all()

    def exportar_inventario(self):
        return self._activos().options(joinedload(Activo.categoria), joinedload(Activo.ubicacion)).order_by(Activo.area, Activo.nombre).all()
