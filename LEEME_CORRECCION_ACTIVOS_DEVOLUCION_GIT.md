CORRECCION: ACTIVOS NUEVOS Y ACTIVOS YA REGISTRADOS EN LA DEVOLUCION
====================================================================

Este ZIP contiene solo los archivos que cambian, conservando las rutas del
proyecto. Descomprime su contenido en la raiz del repositorio stock_colegio.

ARCHIVOS
--------
app/modules/activos/levantamiento_service.py
app/modules/activos/levantamiento_routes.py
app/templates/activos/inventario_fisico.html
tests/test_levantamiento_devolucion_activos_nuevos.py

CAMBIOS
-------
1. El alta registrada por el boton "Agregar activo" se marca automaticamente
   como revisada para la etapa de devolucion. Nunca se considera un prestamo
   al docente y no bloquea "Registrar devolucion".

2. Al abrir un levantamiento Aprobado o Devuelto parcialmente como Logistica,
   el sistema sincroniza al detalle de devolucion los activos que ya existen
   individualmente en el inventario y coinciden con la misma empresa, area y
   ubicacion. Se muestran como "Ya registrado en inventario" y "Revisado
   automaticamente", sin crear otro activo.

3. Solo se sincronizan activos activos con estado Disponible o Mantenimiento.
   No se agregan activos Prestados, dados de baja, inactivos ni de otra empresa,
   area o ubicacion. Esto evita mezclar inventarios o marcar como revisado un
   equipo que sigue bajo custodia de otra persona.

4. La validacion del cierre ignora las altas logisticas y los activos existentes
   sincronizados, porque no fueron parte del prestamo original. Los articulos
   que si fueron prestados siguen requiriendo revision.

5. La sincronizacion es idempotente: al volver a abrir la pantalla no duplica
   detalles ni activos. Tambien excluye los activos que ya se crearon desde las
   altas logisticas o por sobrantes, mediante los marcadores de sus movimientos.

COMO SUBIR A GITHUB
-------------------
1. Haz una copia local del repositorio.
2. Descomprime este ZIP en la raiz de stock_colegio, conservando las carpetas.
3. Revisa los cambios:

   git diff --check
   python -m py_compile app/modules/activos/levantamiento_service.py
   python -m py_compile app/modules/activos/levantamiento_routes.py

4. Ejecuta las pruebas (con las dependencias del proyecto instaladas):

   pytest -q tests/test_levantamiento_devolucion_activos_nuevos.py
   pytest -q tests/test_levantamiento_altas_logistica.py tests/test_levantamiento_sobrantes.py

5. Sube los archivos:

   git add app/modules/activos/levantamiento_service.py
   git add app/modules/activos/levantamiento_routes.py
   git add app/templates/activos/inventario_fisico.html
   git add tests/test_levantamiento_devolucion_activos_nuevos.py
   git commit -m "Fix new and existing assets in physical inventory returns"
   git push origin main

6. En el servidor:

   cd ~/stock_colegio
   git pull --ff-only
   sudo systemctl restart prestamo.service

IMPORTANTE
----------
- No incluye ni modifica .env.
- No incluye migraciones nuevas; utiliza los campos de devolucion que ya se
  agregaron en las migraciones anteriores.
- No ejecutes alembic upgrade por este parche.
- Cuando agregues un activo manualmente en el modulo Activos, asignale la empresa,
  el area, la ubicacion y un estado Disponible o Mantenimiento. Al volver a abrir
  el levantamiento de devolucion, aparecera automaticamente. Si la pagina ya
  estaba abierta, actualizala para ejecutar la sincronizacion.
