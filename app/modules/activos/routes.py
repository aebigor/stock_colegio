from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templates import templates
from app.modules.auth.dependencies import get_current_user, user_area, area_permitida, SUPER_ADMIN_ROLES
from app.modules.auth.models import Usuario
from app.modules.categorias.service import CategoriaService
from app.modules.personas.service import PersonaService
from app.modules.ubicaciones.service import UbicacionService
from .barcode import BarcodeGenerator
from .catalogo_pdf import generar_catalogo_pdf
from .movimiento_service import MovimientoService
from .movimiento_schema import MovimientoCreate
from .qr import QRGenerator
from app.core.config import settings
from .schema import ActivoCreate, ActivoUpdate
from .service import ActivoService

router = APIRouter(prefix="/activos", tags=["Activos"], dependencies=[Depends(get_current_user)])


def _area_filtro(user: Usuario, requested: str | None) -> str:
    own = user_area(user)
    if own != "Todas":
        return own
    return requested if requested in {"Medios", "Logística"} else "Todas"


def _not_found():
    raise HTTPException(status_code=404, detail="Activo no encontrado en tu inventario.")


@router.get("/")
def index(
    request: Request,
    q: str = "",
    categoria_id: str | None = None,
    estado: str = "Todos",
    registro: str = "Todos",
    ubicacion_id: str | None = None,
    area: str | None = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    service = ActivoService(db)
    scope_area = _area_filtro(user, area)
    categoria_id_int = None
    if categoria_id is not None and categoria_id.strip():
        try:
            categoria_id_int = int(categoria_id.strip())
        except ValueError:
            categoria_id_int = None
    if estado not in {"Todos", "Disponible", "Prestado", "Mantenimiento", "Baja"}:
        estado = "Todos"
    if registro not in {"Todos", "Activos", "Inactivos"}:
        registro = "Todos"
    ubicacion_id_int = None
    if ubicacion_id and ubicacion_id.strip():
        try:
            ubicacion_id_int = int(ubicacion_id.strip())
        except ValueError:
            ubicacion_id_int = None
    activos = service.listar(scope_area, q, categoria_id_int, estado, registro, ubicacion_id_int)
    return templates.TemplateResponse(
        request=request,
        name="activos/index.html",
        context={
            "title": "Inventario de activos",
            "activos": activos,
            "disponibles": service.contar_disponibles(scope_area),
            "prestados": service.contar_prestados(scope_area),
            "mantenimiento": service.contar_mantenimiento(scope_area),
            "categorias": CategoriaService(db).listar(estado="Activas"),
            "ubicaciones": UbicacionService(db).listar(scope_area),
            "q": q,
            "categoria_id": categoria_id_int,
            "ubicacion_id": ubicacion_id_int,
            "estado_filtro": estado,
            "registro_filtro": registro,
            "area_filtro": scope_area,
            "puede_ver_areas": user_area(user) == "Todas",
        },
    )


@router.get("/crear")
def crear(request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request,
        name="activos/crear.html",
        context={
            "title": "Nuevo activo",
            "categorias": CategoriaService(db).listar(estado="Activas"),
            "ubicaciones": UbicacionService(db).listar("Todas" if user_area(user) == "Todas" else user_area(user)),
            "area_inicial": "Medios" if user_area(user) == "Todas" else user_area(user),
            "puede_ver_areas": user_area(user) == "Todas",
        },
    )


@router.post("/crear")
def guardar(
    nombre: str = Form(...),
    categoria_id: int = Form(...),
    ubicacion_id: int = Form(...),
    marca: str = Form(""),
    modelo: str = Form(""),
    cantidad: int = Form(1),
    estado: str = Form("Disponible"),
    observaciones: str = Form(""),
    area: str | None = Form(None),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    area_objetivo = area_permitida(user, area)
    if estado not in {"Disponible", "Prestado", "Mantenimiento", "Baja"}:
        raise HTTPException(status_code=400, detail="Estado de activo no válido.")
    datos = ActivoCreate(
        nombre=nombre,
        categoria_id=categoria_id,
        ubicacion_id=ubicacion_id,
        marca=marca,
        modelo=modelo,
        cantidad=cantidad,
        estado=estado,
        observaciones=observaciones,
        area=area_objetivo,
    )
    try:
        ActivoService(db).crear(datos, area=area_objetivo, usuario=user.usuario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url="/activos", status_code=303)



@router.get("/entrega-masiva", response_class=HTMLResponse)
def entrega_masiva(
    request: Request,
    ubicacion_id: int | None = None,
    ubicacion_destino_id: int | None = None,
    operacion: str = "Entrega",
    persona_id: int | None = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    area = user_area(user)
    if operacion not in {"Entrega", "Devolucion"}:
        operacion = "Entrega"

    # En entrega/devolución la ubicación es el punto físico de búsqueda, no el propietario del inventario.
    # Mostrar todas las ubicaciones de la empresa permite a Logística o Medios asumir su custodia al entregar.
    ubicaciones = UbicacionService(db).listar("Todas")
    personas = PersonaService(db).listar()
    activos = []
    ubicacion = None
    ubicacion_destino = None
    persona = None

    if operacion == "Entrega":
        if ubicacion_id:
            ubicacion = UbicacionService(db).obtener(ubicacion_id, "Todas")
            if ubicacion is not None:
                # Buscar por ubicación y empresa; no filtrar por el área anterior del activo.
                activos = ActivoService(db).listar_disponibles_por_ubicacion(ubicacion.id, "Todas")
        if ubicacion_destino_id:
            ubicacion_destino = UbicacionService(db).obtener(ubicacion_destino_id, "Todas")
        if persona_id:
            persona = PersonaService(db).obtener(persona_id)
    else:
        if persona_id:
            persona = PersonaService(db).obtener(persona_id)
            if persona is not None:
                # La devolución anual se hace sobre TODO lo asignado al responsable,
                # aunque temporalmente lo tenga otra persona (ej. un estudiante).
                activos = ActivoService(db).listar_prestados_por_responsable(persona.id, area)

    nombre_usuario = " ".join(
        parte for parte in [getattr(user, "nombre", ""), getattr(user, "apellido", "")] if parte
    ).strip() or user.usuario

    return templates.TemplateResponse(
        request=request,
        name="activos/entrega_masiva.html",
        context={
            "title": "Entrega y devolución masiva",
            "ubicaciones": ubicaciones,
            "personas": personas,
            "activos": activos,
            "ubicacion": ubicacion,
            "ubicacion_destino": ubicacion_destino,
            "ubicacion_destino_id": ubicacion_destino_id,
            "persona": persona,
            "persona_id": persona_id,
            "operacion": operacion,
            "area": area,
            "usuario_actual": nombre_usuario,
            "usuario_actual_area": area if area != "Todas" else "Super Admin",
        },
    )


@router.get("/protocolo-tecnologia", response_class=HTMLResponse)
def protocolo_tecnologia(request: Request, user: Usuario = Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request,
        name="activos/protocolo_tecnologia.html",
        context={"title": "Protocolo para préstamo y uso de dispositivos tecnológicos"},
    )


@router.post("/entrega-masiva")
def guardar_entrega_masiva(
    ubicacion_id: int | None = Form(None),
    ubicacion_destino_id: int | None = Form(None),
    persona_id: int = Form(...),
    activo_ids: list[int] = Form(...),
    firma: str = Form(""),
    operacion: str = Form("Entrega"),
    persona_operacion_id: int | None = Form(None),
    observaciones: str = Form(""),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    if operacion not in {"Entrega", "Devolucion"}:
        raise HTTPException(status_code=400, detail="Operación no válida.")
    if not firma or firma == "data: ," or firma == "data:,":
        raise HTTPException(status_code=400, detail="La firma es obligatoria.")

    area = user_area(user)
    persona = PersonaService(db).obtener(persona_id)
    if persona is None:
        raise HTTPException(status_code=400, detail="La persona responsable no es válida.")

    ubicacion_origen = None
    ubicacion_destino = None
    if operacion == "Entrega":
        if not ubicacion_id:
            raise HTTPException(status_code=400, detail="Debes seleccionar la ubicación de origen.")
        if not ubicacion_destino_id:
            raise HTTPException(status_code=400, detail="Debes seleccionar la ubicación donde quedarán los activos.")
        # Las ubicaciones no se restringen por área: pertenecen a la empresa y
        # el área responsable cambia solo cuando la entrega se confirma.
        ubicacion_origen = UbicacionService(db).obtener(ubicacion_id, "Todas")
        ubicacion_destino = UbicacionService(db).obtener(ubicacion_destino_id, "Todas")
        if ubicacion_origen is None:
            raise HTTPException(status_code=400, detail="La ubicación de origen no es válida.")
        if ubicacion_destino is None:
            raise HTTPException(status_code=400, detail="La ubicación de destino no es válida.")

    persona_operacion = PersonaService(db).obtener(persona_operacion_id) if persona_operacion_id else None
    if persona_operacion_id and persona_operacion is None:
        raise HTTPException(status_code=400, detail="La persona indicada para realizar la operación no es válida.")

    service = ActivoService(db)
    procesados = 0
    nombre_usuario = " ".join(
        parte for parte in [getattr(user, "nombre", ""), getattr(user, "apellido", "")] if parte
    ).strip() or user.usuario

    for activo_id in dict.fromkeys(activo_ids):
        # Un activo puede estar físicamente en esta ubicación aunque su área
        # registrada sea otra. El filtro de empresa sigue activo en SQLAlchemy.
        activo = service.obtener(activo_id, "Todas") if operacion == "Entrega" else service.obtener(activo_id, area)
        if activo is None or not activo.activo:
            continue

        if operacion == "Entrega":
            if activo.estado != "Disponible" or activo.ubicacion_id != ubicacion_origen.id:
                continue
            origen_id = activo.ubicacion_id
            destino_id = ubicacion_destino.id
            nuevo_estado = "Prestado"
            tipo = "Entrega"
            etiqueta_persona = "Entregado por"
            liberar_responsable = False
            persona_movimiento = persona.id
            partes = [
                "Entrega masiva.",
                f"Responsable institucional: {persona.nombre}.",
                f"Ubicación de origen: {ubicacion_origen.nombre}.",
                f"Ubicación destino: {ubicacion_destino.nombre}.",
                f"Registrado por: {nombre_usuario}.",
            ]
        else:
            if activo.estado != "Prestado":
                continue
            responsable_valido = activo.responsable_id == persona.id
            if not responsable_valido:
                ultima_entrega = service.ultima_entrega(activo.id)
                responsable_valido = ultima_entrega is not None and ultima_entrega.persona_id == persona.id
            if not responsable_valido:
                continue
            origen_id = activo.ubicacion_id
            destino_id = activo.ubicacion_id
            nuevo_estado = "Disponible"
            tipo = "Devolucion"
            etiqueta_persona = "Recibido por"
            liberar_responsable = True
            persona_movimiento = persona.id
            partes = [
                "Devolución masiva.",
                f"Responsable que devuelve: {persona.nombre}.",
                f"Ubicación de retorno: {activo.ubicacion.nombre if activo.ubicacion else 'Sin ubicación'}.",
                f"Registrado por: {nombre_usuario}.",
            ]

        if persona_operacion:
            partes.append(f"{etiqueta_persona}: {persona_operacion.nombre}.")
        else:
            partes.append(f"{etiqueta_persona}: {nombre_usuario}.")
        if observaciones.strip():
            partes.append(observaciones.strip())

        datos = MovimientoCreate(
            activo_id=activo.id,
            persona_id=persona_movimiento,
            ubicacion_id=destino_id,
            ubicacion_origen_id=origen_id,
            tipo=tipo,
            estado=nuevo_estado,
            estado_entrega="Recibido y firmado",
            observaciones=" ".join(partes),
            usuario=nombre_usuario,
            firma=firma,
            # En una entrega real, la custodia pasa al área que realiza la operación.
            area=(area if operacion == "Entrega" and area in {"Medios", "Logística"} else activo.area),
            liberar_responsable=liberar_responsable,
        )
        movimiento = MovimientoService(db).crear(
            datos, area=("Todas" if operacion == "Entrega" else area),
            usuario=nombre_usuario, permitir_cambio_area=(operacion == "Entrega"),
        )
        if movimiento:
            procesados += 1

    if not procesados:
        if operacion == "Entrega":
            raise HTTPException(status_code=400, detail="No se encontraron activos disponibles en la ubicación de origen seleccionada.")
        raise HTTPException(status_code=400, detail="No se encontraron activos prestados bajo la responsabilidad de esa persona.")

    if operacion == "Entrega":
        return RedirectResponse(
            url=f"/activos/entrega-masiva?ubicacion_id={ubicacion_origen.id}&ubicacion_destino_id={ubicacion_destino.id}&operacion=Entrega",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/activos/entrega-masiva?persona_id={persona.id}&operacion=Devolucion",
        status_code=303,
    )

@router.get("/{activo_id}/detalle")
def detalle(activo_id: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    activo = ActivoService(db).obtener(activo_id, user_area(user))
    if activo is None:
        _not_found()
    return templates.TemplateResponse(request=request, name="activos/detalle.html", context={"title": "Detalle del activo", "activo": activo})


@router.get("/{activo_id}/editar")
def editar(activo_id: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    service = ActivoService(db)
    activo = service.obtener(activo_id, user_area(user))
    if activo is None:
        _not_found()
    return templates.TemplateResponse(
        request=request,
        name="activos/editar.html",
        context={
            "title": "Editar activo",
            "activo": activo,
            "categorias": service.listar_categorias(),
            "ubicaciones": UbicacionService(db).listar("Todas", include_inactive=True),
            "puede_ver_areas": user_area(user) == "Todas",
        },
    )


@router.post("/{activo_id}/editar")
def actualizar(
    activo_id: int,
    nombre: str = Form(...),
    serial: str = Form(""),
    descripcion: str = Form(""),
    categoria_id: int = Form(...),
    ubicacion_id: int = Form(...),
    marca: str = Form(""),
    modelo: str = Form(""),
    estado: str = Form(...),
    observaciones: str = Form(""),
    area_nueva: str | None = Form(None),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    if estado not in {"Disponible", "Prestado", "Mantenimiento", "Baja"}:
        raise HTTPException(status_code=400, detail="Estado de activo no válido.")
    area = user_area(user)
    service = ActivoService(db)
    existente = service.obtener(activo_id, area)
    if existente is None:
        _not_found()
    target_area = existente.area
    # Solo el Super Admin puede reasignar un registro a otro inventario.
    if user_area(user) == "Todas" and area_nueva in {"Medios", "Logística"}:
        target_area = area_nueva
    datos = ActivoUpdate(
        nombre=nombre,
        serial=serial or None,
        descripcion=descripcion or None,
        categoria_id=categoria_id,
        ubicacion_id=ubicacion_id,
        marca=marca or None,
        modelo=modelo or None,
        estado=estado,
        observaciones=observaciones or None,
        activo=existente.activo,
        area=target_area,
    )
    try:
        actualizado = service.actualizar(activo_id, datos, area=area, usuario=user.usuario)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if actualizado is None:
        _not_found()
    return RedirectResponse(url=f"/activos/{activo_id}/detalle", status_code=303)


@router.post("/{activo_id}/estado")
def cambiar_estado_registro(activo_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    updated = ActivoService(db).cambiar_estado_registro(activo_id, user_area(user), user.usuario)
    if updated is None:
        _not_found()
    return RedirectResponse(url="/activos", status_code=303)


@router.get("/codigos/pdf")
def descargar_todos_los_codigos(
    request: Request,
    area: str | None = None,
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    """Descarga etiquetas PDF QR + barras para todos los activos de las áreas permitidas.

    Incluye estados Disponible, Prestado, Mantenimiento y Baja, así como registros
    desactivados. Los usuarios normales solo pueden exportar su propia área.
    """
    scope_area = _area_filtro(user, area)
    activos = ActivoService(db).listar(
        area=scope_area,
        q=None,
        categoria_id=None,
        estado="Todos",
        registro="Todos",
    )
    base_url = (settings.PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")
    pdf = generar_catalogo_pdf(activos, base_url)
    filename_area = "todas" if scope_area == "Todas" else "logistica" if scope_area == "Logística" else "medios"
    return StreamingResponse(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="etiquetas_qr_barras_{filename_area}.pdf"'},
    )


@router.get("/{activo_id}/barcode")
def descargar_codigo_barras(activo_id: int, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    activo = ActivoService(db).obtener(activo_id, user_area(user))
    if activo is None:
        _not_found()
    pdf = BarcodeGenerator.generar_pdf(activo.codigo_barras)
    return StreamingResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{activo.codigo_barras}.pdf"'})


@router.get("/{activo_id}/qr")
def descargar_qr(activo_id: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    activo = ActivoService(db).obtener(activo_id, user_area(user))
    if activo is None:
        _not_found()
    base_url = (settings.PUBLIC_BASE_URL or str(request.base_url)).rstrip("/")
    pdf = QRGenerator.generar_pdf(activo, base_url=base_url)
    return StreamingResponse(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{activo.codigo_barras}_QR.pdf"'})


@router.get("/{activo_id}/movimiento", response_class=HTMLResponse)
def movimiento(activo_id: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    activo = ActivoService(db).obtener(activo_id, user_area(user))
    if activo is None:
        _not_found()
    requiere_protocolo = bool(getattr(activo.categoria, "requiere_protocolo", False))
    return templates.TemplateResponse(
        request=request,
        name="activos/movimiento.html",
        context={
            "title": "Registrar movimiento",
            "activo": activo,
            "personas": PersonaService(db).listar(),
            "ubicaciones": UbicacionService(db).listar(activo.area),
            "requiere_protocolo": requiere_protocolo,
        },
    )


@router.post("/{activo_id}/movimiento")
def guardar_movimiento(
    activo_id: int,
    persona_id: int | None = Form(None),
    ubicacion_id: int | None = Form(None),
    tipo: str = Form(...),
    observaciones: str = Form(""),
    firma: str = Form(""),
    acepto_protocolo: str | None = Form(None),
    db: Session = Depends(get_db),
    user: Usuario = Depends(get_current_user),
):
    estados = {"Entrega": "Prestado", "Mantenimiento": "Mantenimiento", "Baja": "Baja", "Devolución": "Disponible", "Devolucion": "Disponible", "Ajuste": "Disponible", "Disponible": "Disponible", "Ingreso a bodega": "Disponible", "Salida Mantenimiento": "Disponible"}
    if tipo not in estados:
        raise HTTPException(status_code=400, detail="Tipo de movimiento no válido.")
    if tipo == "Entrega" and not ubicacion_id:
        raise HTTPException(status_code=400, detail="Para una entrega debes indicar la ubicación donde quedará el activo.")
    activo = ActivoService(db).obtener(activo_id, user_area(user))
    if activo is None:
        _not_found()

    requiere_protocolo = bool(getattr(activo.categoria, "requiere_protocolo", False))
    protocolo_aceptado = False
    if tipo == "Entrega" and requiere_protocolo:
        if acepto_protocolo != "on":
            raise HTTPException(
                status_code=400,
                detail="Debes leer y aceptar el protocolo tecnológico antes de registrar la entrega.",
            )
        if not firma or firma == "data:,":
            raise HTTPException(
                status_code=400,
                detail="La firma de quien recibe el dispositivo es obligatoria para esta entrega.",
            )
        protocolo_aceptado = True

    datos = MovimientoCreate(
        activo_id=activo_id,
        persona_id=persona_id,
        ubicacion_id=ubicacion_id,
        tipo=tipo,
        estado=estados[tipo],
        observaciones=observaciones,
        usuario=user.usuario,
        firma=firma or None,
        protocolo_aceptado=protocolo_aceptado,
        estado_entrega="Protocolo aceptado y firmado" if protocolo_aceptado else None,
        area=user_area(user) if user_area(user) != "Todas" else activo.area,
    )
    movimiento = MovimientoService(db).crear(datos, area=user_area(user), usuario=user.usuario)
    if movimiento is None:
        _not_found()
    return RedirectResponse(url=f"/activos/{activo_id}/historial", status_code=303)


@router.get("/{activo_id}/historial", response_class=HTMLResponse)
def historial(activo_id: int, request: Request, db: Session = Depends(get_db), user: Usuario = Depends(get_current_user)):
    area = user_area(user)
    activo = ActivoService(db).obtener(activo_id, area)
    if activo is None:
        _not_found()
    movimientos = MovimientoService(db).listar_por_activo(activo_id, area)
    return templates.TemplateResponse(request=request, name="activos/historial.html", context={"title": "Historial del activo", "activo": activo, "historial": movimientos, "es_super_admin": bool(user.rol and user.rol.nombre in SUPER_ADMIN_ROLES)})
