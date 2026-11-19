from types import SimpleNamespace

from app.modules.activos.levantamiento_service import (
    activo_sincronizable_devolucion,
    detalles_pendientes_devolucion,
    cantidad_entregada_detalle,
)


def test_alta_logistica_no_bloquea_el_cierre_aunque_no_tenga_revision_manual():
    alta = SimpleNamespace(alta_logistica=True, revisado_devolucion=False)
    prestamo_pendiente = SimpleNamespace(alta_logistica=False, revisado_devolucion=False)

    assert detalles_pendientes_devolucion([alta, prestamo_pendiente]) == [prestamo_pendiente]
    assert cantidad_entregada_detalle(alta) == 0


def test_alta_logistica_ya_revisada_no_cuenta_como_prestamo():
    alta = SimpleNamespace(
        alta_logistica=True,
        es_nuevo=True,
        activo_id=None,
        cantidad_encontrada=3,
        revisado_devolucion=True,
    )

    assert detalles_pendientes_devolucion([alta]) == []
    assert cantidad_entregada_detalle(alta) == 0


def test_activo_disponible_de_la_misma_empresa_area_y_ubicacion_se_sincroniza():
    levantamiento = SimpleNamespace(empresa_id=15, ubicacion_id=28, area="Logística")
    activo = SimpleNamespace(
        empresa_id=15,
        ubicacion_id=28,
        area="Logística",
        estado="Disponible",
        activo=True,
    )

    assert activo_sincronizable_devolucion(activo, levantamiento)


def test_activo_en_mantenimiento_de_la_misma_ubicacion_tambien_se_sincroniza():
    levantamiento = SimpleNamespace(empresa_id=15, ubicacion_id=28, area="Logística")
    activo = SimpleNamespace(
        empresa_id=15,
        ubicacion_id=28,
        area="Logística",
        estado="Mantenimiento",
        activo=True,
    )

    assert activo_sincronizable_devolucion(activo, levantamiento)


def test_no_se_sincronizan_activos_de_otra_area_empresa_o_ubicacion():
    levantamiento = SimpleNamespace(empresa_id=15, ubicacion_id=28, area="Logística")
    base = {
        "empresa_id": 15,
        "ubicacion_id": 28,
        "area": "Logística",
        "estado": "Disponible",
        "activo": True,
    }

    for cambio in (
        {"empresa_id": 16},
        {"ubicacion_id": 29},
        {"area": "Medios"},
    ):
        datos = {**base, **cambio}
        assert not activo_sincronizable_devolucion(SimpleNamespace(**datos), levantamiento)


def test_no_se_sincronizan_activos_prestados_o_dados_de_baja():
    levantamiento = SimpleNamespace(empresa_id=15, ubicacion_id=28, area="Logística")
    base = {
        "empresa_id": 15,
        "ubicacion_id": 28,
        "area": "Logística",
        "estado": "Disponible",
        "activo": True,
    }

    for estado in ("Prestado", "Baja"):
        datos = {**base, "estado": estado}
        assert not activo_sincronizable_devolucion(SimpleNamespace(**datos), levantamiento)

    datos = {**base, "activo": False}
    assert not activo_sincronizable_devolucion(SimpleNamespace(**datos), levantamiento)
