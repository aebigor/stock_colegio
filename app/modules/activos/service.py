from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from .model import Activo
from .schema import ActivoCreate, ActivoUpdate
from .movimiento_model import Movimiento
from app.modules.categorias.model import Categoria
from app.modules.ubicaciones.model import Ubicacion


class ActivoService:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _aplicar_area(query, area: str | None):
        if area and area != "Todas":
            query = query.filter(Activo.area == area)
        return query

    def listar(
        self,
        area: str | None = "Todas",
        q: str | None = None,
        categoria_id: int | None = None,
        estado: str | None = None,
        registro: str = "Todos",
    ):
        query = self._aplicar_area(
            self.db.query(Activo).options(joinedload(Activo.categoria), joinedload(Activo.ubicacion)),
            area,
        )
        if q and q.strip():
            patron = f"%{q.strip()}%"
            query = query.filter(or_(
                Activo.nombre.ilike(patron),
                Activo.codigo.ilike(patron),
                Activo.codigo_barras.ilike(patron),
                Activo.serial.ilike(patron),
                Activo.marca.ilike(patron),
                Activo.modelo.ilike(patron),
            ))
        if categoria_id:
            query = query.filter(Activo.categoria_id == categoria_id)
        if estado and estado != "Todos":
            query = query.filter(Activo.estado == estado)
        if registro == "Activos":
            query = query.filter(Activo.activo.is_(True))
        elif registro == "Inactivos":
            query = query.filter(Activo.activo.is_(False))
        return query.order_by(Activo.id.desc()).all()

    def obtener(self, activo_id: int, area: str | None = "Todas"):
        query = self.db.query(Activo).filter(Activo.id == activo_id)
        query = self._aplicar_area(query, area)
        return query.first()

    def generar_codigo(self, prefijo: str) -> str:
        ultimo = self.db.query(func.max(Activo.id)).scalar() or 0
        return f"{prefijo.upper()}{ultimo + 1:06d}"

    def generar_codigo_barras(self) -> str:
        ultimo = self.db.query(func.max(Activo.id)).scalar() or 0
        return f"TEC-GLS-{ultimo + 1:06d}"

    def crear(self, datos: ActivoCreate, area: str = "Medios", usuario: str = "Sistema"):
        categoria = self.db.query(Categoria).filter(Categoria.id == datos.categoria_id).first()
        if categoria is None:
            raise ValueError("La categoría seleccionada no existe.")
        ubicacion = self.db.query(Ubicacion).filter(Ubicacion.id == datos.ubicacion_id).first()
        if ubicacion is None:
            raise ValueError("La ubicación seleccionada no existe.")
        if ubicacion.area != area:
            raise ValueError("La bodega seleccionada no pertenece al inventario de este artículo.")
        if not 1 <= datos.cantidad <= 500:
            raise ValueError("La cantidad debe estar entre 1 y 500.")

        activos_creados = []
        for _ in range(datos.cantidad):
            codigo = self.generar_codigo(categoria.prefijo)
            codigo_barras = self.generar_codigo_barras()
            activo = Activo(
                codigo=codigo,
                codigo_barras=codigo_barras,
                serial=None,
                nombre=datos.nombre.strip(),
                descripcion=datos.descripcion,
                categoria_id=datos.categoria_id,
                ubicacion_id=datos.ubicacion_id,
                marca=datos.marca,
                modelo=datos.modelo,
                estado=datos.estado,
                qr=codigo_barras,
                observaciones=datos.observaciones,
                activo=True,
                area=area,
            )
            self.db.add(activo)
            self.db.flush()
            # El alta también queda en el historial del artículo.
            self.db.add(Movimiento(
                activo_id=activo.id,
                ubicacion_id=activo.ubicacion_id,
                tipo="Alta",
                estado=activo.estado,
                observaciones=f"Artículo registrado en el inventario de {area}.",
                usuario=usuario,
                area=area,
            ))
            activos_creados.append(activo)
        self.db.commit()
        return activos_creados

    def actualizar(
        self,
        activo_id: int,
        datos: ActivoUpdate,
        area: str = "Todas",
        usuario: str = "Sistema",
    ):
        activo = self.obtener(activo_id, area)
        if activo is None:
            return None

        ubicacion_nueva = self.db.query(Ubicacion).filter(Ubicacion.id == datos.ubicacion_id).first()
        if ubicacion_nueva is None:
            raise ValueError("La ubicación seleccionada no existe.")
        if ubicacion_nueva.area != datos.area:
            raise ValueError("La bodega seleccionada debe pertenecer al área del inventario del artículo.")

        campos_a_actualizar = (
            "nombre", "serial", "descripcion", "categoria_id", "ubicacion_id",
            "marca", "modelo", "estado", "observaciones", "activo", "area",
        )
        etiquetas = {
            "nombre": "nombre", "serial": "serial", "descripcion": "descripción",
            "categoria_id": "categoría", "ubicacion_id": "ubicación", "marca": "marca",
            "modelo": "modelo", "estado": "estado", "observaciones": "observaciones",
            "activo": "estado del registro",
            "area": "área del inventario",
        }
        cambios = []
        datos_dict = datos.model_dump(exclude_unset=False)
        estado_anterior = activo.estado
        for campo in campos_a_actualizar:
            if campo not in datos_dict:
                continue
            nuevo = datos_dict[campo]
            anterior = getattr(activo, campo)
            if isinstance(nuevo, str):
                nuevo = nuevo.strip() or None
            if anterior != nuevo:
                cambios.append(f"{etiquetas.get(campo, campo)}: {anterior or '—'} → {nuevo or '—'}")
                setattr(activo, campo, nuevo)

        if cambios:
            tipo = "Baja" if activo.estado == "Baja" and estado_anterior != "Baja" else "Edición"
            self.db.add(Movimiento(
                activo_id=activo.id,
                ubicacion_id=activo.ubicacion_id,
                tipo=tipo,
                estado=activo.estado,
                observaciones="Cambios registrados: " + "; ".join(cambios),
                usuario=usuario,
                area=activo.area,
            ))
            self.db.commit()
            self.db.refresh(activo)
        return activo

    def cambiar_estado_registro(self, activo_id: int, area: str = "Todas", usuario: str = "Sistema"):
        activo = self.obtener(activo_id, area)
        if activo is None:
            return None
        activo.activo = not activo.activo
        tipo = "Baja lógica" if not activo.activo else "Reactivación"
        self.db.add(Movimiento(
            activo_id=activo.id,
            ubicacion_id=activo.ubicacion_id,
            tipo=tipo,
            estado=activo.estado,
            observaciones=f"Registro {'desactivado' if not activo.activo else 'reactivado'} por {usuario}.",
            usuario=usuario,
            area=activo.area,
        ))
        self.db.commit()
        self.db.refresh(activo)
        return activo

    def contar_disponibles(self, area: str = "Todas"):
        query = self._aplicar_area(self.db.query(Activo), area)
        return query.filter(Activo.estado == "Disponible", Activo.activo.is_(True)).count()

    def contar_prestados(self, area: str = "Todas"):
        query = self._aplicar_area(self.db.query(Activo), area)
        return query.filter(Activo.estado == "Prestado", Activo.activo.is_(True)).count()

    def contar_mantenimiento(self, area: str = "Todas"):
        query = self._aplicar_area(self.db.query(Activo), area)
        return query.filter(Activo.estado == "Mantenimiento", Activo.activo.is_(True)).count()

    def listar_categorias(self):
        return self.db.query(Categoria).filter(Categoria.activo.is_(True)).order_by(Categoria.nombre).all()

    def listar_ubicaciones(self, area: str = "Todas", include_inactive: bool = False):
        query = self.db.query(Ubicacion)
        if area != "Todas":
            query = query.filter(Ubicacion.area == area)
        if not include_inactive:
            query = query.filter(Ubicacion.activo.is_(True))
        return query.order_by(Ubicacion.area, Ubicacion.nombre).all()
