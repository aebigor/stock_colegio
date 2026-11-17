import ast
import re
import unicodedata
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).parents[1]


def extraer_funciones(ruta, nombres, namespace):
    tree = ast.parse(ruta.read_text(encoding="utf-8"))
    nodes = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in nombres
    ]
    namespace.update({"__builtins__": __builtins__})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ruta), "exec"), namespace)
    return namespace


routes_ns = extraer_funciones(
    ROOT / "app/modules/activos/levantamiento_routes.py",
    {"_normalizar", "_parsear_cantidad"},
    {"re": re},
)
service_ns = extraer_funciones(
    ROOT / "app/modules/activos/levantamiento_service.py",
    {"cantidad_entregada_detalle", "cantidad_devuelta_detalle", "_normalizar_grupo_detalle"},
    {"re": re, "unicodedata": unicodedata},
)

_normalizar = routes_ns["_normalizar"]
_parsear_cantidad = routes_ns["_parsear_cantidad"]
cantidad_entregada_detalle = service_ns["cantidad_entregada_detalle"]
cantidad_devuelta_detalle = service_ns["cantidad_devuelta_detalle"]
_normalizar_grupo_detalle = service_ns["_normalizar_grupo_detalle"]


class LevantamientoTests(unittest.TestCase):
    def test_normaliza_texto_con_acentos_y_espacios(self):
        self.assertEqual(_normalizar("  Robótica "), "robotica")
        self.assertEqual(_normalizar("CAJAS EQUIPOS ROBÓTICA"), "cajasequiposrobotica")

    def test_parsea_cantidades_desde_textos(self):
        self.assertEqual(_parsear_cantidad("16 CAJAS"), 16)
        self.assertEqual(_parsear_cantidad("7,5 UND"), 7)
        self.assertEqual(_parsear_cantidad("sin cantidad"), 0)
        self.assertEqual(_parsear_cantidad("3 unidades"), 3)

    def test_cantidad_entregada_para_activo_existente_es_una_unidad(self):
        detalle = SimpleNamespace(cantidad_encontrada=9, es_nuevo=False, activo_id=25)
        self.assertEqual(cantidad_entregada_detalle(detalle), 1)

    def test_cantidad_entregada_para_hallazgo_nuevo_respeta_el_total(self):
        detalle = SimpleNamespace(cantidad_encontrada=10, es_nuevo=True, activo_id=None)
        self.assertEqual(cantidad_entregada_detalle(detalle), 10)

    def test_sin_activo_existente_no_se_cuenta_como_entregado(self):
        detalle = SimpleNamespace(cantidad_encontrada=4, es_nuevo=False, activo_id=None)
        self.assertEqual(cantidad_entregada_detalle(detalle), 0)

    def test_cantidad_devuelta_nula_conserva_el_total_legacy_entregado(self):
        detalle = SimpleNamespace(
            cantidad_encontrada=10,
            es_nuevo=True,
            activo_id=None,
            cantidad_devuelta=None,
        )
        self.assertEqual(cantidad_devuelta_detalle(detalle), 10)

    def test_cantidad_devuelta_limita_al_total_entregado(self):
        detalle = SimpleNamespace(
            cantidad_encontrada=10,
            es_nuevo=True,
            activo_id=None,
            cantidad_devuelta=12,
        )
        self.assertEqual(cantidad_devuelta_detalle(detalle), 10)
        detalle.cantidad_devuelta = 8
        self.assertEqual(cantidad_devuelta_detalle(detalle), 8)

    def test_grupos_ignoran_mayusculas_y_acentos(self):
        primero = SimpleNamespace(
            serial=None, id=1, nombre="Portátil", categoria_id=3, marca="Lenovo",
            modelo="T14", es_nuevo=False, estado_fisico="Bueno", observacion="",
        )
        segundo = SimpleNamespace(
            serial=None, id=2, nombre="PORTATIL", categoria_id=3, marca="LENOVO",
            modelo="T14", es_nuevo=False, estado_fisico="Bueno", observacion="",
        )
        self.assertEqual(_normalizar_grupo_detalle(primero), _normalizar_grupo_detalle(segundo))


if __name__ == "__main__":
    unittest.main()
