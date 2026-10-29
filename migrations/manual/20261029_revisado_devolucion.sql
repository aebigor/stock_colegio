-- Agrega una marca independiente para revisar los grupos antes de devolver.
-- Ejecutar una sola vez en la base PostgreSQL del inventario.
ALTER TABLE levantamientos_inventario_detalle
    ADD COLUMN IF NOT EXISTS revisado_devolucion BOOLEAN NOT NULL DEFAULT FALSE;
