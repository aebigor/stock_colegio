from datetime import datetime, timezone
from secrets import token_urlsafe
from sqlalchemy.orm import Session, joinedload
from .levantamiento_model import LevantamientoInventario, LevantamientoDetalle
from .model import Activo
from .movimiento_model import Movimiento
from app.modules.categorias.model import Categoria
from app.modules.personas.model import Persona
from app.modules.ubicaciones.model import Ubicacion


class LevantamientoService:
    def __init__(self, db: Session):
        self.db = db

    def listar(self, area="Todas"):
        q = self.db.query(LevantamientoInventario).options(
            joinedload(LevantamientoInventario.ubicacion),
            joinedload(LevantamientoInventario.responsable),
        )
        if area != "Todas":
            q = q.filter(LevantamientoInventario.area == area)
        return q.order_by(LevantamientoInventario.created_at.desc(), LevantamientoInventario.id.desc()).all()

    def obtener(self, levantamiento_id, area="Todas"):
        q = self.db.query(LevantamientoInventario).options(
            joinedload(LevantamientoInventario.ubicacion),
            joinedload(LevantamientoInventario.responsable),
            joinedload(LevantamientoInventario.detalles).joinedload(LevantamientoDetalle.activo),
            joinedload(LevantamientoInventario.detalles).joinedload(LevantamientoDetalle.categoria),
        ).filter(LevantamientoInventario.id == levantamiento_id)
        if area != "Todas":
            q = q.filter(LevantamientoInventario.area == area)
        return q.first()

    def crear_borrador(self, ubicacion_id, responsable_id, area, usuario):
        ubicacion = self.db.query(Ubicacion).filter(Ubicacion.id == ubicacion_id, Ubicacion.area == area).first() if area != "Todas" else self.db.query(Ubicacion).filter(Ubicacion.id == ubicacion_id).first()
        if not ubicacion:
            raise ValueError("La ubicación seleccionada no es válida.")
        responsable = self.db.query(Persona).filter(Persona.id == responsable_id).first() if responsable_id else None
        levantamiento = LevantamientoInventario(
            ubicacion_id=ubicacion.id,
            responsable_id=responsable.id if responsable else None,
            estado="Borrador",
            creado_por=usuario,
            area=ubicacion.area,
            public_token=token_urlsafe(48),
        )
        self.db.add(levantamiento)
        self.db.flush()
        activos = self.db.query(Activo).filter(
            Activo.ubicacion_id == ubicacion.id,
            Activo.activo.is_(True),
        ).order_by(Activo.nombre, Activo.id).all()
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

    def actualizar_detalle(self, detalle_id, cantidad_encontrada, estado_fisico, observacion):
        d = self.db.query(LevantamientoDetalle).join(LevantamientoInventario).filter(LevantamientoDetalle.id == detalle_id).first()
        if not d or d.levantamiento.estado != "Borrador":
            raise ValueError("Este levantamiento ya está cerrado.")
        d.cantidad_encontrada = max(0, int(cantidad_encontrada))
        d.estado_fisico = estado_fisico
        d.observacion = observacion.strip() or None
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

    def aprobar(self, levantamiento_id, usuario):
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
                detalle_fisico = f"Estado físico verificado: {d.estado_fisico}."
                activo.observaciones = " ".join(x for x in [detalle_fisico, d.observacion, activo.observaciones] if x)
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
                        f"Responsable: {responsable.nombre}. "
                        f"Verificado por Logística: {usuario}."
                        + (f" Observación del docente: {d.observacion}" if d.observacion else "")
                    ),
                    usuario=usuario,
                    firma=lev.firma,
                    area=activo.area,
                    protocolo_aceptado=False,
                ))
                entregados += 1
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
                        observaciones=" ".join(x for x in [f"Estado físico verificado: {d.estado_fisico}.", d.observacion] if x),
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
                            f"Hallazgo nuevo incorporado y entregado automáticamente al aprobar el levantamiento #{lev.id}. "
                            f"Responsable: {responsable.nombre}. "
                            f"Aprobado por: {usuario}."
                            + (f" Observación del docente: {d.observacion}" if d.observacion else "")
                        ),
                        usuario=usuario,
                        firma=lev.firma,
                        area=lev.area,
                    ))
                    creados += 1
                    entregados += 1
                d.observacion = (d.observacion or "") + f" [Incorporado y entregado al responsable al aprobar levantamiento #{lev.id}.]"

        lev.estado = "Aprobado"
        lev.aprobado_por = usuario
        lev.aprobado_at = datetime.now(timezone.utc)
        self.db.commit()
        return {"creados": creados, "entregados": entregados}

    def devolver_todo(self, levantamiento_id, usuario):
        lev = self.db.query(LevantamientoInventario).options(
            joinedload(LevantamientoInventario.detalles)
        ).filter(LevantamientoInventario.id == levantamiento_id).first()
        if not lev or lev.estado != "Aprobado":
            raise ValueError("Solo se puede devolver un levantamiento aprobado.")
        if not lev.responsable_id:
            raise ValueError("El levantamiento no tiene responsable.")

        # No dependemos únicamente de detalle.activo_id: un hallazgo nuevo
        # puede representar varias unidades y cada una obtiene su propio
        # registro de Activo. Las recuperamos por el movimiento de entrega
        # generado al aprobar este levantamiento.
        marca = f"levantamiento físico #{lev.id}"
        movimientos_entrega = (
            self.db.query(Movimiento)
            .filter(
                Movimiento.tipo == "Entrega",
                Movimiento.observaciones.ilike(f"%{marca}%"),
                Movimiento.persona_id == lev.responsable_id,
            )
            .all()
        )
        activo_ids = {m.activo_id for m in movimientos_entrega}
        if not activo_ids:
            raise ValueError("No hay activos entregados por este levantamiento para devolver.")

        devueltos = 0
        for activo_id in activo_ids:
            activo = self.db.query(Activo).filter(Activo.id == activo_id).first()
            if not activo or not activo.activo:
                continue
            if activo.responsable_id != lev.responsable_id or activo.estado != "Prestado":
                continue
            activo.estado = "Disponible"
            activo.responsable_id = None
            activo.tenedor_id = None
            activo.ubicacion_id = lev.ubicacion_id
            self.db.add(Movimiento(
                empresa_id=lev.empresa_id,
                activo_id=activo.id,
                persona_id=lev.responsable_id,
                ubicacion_id=lev.ubicacion_id,
                ubicacion_origen_id=lev.ubicacion_id,
                tipo="Devolucion",
                estado="Disponible",
                estado_entrega="Devuelto a bodega",
                observaciones=f"Devolución completa del levantamiento físico #{lev.id}. Responsable liberado. Registrado por {usuario}.",
                usuario=usuario,
                area=activo.area,
            ))
            devueltos += 1

        self.db.commit()
        return devueltos

