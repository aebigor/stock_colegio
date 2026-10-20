# Inventario Escolar — arranque local y áreas separadas

## Qué cambió

- Los filtros de activos trabajan en el servidor: texto (nombre, código, serial, marca y modelo), categoría, estado del artículo, registro activo/inactivo y área (esta última solo para Super Admin).
- Categorías ahora se pueden buscar por nombre/prefijo y filtrar por activas/inactivas. Se evita borrar una categoría que ya tenga artículos: se desactiva para conservar su trazabilidad.
- Hay tres roles: `Super Admin`, `Administrador de Medios` y `Administrador de Logística`. El Super Admin consulta ambos inventarios y puede crear/desactivar usuarios desde **Usuarios**.
- La cuenta `bader` queda como Administrador de Logística. Su inventario queda separado de Medios en las consultas del servidor y en reportes.
- Altas, ediciones, cambios de estado, bajas y desactivaciones/reactivaciones generan un registro de movimiento con fecha, usuario, área y detalle. El reporte muestra el historial reciente y el Excel incluye el área.
- Se corrigieron las vistas de ubicaciones y configuración para que correspondan con los campos actuales de la base de datos.
- Las rutas internas exigen inicio de sesión. El cierre de sesión elimina la cookie de acceso.

## Requisitos

- Python 3.11 o superior (si se usa Python 3.14, instalar las dependencias en un entorno virtual limpio).
- PostgreSQL encendido y una base de datos para este proyecto.

## Ejecutarlo en Windows / PowerShell

1. Descomprime esta carpeta en una ruta sencilla, por ejemplo `C:\proyectos\Inventario`. Abre PowerShell en esa carpeta.
2. Si ya tienes un `.env` con tu conexión válida, **consérvalo**. Si no lo tienes, ejecuta:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

   Configura `DATABASE_NAME`, `DATABASE_USER` y `DATABASE_PASSWORD` con los datos reales de PostgreSQL. También cambia `SECRET_KEY`, `INITIAL_ADMIN_PASSWORD` e `INITIAL_BADER_PASSWORD` antes del primer arranque. Las contraseñas iniciales solo se usan al crear cada cuenta por primera vez.

3. Crea y activa el entorno e instala dependencias:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

   Si PowerShell bloquea la activación, ejecuta `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` en esa ventana y activa otra vez.

4. Crea la base si aún no existe. En pgAdmin puedes crear una base llamada `inventario_colegio` o usar la que hayas configurado en `.env`. Si contiene información importante, haz primero un respaldo desde PowerShell, por ejemplo: `pg_dump -h 127.0.0.1 -p 5432 -U postgres inventario_colegio > respaldo_inventario.sql` (ajusta usuario, puerto y nombre).
5. Ejecuta las migraciones desde la carpeta raíz del proyecto:

   ```powershell
   alembic upgrade head
   ```

6. Inicia la aplicación:

   ```powershell
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

7. Abre `http://127.0.0.1:8000/login`.

## Cuentas iniciales

En una base nueva se crean estas cuentas: `admin` (Super Admin) y `bader` (Administrador de Logística). Con los valores de ejemplo de `.env.example`, las contraseñas iniciales son `CambiarAdmin2026!` y `CambiarBader2026!`, respectivamente. Cámbialas en `.env` antes del primer arranque. En bases donde ya existe una cuenta, el seeder no reemplaza su contraseña.

El usuario `bader` ve y modifica únicamente artículos del área Logística. El Super Admin ve ambos inventarios desde Activos y Reportes. No compartas las contraseñas iniciales: usa contraseñas propias antes de exponer la web en red.

## Pruebas manuales recomendadas

1. Entra como Super Admin y crea un activo para `Medios` y otro para `Logística`.
2. Entra como `bader`: confirma que solo aparecen los registros de Logística y que probar una URL de un artículo de Medios devuelve 404.
3. En Activos, filtra por categoría, estado y texto; confirma que los resultados cambian.
4. Edita el nombre/estado de un activo y luego desactiva uno; revisa **Reportes → Historial reciente de cambios y bajas**.
5. Descarga el Excel desde Reportes y confirma que contiene la columna Área.
6. Cierra sesión y prueba abrir `/activos`: debe enviarte al login.

## Notas de datos

Los artículos existentes se asignan inicialmente al área `Medios` durante la migración. Revisa con el Super Admin y reasigna a Logística únicamente los artículos que correspondan al inventario de Bader. No se mezclan ni se duplican automáticamente los artículos históricos.
