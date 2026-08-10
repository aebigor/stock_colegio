from sqlalchemy.orm import Session

from .model import Mantenimiento


class MantenimientoService:

    def __init__(self, db: Session):

        self.db = db

    def listar(self):

        return (

            self.db.query(Mantenimiento)

            .order_by(Mantenimiento.created_at.desc())

            .all()

        )

    def obtener(self, id: int):

        return (

            self.db.query(Mantenimiento)

            .filter(Mantenimiento.id == id)

            .first()

        )

    def en_mantenimiento(self):

        return (

            self.db.query(Mantenimiento)

            .filter(Mantenimiento.estado == "En mantenimiento")

            .count()

        )

    def finalizados(self):

        return (

            self.db.query(Mantenimiento)

            .filter(Mantenimiento.estado == "Finalizado")

            .count()

        )