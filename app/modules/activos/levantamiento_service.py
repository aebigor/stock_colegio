from datetime import datetime, timezone
from secrets import token_urlsafe
import re
import unicodedata
from sqlalchemy.orm import Session, joinedload
from .levantamiento_model import LevantamientoInventario, LevantamientoDetalle
from .model import Activo
from .movimiento_model import Movimiento
from app.modules.categorias.model import Categoria
from app.modules.personas.model import Persona
from app.modules.ubicaciones.model import Ubicacion


def cantidad_entregada_detalle(detalle):
    """Cantidad que salió al responsable según el detalle aprobado.

    Un detalle de activo existente representa como máximo una unidad; un hallazgo
    nuevo puede representar varias unidades registradas en cantidad_encontrada.
    """
    # Las altas capturadas por Logística no se entregan al docente y, por tanto,
    # nunca deben entrar en el cálculo de préstamos/devoluciones del levantamiento.
    if getattr(detalle, "alta_logistica", False):
        return 0
    cantidad = max(0, int(detalle.cantidad_encontrada or 0))
    if detalle.es_nuevo:
        return cantidad
    return 1 if detalle.activo_id and cantidad > 0 else 0


def cantidad_devuelta_detalle(detalle):
    """Unidades del lote original que ya regresaron a bodega."""
    entregada = cantidad_entregada_detalle(detalle)
    if detalle.cantidad_devuelta is None:
        return entregada
    return max(0, min(entregada, int(detalle.cantidad_devuelta or 0)))


def cantidad_sobrante_detalle(detalle):
    """Unidades adicionales halladas, separadas de las unidades originalmente entregadas."""
    return max(0, int(getattr(detalle, "cantidad_sobrante", 0) or 0))


def calcular_diferencias_cantidad(entregadas, cantidad_actual):
    """Devuelve (originales_recibidas, nuevas, faltantes) para el conteo final."""
    entregadas = max(0, int(entregadas or 0))
    cantidad_actual = max(0, int(cantidad_actual or 0))
    originales_recibidas = min(entregadas, cantidad_actual)
    nuevas = max(0, cantidad_actual - entregadas)
    faltantes = max(0, entregadas - cantidad_actual)
    return originales_recibidas, nuevas, faltantes


def cantidad_total_encontrada_devolucion(detalle):
    return cantidad_devuelta_detalle(detalle) + cantidad_sobrante_detalle(detalle)


def estado_inventario_para_alta(estado_fisico):
    """Mapea la condición física del artículo nuevo al estado del inventario."""
    estado = (estado_fisico or "Bueno").strip().casefold()
    return "Mantenimiento" if estado in {"malo", "mantenimiento"} else "Disponible"


def _normalizar_grupo_detalle(detalle):
    def normalizar(valor):
        texto = unicodedata.normalize("NFD", str(valor or "").strip().casefold())
        texto = "".join(caracter for caracter in texto if unicodedata.category(caracter) != "Mn")
        return re.sub(r"[^a-z0-9]+", "", texto)

    if detalle.serial:
        return ("individual", detalle.id)
    return (
        "grupo",
        normalizar(detalle.nombre),
        detalle.categoria_id or 0,
        normalizar(detalle.marca),
        normalizar(detalle.modelo),
        bool(detalle.es_nuevo),
        (detalle.estado_fisico or "").strip().casefold(),
        (detalle.observacion or "").strip().casefold(),
    )


