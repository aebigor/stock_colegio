from sqlalchemy.orm import Session

from .model import Persona
from .schema import (
    PersonaCreate,
    PersonaUpdate
)


class PersonaService:

    def __init__(self, db: Session):

        self.db = db

    # ==========================================
    # LISTAR
    # ==========================================

    def listar(self):

        return (

            self.db.query(Persona)

            .order_by(Persona.nombre)

            .all()

        )

    # ==========================================
    # OBTENER
    # ==========================================

    def obtener(self, persona_id: int):

        return (

            self.db.query(Persona)

            .filter(Persona.id == persona_id)

            .first()

        )

    # ==========================================
    # CREAR
    # ==========================================

    def crear(self, datos: PersonaCreate):

        persona = Persona(

            **datos.model_dump()

        )

        self.db.add(persona)

        self.db.commit()

        self.db.refresh(persona)

        return persona

    # ==========================================
    # ACTUALIZAR
    # ==========================================

    def actualizar(

        self,

        persona_id: int,

        datos: PersonaUpdate

    ):

        persona = self.obtener(persona_id)

        if persona is None:

            return None

        for campo, valor in datos.model_dump().items():

            setattr(

                persona,

                campo,

                valor

            )

        self.db.commit()

        self.db.refresh(persona)

        return persona

    # ==========================================
    # CAMBIAR ESTADO
    # ==========================================

    def cambiar_estado(

        self,

        persona_id: int

    ):

        persona = self.obtener(persona_id)

        if persona is None:

            return None

        persona.activo = not persona.activo

        self.db.commit()

        self.db.refresh(persona)

        return persona

    # ==========================================
    # ELIMINAR
    # ==========================================

    def eliminar(

        self,

        persona_id: int

    ):

        persona = self.obtener(persona_id)

        if persona is None:

            return False

        self.db.delete(persona)

        self.db.commit()

        return True