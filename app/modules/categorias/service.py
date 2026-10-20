from sqlalchemy.orm import Session

from .model import Categoria
from .schema import CategoriaCreate, CategoriaUpdate


class CategoriaService:
    def __init__(self, db: Session):
        self.db = db

    def listar(self, q: str | None = None, estado: str = "Todas"):
        query = self.db.query(Categoria)
        if q and q.strip():
            query = query.filter(Categoria.nombre.ilike(f"%{q.strip()}%") | Categoria.prefijo.ilike(f"%{q.strip()}%"))
        if estado == "Activas":
            query = query.filter(Categoria.activo.is_(True))
        elif estado == "Inactivas":
            query = query.filter(Categoria.activo.is_(False))
        return query.order_by(Categoria.nombre).all()

    def obtener(self, categoria_id: int):
        return self.db.query(Categoria).filter(Categoria.id == categoria_id).first()

    def buscar_nombre(self, nombre: str):
        return self.db.query(Categoria).filter(Categoria.nombre.ilike(nombre.strip())).first()

    def buscar_prefijo(self, prefijo: str):
        return self.db.query(Categoria).filter(Categoria.prefijo.ilike(prefijo.strip())).first()

    def crear(self, datos: CategoriaCreate):
        if self.buscar_nombre(datos.nombre):
            raise ValueError("Ya existe una categoría con ese nombre.")
        if self.buscar_prefijo(datos.prefijo):
            raise ValueError("Ya existe una categoría con ese prefijo.")
        categoria = Categoria(**datos.model_dump())
        self.db.add(categoria)
        self.db.commit()
        self.db.refresh(categoria)
        return categoria

    def actualizar(self, categoria_id: int, datos: CategoriaUpdate):
        categoria = self.obtener(categoria_id)
        if categoria is None:
            return None
        repetida = self.buscar_nombre(datos.nombre)
        if repetida and repetida.id != categoria_id:
            raise ValueError("Ya existe una categoría con ese nombre.")
        repetido_prefijo = self.buscar_prefijo(datos.prefijo)
        if repetido_prefijo and repetido_prefijo.id != categoria_id:
            raise ValueError("Ya existe una categoría con ese prefijo.")
        for campo, valor in datos.model_dump().items():
            setattr(categoria, campo, valor)
        self.db.commit()
        self.db.refresh(categoria)
        return categoria

    def cambiar_estado(self, categoria_id: int):
        categoria = self.obtener(categoria_id)
        if categoria is None:
            return None
        categoria.activo = not categoria.activo
        self.db.commit()
        self.db.refresh(categoria)
        return categoria

    def eliminar(self, categoria_id: int):
        categoria = self.obtener(categoria_id)
        if categoria is None:
            return False
        if self.db.query(Categoria).filter(Categoria.id == categoria_id).join(Categoria.activos).first():
            raise ValueError("No se puede eliminar una categoría que tiene artículos. Desactívala para conservar el historial.")
        self.db.delete(categoria)
        self.db.commit()
        return True
