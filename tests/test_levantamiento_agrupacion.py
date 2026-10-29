import ast
import re
import unittest
from pathlib import Path


# Carga las funciones puras del módulo sin inicializar la aplicación ni abrir
# una conexión PostgreSQL durante estas pruebas unitarias.
SOURCE = Path(__file__).parents[1] / "app" / "modules" / "activos" / "levantamiento_routes.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
FUNCTIONS = {"_normalizar", "_agrupar_filas_importadas"}
NODES = [node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS]
NAMESPACE = {"re": re}
exec(compile(ast.Module(body=NODES, type_ignores=[]), str(SOURCE), "exec"), NAMESPACE)
_agrupar_filas_importadas = NAMESPACE["_agrupar_filas_importadas"]


class AgrupacionLevantamientoTests(unittest.TestCase):
    def test_agrupa_filas_compatibles_sumando_cantidad(self):
        filas = [
            {"nombre": "Silla", "categoria": "Mobiliario", "cantidad": 2, "estado": "Bueno", "observacion": ""},
            {"nombre": " silla ", "categoria": "MOBILIARIO", "cantidad": 3, "estado": "Bueno", "observacion": ""},
        ]
        resultado = _agrupar_filas_importadas(filas)
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["cantidad"], 5)
        self.assertEqual(resultado[0]["nombre"], "Silla")

    def test_no_agrupa_seriales_o_referencias(self):
        filas = [
            {"nombre": "Portátil", "cantidad": 1, "serial": "ABC123"},
            {"nombre": "Portátil", "cantidad": 1, "serial": "DEF456"},
            {"nombre": "Silla", "cantidad": 2, "referencia": "REF-1"},
            {"nombre": "Silla", "cantidad": 3, "referencia": "REF-1"},
        ]
        self.assertEqual(len(_agrupar_filas_importadas(filas)), 4)

    def test_separa_categoria_estado_y_observacion(self):
        filas = [
            {"nombre": "Silla", "categoria": "Mobiliario", "cantidad": 2, "estado": "Bueno"},
            {"nombre": "Silla", "categoria": "Laboratorio", "cantidad": 1, "estado": "Bueno"},
            {"nombre": "Silla", "categoria": "Mobiliario", "cantidad": 1, "estado": "Malo"},
            {"nombre": "Silla", "categoria": "Mobiliario", "cantidad": 1, "estado": "Bueno", "observacion": "Pata rota"},
        ]
        self.assertEqual(len(_agrupar_filas_importadas(filas)), 4)

    def test_ignora_cantidades_invalidas_y_no_modifica_entrada(self):
        fila = {"nombre": "Silla", "cantidad": 0}
        resultado = _agrupar_filas_importadas([fila])
        self.assertEqual(resultado, [])
        self.assertEqual(fila["cantidad"], 0)


if __name__ == "__main__":
    unittest.main()
