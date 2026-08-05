from sqlalchemy.orm import Session

from .model import Categoria
from .schema import CategoriaCreate, CategoriaUpdate


class CategoriaService:

    def __init__(self, db: Session):
        self.db = db

    # ==========================
    # LISTAR
    # ==========================
    def listar(self):

        return (
            self.db.query(Categoria)
            .order_by(Categoria.nombre)
            .all()
        )

    # ==========================
    # OBTENER POR ID
    # ==========================
    def obtener(self, categoria_id: int):

        return (
            self.db.query(Categoria)
            .filter(Categoria.id == categoria_id)
            .first()
        )

    # ==========================
    # BUSCAR POR NOMBRE
    # ==========================
    def buscar_nombre(self, nombre: str):

        return (
            self.db.query(Categoria)
            .filter(Categoria.nombre == nombre)
            .first()
        )

    # ==========================
    # BUSCAR POR PREFIJO
    # ==========================
    def buscar_prefijo(self, prefijo: str):

        return (
            self.db.query(Categoria)
            .filter(Categoria.prefijo == prefijo)
            .first()
        )

    # ==========================
    # CREAR
    # ==========================
    def crear(self, datos: CategoriaCreate):

        # Validar nombre repetido
        existe_nombre = self.buscar_nombre(datos.nombre)

        if existe_nombre:
            raise Exception("Ya existe una categoría con ese nombre.")

        # Validar prefijo repetido
        existe_prefijo = self.buscar_prefijo(datos.prefijo)

        if existe_prefijo:
            raise Exception("Ya existe una categoría con ese prefijo.")

        categoria = Categoria(**datos.model_dump())

        self.db.add(categoria)

        self.db.commit()

        self.db.refresh(categoria)

        return categoria

    # ==========================
    # ACTUALIZAR
    # ==========================
    def actualizar(
        self,
        categoria_id: int,
        datos: CategoriaUpdate
    ):

        categoria = self.obtener(categoria_id)

        if categoria is None:
            return None

        for campo, valor in datos.model_dump().items():

            setattr(categoria, campo, valor)

        self.db.commit()

        self.db.refresh(categoria)

        return categoria

    # ==========================
    # CAMBIAR ESTADO
    # ==========================
    def cambiar_estado(self, categoria_id: int):

        categoria = self.obtener(categoria_id)

        if categoria is None:
            return None

        categoria.activo = not categoria.activo

        self.db.commit()

        self.db.refresh(categoria)

        return categoria

    # ==========================
    # ELIMINAR (POR SI SE NECESITA)
    # ==========================
    def eliminar(self, categoria_id: int):

        categoria = self.obtener(categoria_id)

        if categoria is None:
            return False

        self.db.delete(categoria)

        self.db.commit()

        return True