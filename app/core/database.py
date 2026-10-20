from sqlalchemy import create_engine, event, inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import sessionmaker, Session, with_loader_criteria

from app.core.config import settings




engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG
)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


class Base(DeclarativeBase):
    pass


def get_db():

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()

# Tenant filter centralizado: las rutas existentes heredan el aislamiento sin
# depender de que cada consulta recuerde filtrar manualmente por empresa.
from app.core.tenancy import TenantScoped

@event.listens_for(Session, "do_orm_execute")
def _aplicar_aislamiento_empresa(execute_state):
    tenant_id = execute_state.session.info.get("empresa_id")
    if tenant_id is None or execute_state.session.info.get("omitir_filtro_empresa"):
        return
    if execute_state.is_select or execute_state.is_update or execute_state.is_delete:
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                TenantScoped,
                lambda cls: cls.empresa_id == tenant_id,
                include_aliases=True,
            )
        )

@event.listens_for(Session, "before_flush")
def _asignar_empresa_a_filas(session, flush_context, instances):
    tenant_id = session.info.get("empresa_id")
    if tenant_id is None:
        return

    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, TenantScoped):
            continue

        existing_tenant = getattr(obj, "empresa_id", None)
        if existing_tenant is None:
            obj.empresa_id = tenant_id
        elif existing_tenant != tenant_id:
            raise ValueError("No se permite crear ni modificar datos de otra empresa.")

        # Evita que una empresa asocie activos, categorías, ubicaciones,
        # personas o mantenimientos pertenecientes a otro inventario mediante
        # un ID manipulado en un formulario o petición HTTP.
        state = sa_inspect(obj)
        for relationship in state.mapper.relationships:
            target_model = relationship.mapper.class_
            if relationship.direction.name != "MANYTOONE":
                continue
            if not isinstance(target_model, type) or not issubclass(target_model, TenantScoped):
                continue

            related_obj = state.dict.get(relationship.key)
            if related_obj is not None and getattr(related_obj, "empresa_id", None) != tenant_id:
                raise ValueError("No se puede vincular un registro perteneciente a otra empresa.")

            for local_column, remote_column in relationship.local_remote_pairs:
                if local_column.table is not obj.__table__:
                    continue
                foreign_id = getattr(obj, local_column.key, None)
                if foreign_id is None:
                    continue

                previous_bypass = session.info.get("omitir_filtro_empresa", False)
                session.info["omitir_filtro_empresa"] = True
                try:
                    referenced_tenant = session.query(target_model.empresa_id).filter(
                        getattr(target_model, remote_column.key) == foreign_id
                    ).scalar()
                finally:
                    if previous_bypass:
                        session.info["omitir_filtro_empresa"] = True
                    else:
                        session.info.pop("omitir_filtro_empresa", None)

                if referenced_tenant is not None and referenced_tenant != tenant_id:
                    raise ValueError("No se puede vincular un registro perteneciente a otra empresa.")
