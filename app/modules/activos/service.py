from sqlalchemy.orm import Session
from sqlalchemy import func

from .model import Activo
from .schema import (
    ActivoCreate,
    ActivoUpdate
)

from app.modules.categorias.model import Categoria
from app.modules.ubicaciones.model import Ubicacion
from app.modules.categorias.model import Categoria


class ActivoService:

    def __init__(self, db: Session):

        self.db = db

    # ==========================================
    # LISTAR
    # ==========================================

    def listar(self):

        return (

            self.db.query(Activo)

            .order_by(Activo.id.desc())

            .all()

        )

    # ==========================================
    # OBTENER
    # ==========================================

    def obtener(self, activo_id: int):

        return (

            self.db.query(Activo)

            .filter(Activo.id == activo_id)

            .first()

        )

    # ==========================================
    # GENERAR CODIGO INTERNO
    # Ej:
    # PC000001
    # HDMI000015
    # ==========================================

    def generar_codigo(self, prefijo: str):

        ultimo = (

            self.db.query(func.max(Activo.id))

            .scalar()

        )

        if ultimo is None:

            ultimo = 0

        consecutivo = ultimo + 1

        return f"{prefijo.upper()}{consecutivo:06d}"

    # ==========================================
    # CODIGO DE BARRAS
    # TEC-GLS-000001
    # ==========================================

    def generar_codigo_barras(self):

        ultimo = (

            self.db.query(func.max(Activo.id))

            .scalar()

        )

        if ultimo is None:

            ultimo = 0

        consecutivo = ultimo + 1

        return f"TEC-GLS-{consecutivo:06d}"

    # ==========================================
    # CREAR
    # ==========================================

    def crear(self, datos: ActivoCreate):

        categoria = (

            self.db.query(Categoria)

            .filter(Categoria.id == datos.categoria_id)

            .first()

        )

        if categoria is None:

            raise Exception("Categoría no encontrada")

        activos_creados = []

        for _ in range(datos.cantidad):

            codigo = self.generar_codigo(
                categoria.prefijo
            )

            codigo_barras = self.generar_codigo_barras()

            activo = Activo(

                codigo=codigo,

                codigo_barras=codigo_barras,

                serial=None,

                nombre=datos.nombre,

                descripcion=datos.descripcion,

                categoria_id=datos.categoria_id,

                ubicacion_id=datos.ubicacion_id,

                marca=datos.marca,

                modelo=datos.modelo,

                estado=datos.estado,

                qr=codigo_barras,

                observaciones=datos.observaciones,

                activo=True

            )

            self.db.add(activo)

            self.db.flush()

            activos_creados.append(activo)

        self.db.commit()

        return activos_creados

    # ==========================================
    # ACTUALIZAR
    # ==========================================

    def actualizar(

        self,

        activo_id: int,

        datos: ActivoUpdate

    ):

        activo = self.obtener(activo_id)

        if activo is None:

            return None

        for campo, valor in datos.model_dump().items():

            setattr(

                activo,

                campo,

                valor

            )

        self.db.commit()

        self.db.refresh(activo)

        return activo

    # ==========================================
    # CAMBIAR ESTADO
    # ==========================================

    def cambiar_estado(

        self,

        activo_id: int

    ):

        activo = self.obtener(activo_id)

        if activo is None:

            return None

        activo.activo = not activo.activo

        self.db.commit()

        self.db.refresh(activo)

        return activo

    def contar_disponibles(self):

        return (
            self.db.query(Activo)
            .filter(
                Activo.estado == "Disponible",
                Activo.activo == True
            )
            .count()
        )


    def contar_prestados(self):

        return (
            self.db.query(Activo)
            .filter(
                Activo.estado == "Prestado",
                Activo.activo == True
            )
            .count()
        )


    def contar_mantenimiento(self):

        return (
            self.db.query(Activo)
            .filter(
                Activo.estado == "Mantenimiento",
                Activo.activo == True
            )
            .count()
        )

    # ==========================
    # UBICACIONES
    # ==========================

    def listar_ubicaciones(self):

        return (

            self.db.query(Ubicacion)

            .filter(Ubicacion.activo == True)

            .order_by(Ubicacion.nombre)

            .all()

        )


    # ==========================
    # CATEGORÍAS
    # ==========================

    def listar_categorias(self):

        return (

            self.db.query(Categoria)

            .filter(Categoria.activo == True)

            .order_by(Categoria.nombre)

            .all()

        )