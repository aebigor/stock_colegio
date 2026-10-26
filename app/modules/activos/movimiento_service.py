from sqlalchemy.orm import Session

from app.modules.activos.model import Activo
from app.modules.activos.movimiento_model import Movimiento
from app.modules.activos.movimiento_schema import MovimientoCreate
from app.modules.mantenimientos.model import Mantenimiento
from app.modules.ubicaciones.model import Ubicacion
from app.modules.personas.model import Persona


class MovimientoService:
    def __init__(self, db: Session):
        self.db = db

    def crear(self, datos: MovimientoCreate, area: str = "Todas", usuario: str | None = None):
        query = self.db.query(Activo).filter(Activo.id == datos.activo_id)
        if area != "Todas":
            query = query.filter(Activo.area == area)
        activo = query.first()
        if activo is None:
            return None

        estado_anterior = activo.estado
        ubicacion_origen_id = activo.ubicacion_id
        if datos.persona_id is not None:
            persona = self.db.query(Persona).filter(Persona.id == datos.persona_id).first()
            if persona is None:
                return None
        if datos.ubicacion_id:
            ubicacion = self.db.query(Ubicacion).filter(Ubicacion.id == datos.ubicacion_id).first()
            if ubicacion is None or ubicacion.area != activo.area:
                return None
            activo.ubicacion_id = datos.ubicacion_id
        activo.estado = datos.estado

        # La responsabilidad institucional no se pierde cuando el activo
        # pasa temporalmente a otra persona.
        if datos.tipo == "Entrega" and datos.persona_id is not None:
            if activo.responsable_id is None:
                activo.responsable_id = datos.persona_id
            activo.tenedor_id = datos.persona_id
        elif datos.tipo in {"Devolución", "Devolucion"}:
            activo.tenedor_id = None
            # Una devolución normal conserva el responsable si todavía existe;
            # la devolución masiva final puede liberarlo explícitamente.
            if getattr(datos, "liberar_responsable", False):
                activo.responsable_id = None

        contenido = datos.model_dump(exclude={"area", "liberar_responsable"})
        contenido["ubicacion_origen_id"] = datos.ubicacion_origen_id or ubicacion_origen_id
        contenido["area"] = activo.area
        contenido["usuario"] = usuario or datos.usuario or "Sistema"
        contenido["estado"] = activo.estado
        movimiento = Movimiento(**contenido)
        if estado_anterior != activo.estado and not movimiento.observaciones:
            movimiento.observaciones = f"Estado anterior: {estado_anterior}; estado nuevo: {activo.estado}."
        self.db.add(movimiento)

        if datos.tipo == "Mantenimiento":
            self.db.add(Mantenimiento(
                activo_id=activo.id,
                estado="En mantenimiento",
                observaciones=datos.observaciones,
                tecnico="",
                empresa="",
                diagnostico="",
                solucion="",
                costo=0,
            ))
        self.db.commit()
        self.db.refresh(movimiento)
        return movimiento

    def listar_por_activo(self, activo_id: int, area: str = "Todas"):
        query = self.db.query(Movimiento).filter(Movimiento.activo_id == activo_id)
        if area != "Todas":
            query = query.filter(Movimiento.area == area)
        return query.order_by(Movimiento.created_at.desc()).all()