class LevantamientoService:
    def __init__(self, db: Session):
        self.db = db

    def listar(self, area="Todas"):
        q = self.db.query(LevantamientoInventario).options(
            joinedload(LevantamientoInventario.ubicacion),
            joinedload(LevantamientoInventario.responsable),
            joinedload(LevantamientoInventario.creador),
            joinedload(LevantamientoInventario.aprobador),
        )
        if area != "Todas":
            q = q.filter(LevantamientoInventario.area == area)
        return q.order_by(LevantamientoInventario.created_at.desc(), LevantamientoInventario.id.desc()).all()

    def obtener(self, levantamiento_id, area="Todas"):
        q = self.db.query(LevantamientoInventario).options(
            joinedload(LevantamientoInventario.ubicacion),
            joinedload(LevantamientoInventario.responsable),
            joinedload(LevantamientoInventario.creador),
            joinedload(LevantamientoInventario.aprobador),
            joinedload(LevantamientoInventario.detalles).joinedload(LevantamientoDetalle.activo),
            joinedload(LevantamientoInventario.detalles).joinedload(LevantamientoDetalle.categoria),
        ).filter(LevantamientoInventario.id == levantamiento_id)
        if area != "Todas":
            q = q.filter(LevantamientoInventario.area == area)
        return q.first()

    def crear_borrador(self, ubicacion_id, responsable_id, area, usuario_id):
        # Evitar una segunda entrega activa al mismo docente en la misma ubicación.
        # Cuando el levantamiento anterior figure como Devuelto, se permite crear otro.
        if responsable_id:
            entrega_activa = self.db.query(LevantamientoInventario).filter(
                LevantamientoInventario.ubicacion_id == ubicacion_id,
                LevantamientoInventario.responsable_id == responsable_id,
                LevantamientoInventario.estado.in_(["Borrador", "Pendiente de aprobación", "Aprobado", "Devuelto parcialmente"]),
            ).first()
            if entrega_activa:
                raise ValueError(
                    f"Este docente ya tiene un levantamiento activo (#{entrega_activa.id}, estado: {entrega_activa.estado}). "
                    "Abre ese proceso y termínalo o registra la devolución si ya recibió los activos antes de crear otro levantamiento para esta ubicación."
                )
        # El área del inventario depende del usuario que crea el levantamiento
        # (Logística/Medios), no del campo descriptivo de la ubicación (p. ej. General).
        ubicacion = self.db.query(Ubicacion).filter(Ubicacion.id == ubicacion_id).first()
        if not ubicacion:
            raise ValueError("La ubicación seleccionada no es válida.")
        responsable = self.db.query(Persona).filter(Persona.id == responsable_id).first() if responsable_id else None
        levantamiento = LevantamientoInventario(
            ubicacion_id=ubicacion.id,
            responsable_id=responsable.id if responsable else None,
            estado="Borrador",
            creado_por=usuario_id,
            area=area if area != "Todas" else "Medios",
            public_token=token_urlsafe(48),
        )
        self.db.add(levantamiento)
        self.db.flush()
        activos_q = self.db.query(Activo).filter(
            Activo.ubicacion_id == ubicacion.id,
            Activo.activo.is_(True),
        )
        # La ubicación seleccionada define qué activos se revisan físicamente.
        # No filtrar por Activo.area: un equipo puede estar en Robótica y tener
        # un área histórica General/Medios. El área responsable del levantamiento
        # se conserva en lev.area y se aplica al aprobar, no al descubrir los activos.
        activos = activos_q.order_by(Activo.nombre, Activo.id).all()
        for activo in activos:
            self.db.add(LevantamientoDetalle(
                empresa_id=ubicacion.empresa_id,
                levantamiento_id=levantamiento.id,
                activo_id=activo.id,
                categoria_id=activo.categoria_id,
                nombre=activo.nombre,
                referencia=activo.codigo_barras or activo.codigo,
                serial=activo.serial,
                marca=activo.marca,
                modelo=activo.modelo,
                cantidad_sistema=1,
                cantidad_encontrada=1 if activo.estado != "Baja" else 0,
                estado_fisico="Bueno" if activo.estado not in {"Mantenimiento", "Baja"} else activo.estado,
                es_nuevo=False,
            ))
        self.db.commit()
        return levantamiento

    def obtener_por_token(self, token):
        return self.db.query(LevantamientoInventario).options(
            joinedload(LevantamientoInventario.ubicacion),
            joinedload(LevantamientoInventario.responsable),
            joinedload(LevantamientoInventario.creador),
            joinedload(LevantamientoInventario.aprobador),
            joinedload(LevantamientoInventario.detalles).joinedload(LevantamientoDetalle.activo),
            joinedload(LevantamientoInventario.detalles).joinedload(LevantamientoDetalle.categoria),
        ).filter(LevantamientoInventario.public_token == token).first()

    def actualizar_detalle_publico(self, token, detalle_id, cantidad_encontrada, estado_fisico, observacion):
        lev = self.obtener_por_token(token)
        if not lev or lev.estado != "Borrador":
            raise ValueError("Este enlace ya no está disponible para edición.")
        detalle = next((d for d in lev.detalles if d.id == detalle_id), None)
        if detalle is None:
            raise ValueError("El elemento no pertenece a este levantamiento.")
        detalle.cantidad_encontrada = max(0, int(cantidad_encontrada))
        detalle.estado_fisico = estado_fisico.strip() or "Bueno"
        detalle.observacion = observacion.strip() or None
        self.db.commit()
        return lev

    def agregar_hallazgo_publico(self, token, nombre, categoria_id, cantidad, estado_fisico, observacion, referencia="", marca="", modelo="", serial=""):
        lev = self.obtener_por_token(token)
        if not lev or lev.estado != "Borrador":
            raise ValueError("Este enlace ya no está disponible para edición.")
        # El enlace público solo puede usar categorías de la misma empresa.
        categoria = self.db.query(Categoria).filter(Categoria.id == categoria_id, Categoria.activo.is_(True)).first()
        if not categoria or categoria.empresa_id != lev.empresa_id:
            raise ValueError("La categoría seleccionada no es válida.")
        if cantidad < 1 or cantidad > 500:
            raise ValueError("La cantidad debe estar entre 1 y 500.")
        detalle = LevantamientoDetalle(
            empresa_id=lev.empresa_id, levantamiento_id=lev.id, categoria_id=categoria.id,
            nombre=nombre.strip(), referencia=referencia.strip() or None, serial=serial.strip() or None,
            marca=marca.strip() or None, modelo=modelo.strip() or None, cantidad_sistema=0,
            cantidad_encontrada=cantidad, estado_fisico=estado_fisico.strip() or "Bueno",
            observacion=observacion.strip() or None, es_nuevo=True,
        )
        self.db.add(detalle)
        self.db.commit()
        self.db.refresh(detalle)
        return detalle

    def verificar_detalle(self, detalle_id, usuario):
        detalle = self.db.query(LevantamientoDetalle).join(LevantamientoInventario).filter(LevantamientoDetalle.id == detalle_id).first()
        if not detalle or detalle.levantamiento.estado != "Pendiente de aprobación":
            raise ValueError("Este elemento no está pendiente de revisión.")
        detalle.verificado_logistica = True
        detalle.revisado_por = usuario
        detalle.revisado_at = datetime.now(timezone.utc)
        self.db.commit()
        return detalle

    def desverificar_detalle(self, detalle_id):
        detalle = self.db.query(LevantamientoDetalle).join(LevantamientoInventario).filter(LevantamientoDetalle.id == detalle_id).first()
        if not detalle or detalle.levantamiento.estado != "Pendiente de aprobación":
            raise ValueError("Este elemento no está pendiente de revisión.")
        detalle.verificado_logistica = False
        detalle.revisado_por = None
        detalle.revisado_at = None
        self.db.commit()
        return detalle

    def agregar_existente(self, levantamiento_id, activo, cantidad_encontrada=1, estado_fisico="Bueno", observacion=""):
        lev = self.db.query(LevantamientoInventario).filter(LevantamientoInventario.id == levantamiento_id).first()
        if not lev or lev.estado != "Borrador":
            raise ValueError("El levantamiento no está abierto para edición.")
        detalle = LevantamientoDetalle(
            empresa_id=lev.empresa_id,
            levantamiento_id=lev.id,
            activo_id=activo.id,
            categoria_id=activo.categoria_id,
            nombre=activo.nombre,
            referencia=activo.codigo_barras or activo.codigo,
            serial=activo.serial,
            marca=activo.marca,
            modelo=activo.modelo,
            cantidad_sistema=1,
            cantidad_encontrada=max(0, int(cantidad_encontrada)),
            estado_fisico=estado_fisico,
            observacion=observacion.strip() or None,
            es_nuevo=False,
        )
        self.db.add(detalle)
        self.db.commit()
        return detalle

    def agregar_hallazgo(self, levantamiento_id, nombre, categoria_id, cantidad, estado_fisico, observacion, referencia="", marca="", modelo="", serial=""):
        lev = self.db.query(LevantamientoInventario).filter(LevantamientoInventario.id == levantamiento_id).first()
        if not lev or lev.estado != "Borrador":
            raise ValueError("El levantamiento no está abierto para edición.")
        categoria = self.db.query(Categoria).filter(Categoria.id == categoria_id, Categoria.activo.is_(True)).first()
        if not categoria:
            raise ValueError("La categoría seleccionada no es válida.")
        if cantidad < 1 or cantidad > 500:
            raise ValueError("La cantidad debe estar entre 1 y 500.")
        detalle = LevantamientoDetalle(
            empresa_id=lev.empresa_id,
            levantamiento_id=lev.id,
            categoria_id=categoria.id,
            nombre=nombre.strip(),
            referencia=referencia.strip() or None,
            serial=serial.strip() or None,
            marca=marca.strip() or None,
            modelo=modelo.strip() or None,
            cantidad_sistema=0,
            cantidad_encontrada=cantidad,
            estado_fisico=estado_fisico,
            observacion=observacion.strip() or None,
            es_nuevo=True,
        )
        self.db.add(detalle)
        self.db.commit()
        self.db.refresh(detalle)
        return detalle

    def agregar_alta_logistica(
        self, levantamiento_id, usuario_nombre, nombre, categoria_id, cantidad,
        estado_fisico="Bueno", referencia="", marca="", modelo="", serial="",
        descripcion="", observacion="",
    ):
        """Agrega artículos recién ingresados desde la revisión de Logística.

        Se guardan como detalles pendientes de aprobación; al aprobar el
        levantamiento se crean como activos disponibles en la ubicación revisada.
        """
        lev = self.db.query(LevantamientoInventario).filter(
            LevantamientoInventario.id == levantamiento_id
        ).first()
        if not lev or lev.estado != "Pendiente de aprobación":
            raise ValueError("Solo puedes agregar artículos nuevos durante una revisión pendiente de Logística.")

        nombre = (nombre or "").strip()
        if not nombre:
            raise ValueError("El nombre del artículo es obligatorio.")
        if len(nombre) > 150:
            raise ValueError("El nombre no puede superar 150 caracteres.")
        cantidad = int(cantidad or 0)
        if cantidad < 1 or cantidad > 500:
            raise ValueError("La cantidad debe estar entre 1 y 500.")

        referencia = (referencia or "").strip()
        marca = (marca or "").strip()
        modelo = (modelo or "").strip()
        serial = (serial or "").strip()
        descripcion = (descripcion or "").strip()
        observacion = (observacion or "").strip()
        estado_fisico = (estado_fisico or "Bueno").strip()
        if serial and cantidad > 1:
            raise ValueError("Si registras un serial individual, la cantidad debe ser 1. Para varios artículos, registra cada serial por separado.")

        categoria = self.db.query(Categoria).filter(
            Categoria.id == categoria_id,
            Categoria.activo.is_(True),
            Categoria.empresa_id == lev.empresa_id,
        ).first()
        if not categoria:
            raise ValueError("La categoría seleccionada no pertenece a esta empresa o está inactiva.")

        # Evita duplicar la misma línea si el usuario reenvía el formulario.
        repetido = self.db.query(LevantamientoDetalle).filter(
            LevantamientoDetalle.empresa_id == lev.empresa_id,
            LevantamientoDetalle.levantamiento_id == lev.id,
            LevantamientoDetalle.alta_logistica.is_(True),
            LevantamientoDetalle.categoria_id == categoria.id,
            LevantamientoDetalle.nombre == nombre,
            LevantamientoDetalle.marca == (marca or None),
            LevantamientoDetalle.modelo == (modelo or None),
            LevantamientoDetalle.serial == (serial or None),
            LevantamientoDetalle.referencia == (referencia or None),
            LevantamientoDetalle.cantidad_encontrada == cantidad,
        ).first()
        if repetido:
            raise ValueError("Este mismo artículo ya fue agregado a la revisión. Cambia la marca, referencia o cantidad si es otro registro.")

        detalle = LevantamientoDetalle(
            empresa_id=lev.empresa_id,
            levantamiento_id=lev.id,
            activo_id=None,
            categoria_id=categoria.id,
            nombre=nombre,
            referencia=referencia or None,
            serial=serial or None,
            marca=marca or None,
            modelo=modelo or None,
            descripcion=descripcion or None,
            cantidad_sistema=0,
            cantidad_encontrada=cantidad,
            estado_fisico=estado_fisico,
            observacion=observacion or None,
            es_nuevo=True,
            alta_logistica=True,
            verificado_logistica=True,
            revisado_por=usuario_nombre,
            revisado_at=datetime.now(timezone.utc),
        )
        self.db.add(detalle)
        self.db.commit()
        self.db.refresh(detalle)
        return detalle

    def actualizar_detalle(self, detalle_id, cantidad_encontrada, estado_fisico, observacion):
        d = self.db.query(LevantamientoDetalle).join(LevantamientoInventario).filter(LevantamientoDetalle.id == detalle_id).first()
        if not d or d.levantamiento.estado != "Borrador":
            raise ValueError("Este levantamiento ya está cerrado.")
        d.cantidad_encontrada = max(0, int(cantidad_encontrada))
        d.estado_fisico = estado_fisico
        d.observacion = observacion.strip() or None
        self.db.commit()

    def eliminar(self, levantamiento_id):
        """Elimina un levantamiento de prueba mientras siga en Borrador.

        Los detalles se eliminan en cascada; no se toca ningún Activo ni
        Movimiento porque durante el borrador todavía no se han incorporado
        al inventario maestro.
        """
        lev = self.db.query(LevantamientoInventario).filter(
            LevantamientoInventario.id == levantamiento_id
        ).first()
        if not lev:
            raise ValueError("Levantamiento no encontrado.")
        if lev.estado != "Borrador":
            raise ValueError("Solo se pueden eliminar levantamientos en Borrador.")
        self.db.delete(lev)
        self.db.commit()

    def enviar(self, levantamiento_id, firma=""):
        lev = self.db.query(LevantamientoInventario).filter(LevantamientoInventario.id == levantamiento_id).first()
        if not lev or lev.estado != "Borrador":
            raise ValueError("El levantamiento no está disponible para enviar.")
        if not lev.detalles:
            raise ValueError("El levantamiento no tiene elementos para revisar.")
        if not firma or firma in {"data: ,", "data:,"}:
            raise ValueError("El docente debe firmar el levantamiento antes de enviarlo.")
        lev.firma = firma
        for d in lev.detalles:
            if d.es_nuevo and not d.categoria_id:
                raise ValueError(f"El hallazgo '{d.nombre}' necesita una categoría antes de enviarse.")
        lev.estado = "Pendiente de aprobación"
        lev.enviado_at = datetime.now(timezone.utc)
        self.db.commit()

    def aprobar(self, levantamiento_id, usuario_id, usuario_nombre):
        lev = self.db.query(LevantamientoInventario).options(
            joinedload(LevantamientoInventario.detalles)
        ).filter(LevantamientoInventario.id == levantamiento_id).first()
        if not lev or lev.estado != "Pendiente de aprobación":
            raise ValueError("Solo se pueden aprobar levantamientos pendientes.")
        if not lev.detalles:
            raise ValueError("El levantamiento no tiene elementos para aprobar.")
        if not lev.responsable_id:
            raise ValueError("El levantamiento debe tener un docente/responsable antes de aprobarse.")
        pendientes = [d for d in lev.detalles if not d.verificado_logistica]
        if pendientes:
            raise ValueError(f"Faltan {len(pendientes)} elemento(s) por verificar en la revisión de Logística.")

        responsable = self.db.query(Persona).filter(Persona.id == lev.responsable_id).first()
        if not responsable:
            raise ValueError("El responsable del levantamiento ya no existe.")

        creados = 0
        entregados = 0
        for d in lev.detalles:
            # Si el docente encontró el activo, la aprobación de Logística se
            # convierte automáticamente en la entrega al responsable. No se
            # obliga a pasar por Entrega Masiva nuevamente.
            cantidad = max(0, int(d.cantidad_encontrada or 0))
            if cantidad <= 0:
                continue

            if not d.es_nuevo and d.activo_id:
                activo = self.db.query(Activo).filter(Activo.id == d.activo_id).first()
                if not activo:
                    continue
                activo.responsable_id = lev.responsable_id
                activo.tenedor_id = lev.responsable_id
                activo.estado = "Prestado"
                # La ubicación del levantamiento sigue siendo la ubicación
                # registrada del activo. La custodia queda en el docente.
                activo.ubicacion_id = lev.ubicacion_id
                # Un levantamiento no debe sobrescribir las observaciones históricas del activo.
                # El estado físico y la observación del docente quedan en el detalle y movimiento.
                activo.area = lev.area
                self.db.add(Movimiento(
                    empresa_id=lev.empresa_id,
                    activo_id=activo.id,
                    persona_id=lev.responsable_id,
                    ubicacion_id=lev.ubicacion_id,
                    ubicacion_origen_id=lev.ubicacion_id,
                    tipo="Entrega",
                    estado="Prestado",
                    estado_entrega="Entregado mediante inventario físico",
                    observaciones=(
                        f"Entrega automática por aprobación del levantamiento físico #{lev.id}. "
                        f"detalle_fisico_id={d.id}. "
                        f"Responsable: {responsable.nombre}. "
                        f"Verificado por Logística: {usuario_nombre}."
                        + (f" Observación del docente: {d.observacion}" if d.observacion else "")
                    ),
                    usuario=usuario_nombre,
                    firma=lev.firma,
                    area=activo.area,
                    protocolo_aceptado=False,
                ))
                entregados += 1
                continue

            if d.es_nuevo and getattr(d, "alta_logistica", False) and d.cantidad_encontrada > 0 and d.activo_id is None:
                categoria = self.db.query(Categoria).filter(
                    Categoria.id == d.categoria_id,
                    Categoria.empresa_id == lev.empresa_id,
                    Categoria.activo.is_(True),
                ).first()
                if not categoria:
                    raise ValueError(f"El artículo nuevo '{d.nombre}' no tiene una categoría válida de esta empresa.")

                marcador = f"alta_logistica_levantamiento={lev.id}_detalle={d.id}"
                movimientos_previos = self.db.query(Movimiento).filter(
                    Movimiento.empresa_id == lev.empresa_id,
                    Movimiento.tipo == "Alta nuevo artículo",
                    Movimiento.observaciones.ilike(f"%{marcador}%"),
                ).all()
                creados_previos = {m.activo_id for m in movimientos_previos if m.activo_id}
                if len(creados_previos) > int(d.cantidad_encontrada or 0):
                    raise ValueError(f"El artículo '{d.nombre}' ya tiene más unidades creadas que las registradas.")

                prefijo = (categoria.prefijo or "ACT").strip().upper()[:10] or "ACT"
                ultimo = self.db.query(Activo.id).order_by(Activo.id.desc()).first()
                siguiente = (ultimo[0] if ultimo else 0) + 1
                restantes = int(d.cantidad_encontrada or 0) - len(creados_previos)
                estado_nuevo = estado_inventario_para_alta(d.estado_fisico)
                for unidad in range(restantes):
                    while True:
                        codigo = f"{prefijo}{siguiente:06d}"
                        codigo_barras = f"TEC-GLS-{siguiente:06d}"
                        existe = self.db.query(Activo.id).filter(
                            Activo.empresa_id == lev.empresa_id,
                            (Activo.codigo == codigo) | (Activo.codigo_barras == codigo_barras),
                        ).first()
                        if not existe:
                            break
                        siguiente += 1

                    descripcion_partes = []
                    if (d.descripcion or "").strip():
                        descripcion_partes.append(d.descripcion.strip())
                    if (d.referencia or "").strip():
                        descripcion_partes.append(f"Referencia de fabricante/proveedor: {d.referencia.strip()}")
                    if (d.observacion or "").strip():
                        descripcion_partes.append(f"Observación de ingreso: {d.observacion.strip()}")
                    activo_nuevo = Activo(
                        empresa_id=lev.empresa_id,
                        codigo=codigo,
                        codigo_barras=codigo_barras,
                        serial=d.serial if int(d.cantidad_encontrada or 0) == 1 else None,
                        nombre=d.nombre,
                        descripcion="\n".join(descripcion_partes) or None,
                        categoria_id=categoria.id,
                        ubicacion_id=lev.ubicacion_id,
                        marca=d.marca,
                        modelo=d.modelo,
                        estado=estado_nuevo,
                        responsable_id=None,
                        tenedor_id=None,
                        qr=codigo_barras,
                        observaciones=(d.observacion or "").strip() or None,
                        area=lev.area,
                        activo=True,
                    )
                    self.db.add(activo_nuevo)
                    self.db.flush()
                    self.db.add(Movimiento(
                        empresa_id=lev.empresa_id,
                        activo_id=activo_nuevo.id,
                        persona_id=None,
                        ubicacion_id=lev.ubicacion_id,
                        ubicacion_origen_id=lev.ubicacion_id,
                        tipo="Alta nuevo artículo",
                        estado=estado_nuevo,
                        estado_entrega="Ingreso nuevo a inventario desde revisión logística",
                        observaciones=(
                            f"{marcador}; unidad={len(creados_previos) + unidad + 1}; "
                            f"cantidad_registrada={d.cantidad_encontrada}; "
                            f"levantamiento={lev.id}; detalle_fisico_id={d.id}. "
                            + (f"Referencia: {d.referencia}. " if d.referencia else "")
                            + (f"Descripción: {d.descripcion}. " if d.descripcion else "")
                            + (f"Observación: {d.observacion}. " if d.observacion else "")
                            + f"Estado físico: {d.estado_fisico}. Registrado y aprobado por {usuario_nombre}."
                        ),
                        usuario=usuario_nombre,
                        area=lev.area,
                    ))
                    creados += 1
                    siguiente += 1
                # Estas altas no se asignan al docente ni se incluyen en la devolución.
                continue

            if d.es_nuevo and d.cantidad_encontrada > 0 and d.activo_id is None:
                categoria = self.db.query(Categoria).filter(Categoria.id == d.categoria_id).first()
                if not categoria:
                    raise ValueError(f"El hallazgo '{d.nombre}' no tiene una categoría válida.")
                for _ in range(d.cantidad_encontrada):
                    ultimo = self.db.query(Activo.id).order_by(Activo.id.desc()).first()
                    siguiente = (ultimo[0] if ultimo else 0) + 1
                    codigo = f"{categoria.prefijo.upper()}{siguiente:06d}"
                    codigo_barras = f"TEC-GLS-{siguiente:06d}"
                    activo = Activo(
                        empresa_id=lev.empresa_id,
                        codigo=codigo,
                        codigo_barras=codigo_barras,
                        serial=d.serial,
                        nombre=d.nombre,
                        categoria_id=categoria.id,
                        ubicacion_id=lev.ubicacion_id,
                        marca=d.marca,
                        modelo=d.modelo,
                        estado="Prestado",
                        responsable_id=lev.responsable_id,
                        tenedor_id=lev.responsable_id,
                        qr=codigo_barras,
                        observaciones=(d.observacion or "").strip() or None,
                        area=lev.area,
                        activo=True,
                    )
                    self.db.add(activo)
                    self.db.flush()
                    self.db.add(Movimiento(
                        empresa_id=lev.empresa_id,
                        activo_id=activo.id,
                        persona_id=lev.responsable_id,
                        ubicacion_id=lev.ubicacion_id,
                        ubicacion_origen_id=lev.ubicacion_id,
                        tipo="Entrega",
                        estado="Prestado",
                        estado_entrega="Activo nuevo entregado mediante inventario físico",
                        observaciones=(
                            f"Hallazgo nuevo incorporado y entregado automáticamente al aprobar el levantamiento físico #{lev.id}. "
                            f"detalle_fisico_id={d.id}. "
                            f"Responsable: {responsable.nombre}. "
                            f"Aprobado por: {usuario_nombre}."
                            + (f" Observación del docente: {d.observacion}" if d.observacion else "")
                        ),
                        usuario=usuario_nombre,
                        firma=lev.firma,
                        area=lev.area,
                    ))
                    creados += 1
                    entregados += 1
                # No modificar d.observacion: es exactamente lo que escribió el docente.

        lev.estado = "Aprobado"
        lev.aprobado_por = usuario_id
        lev.aprobado_at = datetime.now(timezone.utc)
        self.db.commit()
        return {"creados": creados, "entregados": entregados}

    def devolver_todo(self, levantamiento_id, usuario):
        lev = self.db.query(LevantamientoInventario).options(
            joinedload(LevantamientoInventario.detalles)
        ).filter(LevantamientoInventario.id == levantamiento_id).first()
        if not lev or lev.estado not in {"Aprobado", "Devuelto parcialmente"}:
            raise ValueError("Solo se puede registrar la devolución de un levantamiento aprobado o con devolución parcial.")
        if not lev.responsable_id:
            raise ValueError("El levantamiento no tiene responsable.")

        pendientes_revision = [d for d in lev.detalles if not getattr(d, "alta_logistica", False) and not getattr(d, "revisado_devolucion", False)]
        if pendientes_revision:
            raise ValueError(
                "Debes guardar la cantidad y observación de todos los grupos antes de registrar la devolución. "
                f"Quedan {len(pendientes_revision)} grupo(s) por revisar."
            )

        from sqlalchemy import or_
        movimientos_entrega = (
            self.db.query(Movimiento)
            .filter(
                Movimiento.empresa_id == lev.empresa_id,
                Movimiento.tipo == "Entrega",
                Movimiento.persona_id == lev.responsable_id,
                or_(
                    Movimiento.observaciones.ilike(f"%levantamiento físico #{lev.id}%"),
                    Movimiento.observaciones.ilike(f"%levantamiento #{lev.id}%"),
                ),
            )
            .order_by(Movimiento.activo_id.asc(), Movimiento.id.asc())
            .all()
        )
        if not movimientos_entrega and not any(cantidad_sobrante_detalle(d) > 0 for d in lev.detalles):
            raise ValueError("No se encontraron movimientos de entrega vinculados a este levantamiento.")

        resumen_grupos = {}
        for detalle in lev.detalles:
            if getattr(detalle, "alta_logistica", False):
                continue
            clave = _normalizar_grupo_detalle(detalle)
            resumen = resumen_grupos.setdefault(clave, {"entregadas": 0, "recibidas": 0, "sobrantes": 0, "observacion": None})
            resumen["entregadas"] += cantidad_entregada_detalle(detalle)
            resumen["recibidas"] += cantidad_devuelta_detalle(detalle)
            resumen["sobrantes"] += cantidad_sobrante_detalle(detalle)
            if detalle.observacion_devolucion:
                resumen["observacion"] = detalle.observacion_devolucion
        for resumen in resumen_grupos.values():
            resumen["faltantes"] = max(0, resumen["entregadas"] - resumen["recibidas"])

        # Mapear activos entregados y planear primero todas las devoluciones.
        # No se modifica ningún activo hasta validar que las cantidades guardadas
        # se pueden asociar con registros concretos.
        from .model import Activo
        activos_ids_entregados = {m.activo_id for m in movimientos_entrega if m.activo_id}
        activos_por_id = {
            a.id: a for a in self.db.query(Activo).filter(
                Activo.empresa_id == lev.empresa_id,
                Activo.id.in_(activos_ids_entregados or {-1}),
            ).all()
        }
        movimientos_por_activo = {}
        for movimiento in movimientos_entrega:
            movimientos_por_activo.setdefault(movimiento.activo_id, []).append(movimiento)

        usados = set()
        plan = []
        for detalle in sorted(lev.detalles, key=lambda d: (str(d.referencia or "").casefold(), d.id)):
            entregada = cantidad_entregada_detalle(detalle)
            solicitada = cantidad_devuelta_detalle(detalle)
            if solicitada > entregada:
                raise ValueError(f"La cantidad devuelta para '{detalle.nombre}' no puede superar las {entregada} unidades entregadas.")
            if entregada <= 0:
                continue

            candidatos = []
            if detalle.activo_id:
                if detalle.activo_id in activos_por_id:
                    candidatos = [detalle.activo_id]
            elif detalle.es_nuevo:
                marcador = f"detalle_fisico_id={detalle.id}"
                candidatos = sorted({
                    m.activo_id for m in movimientos_entrega
                    if m.activo_id and marcador in (m.observaciones or "")
                })

                # Compatibilidad con levantamientos aprobados antes de incorporar
                # el marcador detalle_fisico_id en sus movimientos.
                if not candidatos:
                    candidatos = sorted(
                        activo_id for activo_id, activo in activos_por_id.items()
                        if activo_id not in usados
                        and (activo.nombre or "").strip().casefold() == (detalle.nombre or "").strip().casefold()
                        and (detalle.categoria_id is None or activo.categoria_id == detalle.categoria_id)
                        and (not detalle.marca or (activo.marca or "").strip().casefold() == detalle.marca.strip().casefold())
                        and (not detalle.modelo or (activo.modelo or "").strip().casefold() == detalle.modelo.strip().casefold())
                        and (not detalle.serial or (activo.serial or "").strip().casefold() == detalle.serial.strip().casefold())
                        and activo_id in movimientos_por_activo
                    )
            candidatos = [asset_id for asset_id in candidatos if asset_id not in usados]
            if len(candidatos) < entregada:
                raise ValueError(
                    f"No fue posible asociar las {entregada} unidades entregadas de '{detalle.nombre}' "
                    "con los activos del inventario. No se registró ninguna devolución; revisa el levantamiento."
                )

            seleccionados = candidatos[:solicitada]
            faltantes_ids = candidatos[solicitada:entregada]
            usados.update(candidatos)
            plan.append((detalle, seleccionados, faltantes_ids, entregada, solicitada))

        devueltos = 0
        faltantes_por_activo = {}
        for detalle, seleccionados, faltantes_ids, entregada, solicitada in plan:
            resumen_grupo = resumen_grupos.get(_normalizar_grupo_detalle(detalle), {})
            entregadas_grupo = int(resumen_grupo.get("entregadas", entregada))
            recibidas_grupo = int(resumen_grupo.get("recibidas", solicitada))
            sobrantes_grupo = int(resumen_grupo.get("sobrantes", 0))
            faltantes_grupo = max(0, entregadas_grupo - recibidas_grupo)
            observacion_grupo = (resumen_grupo.get("observacion") or detalle.observacion_devolucion or "").strip()
            detalle_id_tag = f"detalle_fisico_id={detalle.id}"

            for activo_id in seleccionados:
                activo = activos_por_id.get(activo_id)
                if not activo or not activo.activo:
                    continue
                # Ya devuelto en un intento anterior: no crear movimiento duplicado.
                if activo.responsable_id != lev.responsable_id or activo.estado != "Prestado":
                    continue
                activo.estado = "Disponible"
                activo.responsable_id = None
                activo.tenedor_id = None
                activo.ubicacion_id = lev.ubicacion_id
                nota = (
                    f"Devolución del levantamiento físico #{lev.id}; {detalle_id_tag}. "
                    f"Resumen del grupo: {recibidas_grupo} unidades originales recibidas de {entregadas_grupo}; "
                    f"nuevas unidades encontradas: {sobrantes_grupo}; faltantes: {faltantes_grupo}. "
                    + (f"Observación de devolución: {observacion_grupo}. " if observacion_grupo else "")
                    + f"Registrado por {usuario}."
                )
                self.db.add(Movimiento(
                    empresa_id=lev.empresa_id,
                    activo_id=activo.id,
                    persona_id=lev.responsable_id,
                    ubicacion_id=lev.ubicacion_id,
                    ubicacion_origen_id=lev.ubicacion_id,
                    tipo="Devolucion",
                    estado="Disponible",
                    estado_entrega="Devuelto a bodega",
                    observaciones=nota,
                    usuario=usuario,
                    area=activo.area,
                ))
                devueltos += 1

            # Registrar también la novedad en el historial de los activos que
            # siguen prestados. No se altera su estado ni su responsable.
            for activo_id in faltantes_ids:
                activo = activos_por_id.get(activo_id)
                if not activo or not activo.activo:
                    continue
                if activo.responsable_id != lev.responsable_id or activo.estado != "Prestado":
                    continue
                nota = (
                    f"Novedad de devolución del levantamiento físico #{lev.id}; {detalle_id_tag}. "
                    f"Resumen del grupo: {recibidas_grupo} unidades originales recibidas de {entregadas_grupo}; "
                    f"nuevas unidades encontradas: {sobrantes_grupo}; faltantes: {faltantes_grupo}. "
                    + (f"Observación de devolución: {observacion_grupo}. " if observacion_grupo else "")
                    + f"El activo continúa prestado a {lev.responsable.nombre if lev.responsable else 'su responsable'}. "
                    + f"Registrado por {usuario}."
                )
                faltantes_por_activo[activo_id] = nota

        if faltantes_por_activo:
            movimientos_novedad_previos = (
                self.db.query(Movimiento)
                .filter(
                    Movimiento.empresa_id == lev.empresa_id,
                    Movimiento.tipo == "Novedad devolución",
                    Movimiento.activo_id.in_(faltantes_por_activo.keys()),
                    Movimiento.observaciones.ilike(f"%levantamiento físico #{lev.id}%"),
                )
                .order_by(Movimiento.created_at.desc(), Movimiento.id.desc())
                .all()
            )
            ultima_novedad = {}
            for movimiento in movimientos_novedad_previos:
                ultima_novedad.setdefault(movimiento.activo_id, movimiento.observaciones or "")
            for activo_id, nota in faltantes_por_activo.items():
                if ultima_novedad.get(activo_id) == nota:
                    continue
                activo = activos_por_id[activo_id]
                self.db.add(Movimiento(
                    empresa_id=lev.empresa_id,
                    activo_id=activo.id,
                    persona_id=lev.responsable_id,
                    ubicacion_id=lev.ubicacion_id,
                    ubicacion_origen_id=lev.ubicacion_id,
                    tipo="Novedad devolución",
                    estado="Prestado",
                    estado_entrega="Faltante reportado; continúa prestado",
                    observaciones=nota,
                    usuario=usuario,
                    area=activo.area,
                ))

        # Incorporar unidades adicionales detectadas por encima de lo originalmente
        # entregado. Cada unidad se crea una sola vez: el marcador de movimiento evita
        # duplicados cuando se vuelve a registrar una devolución parcial.
        for detalle in sorted(lev.detalles, key=lambda d: d.id):
            cantidad_nueva = cantidad_sobrante_detalle(detalle)
            if cantidad_nueva <= 0:
                continue
            categoria = self.db.query(Categoria).filter(
                Categoria.id == detalle.categoria_id,
                Categoria.empresa_id == lev.empresa_id,
            ).first()
            if not categoria:
                raise ValueError(
                    f"No se pueden incorporar las unidades nuevas de '{detalle.nombre}': "
                    "la categoría no existe en esta empresa."
                )

            marcador = f"sobrante_devolucion_levantamiento={lev.id}_detalle={detalle.id}"
            movimientos_sobrante = self.db.query(Movimiento).filter(
                Movimiento.empresa_id == lev.empresa_id,
                Movimiento.tipo == "Alta por sobrante",
                Movimiento.observaciones.ilike(f"%{marcador}%"),
            ).all()
            activos_sobrante_existentes = {m.activo_id for m in movimientos_sobrante if m.activo_id}
            creados_antes = len(activos_sobrante_existentes)
            if cantidad_nueva < creados_antes:
                raise ValueError(
                    f"Ya se incorporaron {creados_antes} unidades nuevas de '{detalle.nombre}'. "
                    "No se puede reducir esa cantidad para evitar retirar del inventario unidades ya registradas."
                )

            prefijo = (categoria.prefijo or "ACT").strip().upper()[:10] or "ACT"
            ultimo = self.db.query(Activo.id).order_by(Activo.id.desc()).first()
            siguiente = (ultimo[0] if ultimo else 0) + 1
            faltan_crear = cantidad_nueva - creados_antes
            for _ in range(faltan_crear):
                while True:
                    codigo = f"{prefijo}{siguiente:06d}"
                    codigo_barras = f"TEC-GLS-{siguiente:06d}"
                    existe = self.db.query(Activo.id).filter(
                        Activo.empresa_id == lev.empresa_id,
                        (Activo.codigo == codigo) | (Activo.codigo_barras == codigo_barras),
                    ).first()
                    if not existe:
                        break
                    siguiente += 1

                activo_nuevo = Activo(
                    empresa_id=lev.empresa_id,
                    codigo=codigo,
                    codigo_barras=codigo_barras,
                    serial=None,
                    nombre=detalle.nombre,
                    categoria_id=categoria.id,
                    ubicacion_id=lev.ubicacion_id,
                    marca=detalle.marca,
                    modelo=detalle.modelo,
                    estado="Disponible",
                    responsable_id=None,
                    tenedor_id=None,
                    qr=codigo_barras,
                    observaciones=(
                        f"Unidad nueva incorporada por sobrante del levantamiento físico #{lev.id}. "
                        + (f"Observación de devolución: {detalle.observacion_devolucion}. " if detalle.observacion_devolucion else "")
                        + f"Registrada por {usuario}."
                    ),
                    area=lev.area,
                    activo=True,
                )
                self.db.add(activo_nuevo)
                self.db.flush()
                self.db.add(Movimiento(
                    empresa_id=lev.empresa_id,
                    activo_id=activo_nuevo.id,
                    persona_id=lev.responsable_id,
                    ubicacion_id=lev.ubicacion_id,
                    ubicacion_origen_id=lev.ubicacion_id,
                    tipo="Alta por sobrante",
                    estado="Disponible",
                    estado_entrega="Nueva unidad incorporada a bodega",
                    observaciones=(
                        f"{marcador}; grupo={detalle.nombre}; "
                        f"cantidad_nueva_grupo={cantidad_nueva}; "
                        f"unidad={creados_antes + 1}; levantamiento={lev.id}. "
                        + (f"Observación: {detalle.observacion_devolucion}. " if detalle.observacion_devolucion else "")
                        + f"Registrada por {usuario}."
                    ),
                    usuario=usuario,
                    area=lev.area,
                ))
                creados_antes += 1
                siguiente += 1

        # Lo que no fue recibido conserva su responsable y estado Prestado.
        pendientes = self.db.query(Activo).filter(
            Activo.empresa_id == lev.empresa_id,
            Activo.id.in_(activos_ids_entregados),
            Activo.activo.is_(True),
            Activo.responsable_id == lev.responsable_id,
            Activo.estado == "Prestado",
        ).count()
        lev.estado = "Devuelto parcialmente" if pendientes else "Devuelto"
        self.db.commit()
        return {"devueltos": devueltos, "pendientes": pendientes, "estado": lev.estado}

