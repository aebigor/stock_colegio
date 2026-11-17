from types import SimpleNamespace

from app.modules.activos.levantamiento_service import (
    cantidad_entregada_detalle,
    estado_inventario_para_alta,
)


def test_logistics_new_assets_are_not_counted_as_teacher_loans():
    detalle = SimpleNamespace(
        alta_logistica=True, es_nuevo=True, cantidad_encontrada=3, activo_id=None
    )
    assert cantidad_entregada_detalle(detalle) == 0


def test_good_or_regular_new_asset_enters_as_available():
    assert estado_inventario_para_alta("Bueno") == "Disponible"
    assert estado_inventario_para_alta("Regular") == "Disponible"


def test_damaged_new_asset_enters_maintenance():
    assert estado_inventario_para_alta("Malo") == "Mantenimiento"
    assert estado_inventario_para_alta("Mantenimiento") == "Mantenimiento"
