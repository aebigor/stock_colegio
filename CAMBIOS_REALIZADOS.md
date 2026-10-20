# Cambios realizados

## Incluido
- Ajustes globales de estilos y contraste para formularios, botones, tablas, tarjetas, sidebar y encabezados.
- QR del activo ahora abre el historial del activo.
- Se quitó el botón de Detalle de la tabla de activos.
- El historial muestra la ubicación actual del activo cuando el movimiento no tiene una ubicación asociada.
- En movimientos se añadió la opción “Disponible (se deja en bodega)” y se conectó el campo de ubicación destino con el backend.
- El movimiento “Disponible” deja el estado del activo como Disponible.

## Importante sobre Super Admin por empresa
La separación real de cada empresa no se debe simular solo con un rol o con filtros visuales: requiere añadir la empresa propietaria a usuarios, activos, categorías, ubicaciones, personas, movimientos, mantenimientos y consultas relacionadas, migrar los datos existentes y aplicar el filtro de empresa en todas las rutas. Esta versión no activa todavía esa separación multiempresa para evitar aparentar un aislamiento que no existe. El administrador autorizado `tecnologia@gimsau.edu.co` debe ser el único creador de empresas/Super Admin en la siguiente fase, y esa autorización debe validarse en el backend, no solo ocultando botones.

## Aplicación
Conserva tu archivo `.env` actual fuera de este ZIP y no lo compartas públicamente. Instala/actualiza los archivos del proyecto y prueba primero en una copia de la base de datos.
