from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import SessionLocal
from app.modules.auth.routes import router as auth_router
from app.modules.usuarios.routes import router as usuarios_router
from app.modules.activos.routes import router as activos_router
from app.modules.categorias.routes import router as categorias_router
from app.modules.personas.routes import router as personas_router
from app.modules.ubicaciones import router as ubicaciones_router
from app.modules.reportes import router as reportes_router
from app.modules.dashboard.routes import router as dashboard_router
from app.modules.mantenimientos.routes import router as mantenimientos_router
from app.modules.configuracion import router as configuracion_router
from app.modules.empresas import router as empresas_router
from app.seeders.create_admin import create_admin


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Ejecutar el seed al iniciar el servidor, no durante la importación del módulo.
    # La base debe tener las migraciones aplicadas antes de arrancar Uvicorn.
    db = SessionLocal()
    try:
        create_admin(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_router)
app.include_router(empresas_router)
app.include_router(usuarios_router)
app.include_router(configuracion_router)
app.include_router(activos_router)
app.include_router(ubicaciones_router)
app.include_router(personas_router)
app.include_router(dashboard_router)
app.include_router(categorias_router)
app.include_router(reportes_router)
app.include_router(mantenimientos_router)
