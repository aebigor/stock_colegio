from fastapi import FastAPI

from app.core.config import settings
from app.core.database import SessionLocal
from fastapi.staticfiles import StaticFiles
from app.modules.auth.routes import router as auth_router

from app.seeders.create_admin import create_admin

app = FastAPI(

    title=settings.APP_NAME,

    version=settings.APP_VERSION

)
app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static"
)

app.include_router(auth_router)

db = SessionLocal()

create_admin(db)

db.close()