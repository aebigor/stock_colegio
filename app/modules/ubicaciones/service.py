from sqlalchemy.orm import Session

from .model import Ubicacion
from .schema import UbicacionCreate, UbicacionUpdate


AREAS_VALIDAS = {"Medios", "Logística"}


class UbicacionService:
    def __init__(self, db: Session):
        self.db = db

    def _consulta(self, area: str = "Todas"):
        query = self.db.query(Ubicacion)
        if area != "Todas":
            query = query.filter(Ubicacion.area == area)
        return query

    def listar(self, area: str = "Todas", include_inactive: bool = False):
        query = self._consulta(area)
        if not include_inactive:
            query = query.filter(Ubicacion.activo.is_(True))
        return query.order_by(Ubicacion.area, Ubicacion.nombre).all()

    def obtener(self, ubicacion_id: int, area: str = "Todas"):
        return self._consulta(area).filter(Ubicacion.id == ubicacion_id).first()

    def crear(self, datos: UbicacionCreate):
        if datos.area not in AREAS_VALIDAS:
            raise ValueError("Selecciona un área válida para la bodega.")
        codigo = datos.codigo.strip().upper()
        existente = self.db.query(Ubicacion).filter(
            Ubicacion.area == datos.area, Ubicacion.codigo == codigo
        ).first()
        if existente:
            raise ValueError("Ya existe una bodega con ese código en esta área.")
        valores = datos.model_dump()
        valores["codigo"] = codigo
        ubicacion = Ubicacion(**valores)
        self.db.add(ubicacion)
        self.db.commit()
        self.db.refresh(ubicacion)
        return ubicacion

    def actualizar(self, ubicacion_id: int, datos: UbicacionUpdate, area_scope: str = "Todas"):
        ubicacion = self.obtener(ubicacion_id, area_scope)
        if ubicacion is None:
            return None
        if datos.area not in AREAS_VALIDAS:
            raise ValueError("Selecciona un área válida para la bodega.")
        codigo = datos.codigo.strip().upper()
        duplicada = self.db.query(Ubicacion).filter(
            Ubicacion.id != ubicacion_id,
            Ubicacion.area == datos.area,
            Ubicacion.codigo == codigo,
        ).first()
        if duplicada:
            raise ValueError("Ya existe otra bodega con ese código en esta área.")
        # Importación diferida para evitar un ciclo entre los paquetes de rutas
        # de Activos y Ubicaciones al iniciar FastAPI/Alembic.
        from app.modules.activos.model import Activo
        activos_asignados = self.db.query(Activo).filter(Activo.ubicacion_id == ubicacion_id).count()
        if datos.area != ubicacion.area and activos_asignados:
            raise ValueError("No puedes cambiar el área de una bodega con artículos asignados. Crea una bodega en el área destino y mueve los artículos desde sus fichas.")
        for campo, valor in datos.model_dump().items():
            setattr(ubicacion, campo, valor)
        ubicacion.codigo = codigo
        self.db.commit()
        self.db.refresh(ubicacion)
        return ubicacion

    def cambiar_estado(self, ubicacion_id: int, area: str = "Todas"):
        ubicacion = self.obtener(ubicacion_id, area)
        if ubicacion is None:
            return None
        ubicacion.activo = not ubicacion.activo
        self.db.commit()
        self.db.refresh(ubicacion)
        return ubicacion
