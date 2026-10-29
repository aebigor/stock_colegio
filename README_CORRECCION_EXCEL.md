# Corrección de comparación Excel/PDF en levantamientos físicos

## Archivos
- `app/modules/activos/levantamiento_routes.py`: compara los renglones importados con los activos que ya se agregaron al borrador desde la ubicación elegida. Usa código/serial cuando identifica una unidad; si no, compara nombre, categoría cuando está indicada, marca y modelo. Solo crea hallazgos por la diferencia que excede las unidades existentes. Los activos de la ubicación que no aparecen en el archivo quedan con cantidad encontrada 0 para revisión.
- `app/modules/activos/levantamiento_service.py`: evita el error de aprobación cuando la observación de un hallazgo nuevo es `None`.

## Aplicación
1. Haz copia de seguridad.
2. Descomprime conservando rutas sobre la raíz del proyecto `stock_colegio`.
3. Activa el entorno virtual y ejecuta:
   `python -m py_compile app/modules/activos/levantamiento_routes.py app/modules/activos/levantamiento_service.py`
4. Reinicia Uvicorn/FastAPI.

No requiere migración Alembic.

## Validación necesaria antes de producción
Probar en una base de pruebas una ubicación con 40 sillas existentes y un Excel que informe 40: no debe crear hallazgos nuevos. Probar 42 en Excel: debe crear un hallazgo de 2 unidades. Probar menos unidades: debe dejar los activos no encontrados en 0 para que Logística revise el faltante. La prueba de extremo a extremo con la base real no se ha ejecutado.
