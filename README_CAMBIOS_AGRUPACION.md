# Agrupación de artículos en levantamientos físicos — GLS Inventario

## Archivos incluidos
- `app/modules/activos/levantamiento_routes.py`: consolida filas compatibles de PDF/Excel, reconoce la columna Serial por separado y reutiliza detalles de activos ya incluidos en el borrador cuando hay coincidencia segura.
- `app/templates/activos/inventario_fisico.html`: indica cuántas unidades representa un hallazgo agrupado en la revisión de Logística.
- `app/templates/activos/inventario_fisico_publico.html`: muestra el mismo indicador en el formulario público del docente.
- `tests/test_levantamiento_agrupacion.py`: pruebas unitarias de las reglas de agrupación.
- No se modificaron modelos ni se requiere migración Alembic: se reutilizan `cantidad_sistema`, `cantidad_encontrada` y los detalles existentes.

## Reglas
- Se agrupan filas con el mismo nombre normalizado, categoría, marca, modelo, estado y observación.
- Una fila que tenga referencia o serial se mantiene individual para preservar identificadores.
- Si el borrador ya contiene activos compatibles en la ubicación y categoría, la importación marca como encontrados tantos registros individuales como indique la cantidad. El sobrante queda como hallazgo nuevo agrupado.
- Si la cantidad importada es menor que la cantidad de activos compatibles, los restantes quedan con cantidad encontrada 0 para revisión; no se eliminan ni se dan de baja automáticamente.
- La aprobación existente procesa `cantidad_encontrada` de cada hallazgo nuevo creando un registro `Activo` por unidad, con código propio.
- Los grupos no combinan observaciones ni estados diferentes.

## Aplicación local (PowerShell)
1. Haz una copia de seguridad del proyecto y reemplaza únicamente los archivos del ZIP respetando las rutas.
2. Activa el entorno virtual desde la raíz del proyecto.
3. Ejecuta las pruebas:

```powershell
python -m unittest discover -s tests -v
python -m compileall app/modules/activos
```

4. Inicia la aplicación como normalmente lo haces. Para este proyecto, el punto de entrada FastAPI es `app.main:app`; por ejemplo:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

No ejecutes `alembic upgrade head` por este cambio, ya que no incluye migraciones.

## Producción
1. Haz backup de la base de datos y despliega los archivos del ZIP conservando la estructura de carpetas.
2. Ejecuta las pruebas en el mismo entorno de despliegue.
3. Reinicia el proceso ASGI/servicio según el mecanismo usado por el servidor.
4. No se requiere migración de base de datos para estos cambios.

## Verificación realizada en este entorno
- Compilación Python de `app/modules/activos`: correcta.
- Compilación Jinja de las dos plantillas editadas: correcta.
- 4 pruebas unitarias de agrupación: correctas.
- No se ejecutó una prueba integral contra PostgreSQL ni una aprobación real con datos: esta entrega no afirma haber validado esas operaciones en una base real.
