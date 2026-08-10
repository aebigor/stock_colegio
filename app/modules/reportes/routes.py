from fastapi import APIRouter
from fastapi import Depends
from fastapi import Request

from fastapi.responses import HTMLResponse

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates

from .service import ReporteService
from io import BytesIO

from fastapi.responses import StreamingResponse

from openpyxl import Workbook



router = APIRouter(

    prefix="/reportes",

    tags=["Reportes"]

)


@router.get(

    "/",

    response_class=HTMLResponse

)
def index(

    request: Request,

    db: Session = Depends(get_db)

):

    service = ReporteService(db)

    return templates.TemplateResponse(

        request=request,

        name="reportes/index.html",

        context={

            "title": "Reportes",

            "total": service.total_activos(),

            "disponibles": service.disponibles(),

            "prestados": service.prestados(),

            "mantenimiento": service.mantenimiento(),

            "baja": service.baja(),

            "categorias": service.categorias()

        }

    )

# ==========================================
# EXPORTAR INVENTARIO EXCEL
# ==========================================

@router.get("/excel")
def exportar_excel(

    db: Session = Depends(get_db)

):

    activos = ReporteService(db).exportar_inventario()

    wb = Workbook()

    ws = wb.active

    ws.title = "Inventario"

    ws.append([

        "Código",

        "Código Barras",

        "Serial",

        "Nombre",

        "Categoría",

        "Ubicación",

        "Marca",

        "Modelo",

        "Estado",

        "Fecha Ingreso"

    ])

    for activo in activos:

        ws.append([

            activo.codigo,

            activo.codigo_barras,

            activo.serial,

            activo.nombre,

            activo.categoria.nombre if activo.categoria else "",

            activo.ubicacion.nombre if activo.ubicacion else "",

            activo.marca,

            activo.modelo,

            activo.estado,

            str(activo.fecha_ingreso)

        ])

    archivo = BytesIO()

    wb.save(archivo)

    archivo.seek(0)

    return StreamingResponse(

        archivo,

        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",

        headers={

            "Content-Disposition":

            "attachment; filename=Inventario_Completo.xlsx"

        }

    )