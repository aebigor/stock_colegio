# Inventario Escolar GIMSAU — tema oscuro y gestión multiempresa

## Qué cambió

- Se conserva el tema oscuro original: fondo azul noche, tarjetas oscuras y acento aguamarina. Los textos principales son blancos y los secundarios gris claro.
- Se corrigió el contraste de tablas que usan fondo blanco o `table-light`: esas superficies tienen texto oscuro y enlaces azul oscuro; las tablas oscuras conservan texto blanco.
- Se reforzaron los estilos de botones, formularios, foco de teclado y botones de acciones.
- Se incorporó gestión multiempresa: el administrador de plataforma `tecnologia@gimsau.edu.co` puede registrar una empresa y crear su primer Super Admin con nombre, correo y contraseña.
- Los Super Admin administran únicamente los datos de su empresa. El administrador de plataforma solo accede al módulo de Empresas y no administra los inventarios de los tenants.
- Se agregaron migraciones para asociar usuarios, activos, categorías, ubicaciones, personas, movimientos, mantenimientos y configuración a una empresa. Los datos históricos se conservan en GIMSAU.
- El QR del activo abre el historial y se añadió el movimiento `Disponible (se deja en bodega)`.


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

## Cuentas iniciales y empresas

- La cuenta `tecnologia@gimsau.edu.co` debe tener el rol **Administrador de Plataforma** y `empresa_id` vacío. Es la única cuenta autorizada para crear empresas y sus Super Admin.
- En una base nueva, la contraseña inicial de esa cuenta se toma de `INITIAL_ADMIN_PASSWORD` en `.env`. En una base existente, el seeder conserva la contraseña de la cuenta existente.
- Cada empresa nueva se crea desde **Empresas**. El formulario solicita nombre completo, correo, instituto/empresa y contraseña inicial (mínimo 10 caracteres). La contraseña se almacena con hash, nunca en texto plano.
- El Super Admin recién creado pertenece a una sola empresa. Los usuarios normales y los datos del inventario deben quedar asociados a esa empresa.
- La cuenta `bader` es una cuenta histórica de Logística; revisa su rol y empresa antes de usarla en una instalación nueva.

**Importante:** antes de aplicar migraciones sobre una base existente, crea un respaldo. Después de `alembic upgrade head`, inicia sesión con `tecnologia@gimsau.edu.co` y confirma que el menú muestre únicamente **Empresas**. No uses el sistema con varios institutos hasta probar con dos empresas de prueba que cada Super Admin no puede ver ni editar los registros de la otra.

## Pruebas manuales recomendadas

1. Entra como Super Admin y crea un activo para `Medios` y otro para `Logística`.
2. Entra como `bader`: confirma que solo aparecen los registros de Logística y que probar una URL de un artículo de Medios devuelve 404.
3. En Activos, filtra por categoría, estado y texto; confirma que los resultados cambian.
4. Edita el nombre/estado de un activo y luego desactiva uno; revisa **Reportes → Historial reciente de cambios y bajas**.
5. Descarga el Excel desde Reportes y confirma que contiene la columna Área.
6. Cierra sesión y prueba abrir `/activos`: debe enviarte al login.

## Notas de datos

Los artículos existentes se asignan inicialmente al área `Medios` durante la migración. Revisa con el Super Admin y reasigna a Logística únicamente los artículos que correspondan al inventario de Bader. No se mezclan ni se duplican automáticamente los artículos históricos.
