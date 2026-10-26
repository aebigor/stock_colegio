from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates
from app.modules.auth.dependencies import get_current_user, user_area
from app.modules.auth.models import Usuario
from .service import ReporteService

router = APIRouter(prefix="/reportes", tags=["Reportes"], dependencies=[Depends(get_current_user)])


def _scope(user: Usuario, area: str | None) -> str:
    own = user_area(user)
    if own != "Todas":
        return own
    return area if area in {"Medios", "Logística"} else "Todas"


@router.get("/", response_class=HTMLResponse)
def index(request: Request, area: str | None = None, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    scope_area = _scope(user, area)
    service = ReporteService(db, scope_area)
    return templates.TemplateResponse(
        request=request,
        name="reportes/index.html",
        context={
            "title": "Reportes de inventario",
            "total": service.total_activos(),
            "disponibles": service.disponibles(),
            "prestados": service.prestados(),
            "mantenimiento": service.mantenimiento(),
            "baja": service.baja(),
            "categorias": service.categorias(),
            "activos_mantenimiento": service.activos_mantenimiento(),
            "cambios_recientes": service.cambios_recientes(),
            "area_filtro": scope_area,
            "puede_ver_areas": user_area(user) == "Todas",
        },
    )


@router.get("/excel")
def exportar_excel(area: str | None = None, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    scope_area = _scope(user, area)
    activos = ReporteService(db, scope_area).exportar_inventario()
    wb = Workbook()
    ws = wb.active
    ws.title = "Inventario"
    ws.append(["Área", "Código", "Código barras", "Serial", "Nombre", "Categoría", "Ubicación", "Marca", "Modelo", "Estado", "Registro activo", "Fecha ingreso"])
    for activo in activos:
        ws.append([
            activo.area, activo.codigo, activo.codigo_barras, activo.serial, activo.nombre,
            activo.categoria.nombre if activo.categoria else "",
            activo.ubicacion.nombre if activo.ubicacion else "",
            activo.marca, activo.modelo, activo.estado,
            "Sí" if activo.activo else "No", str(activo.fecha_ingreso or ""),
        ])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for column in ws.columns:
        width = max(len(str(cell.value or "")) for cell in column) + 2
        ws.column_dimensions[column[0].column_letter].width = min(width, 35)
    archivo = BytesIO()
    wb.save(archivo)
    archivo.seek(0)
    nombre_area = {"Todas": "General", "Medios": "Medios", "Logística": "Logistica"}.get(scope_area, "General")
    filename = f"Inventario_{nombre_area}.xlsx"
    return StreamingResponse(archivo, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
