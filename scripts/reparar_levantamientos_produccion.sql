-- Reparación de datos de levantamientos físicos ya aprobados.
-- IMPORTANTE: haz primero un backup de prestamo_computadores.
-- Ejecutar conectado a la base de datos de producción correcta.
BEGIN;

-- 1) Quitar únicamente la nota automática que se añadió por error a la
-- observación escrita por el docente. El resto del texto se conserva.
UPDATE levantamientos_inventario_detalle
SET observacion = NULLIF(BTRIM(REGEXP_REPLACE(
    observacion,
    E'\\s*\\[Incorporado y entregado al responsable al aprobar levantamiento #[0-9]+\\.\\]',
    '',
    'g'
)), '')
WHERE observacion ~ E'\\[Incorporado y entregado al responsable al aprobar levantamiento #[0-9]+\\.\\]';

-- 1b) Restaurar observaciones originales de activos existentes afectados por
-- el error anterior. El código concatenaba el estado físico + observación del
-- docente delante de la observación que ya tenía el activo. Se elimina solo
-- ese prefijo para los activos vinculados a levantamientos.
UPDATE activos a
SET observaciones = NULLIF(BTRIM(SUBSTRING(
    a.observaciones FROM
    LENGTH('Estado físico verificado: ' || d.estado_fisico || '.')
    + LENGTH(COALESCE(d.observacion, '')) + 3
)), '')
FROM levantamientos_inventario_detalle d
JOIN levantamientos_inventario li ON li.id = d.levantamiento_id
WHERE d.activo_id = a.id
  AND d.es_nuevo IS FALSE
  AND a.observaciones LIKE ('Estado físico verificado: ' || d.estado_fisico || '.%');

-- 2) Corregir área de levantamientos que quedaron como "General" por tomar
-- el área descriptiva de la ubicación en vez del área del usuario creador.
UPDATE levantamientos_inventario li
SET area = CASE
    WHEN r.nombre IN ('Administrador de Logística', 'Admin de Logística') THEN 'Logística'
    WHEN r.nombre IN ('Administrador de Medios', 'Admin de Medios') THEN 'Medios'
    ELSE li.area
END
FROM usuarios u
JOIN roles r ON r.id = u.rol_id
WHERE li.creado_por = u.id
  AND li.area = 'General'
  AND r.nombre IN ('Administrador de Logística', 'Admin de Logística', 'Administrador de Medios', 'Admin de Medios');

-- 3) Marcar como Devuelto solo los levantamientos aprobados cuyos movimientos
-- de entrega están vinculados a ese levantamiento y cuyos activos ya no están
-- prestados al responsable. No cambia estados de activos.
UPDATE levantamientos_inventario li
SET estado = 'Devuelto'
WHERE li.estado = 'Aprobado'
  AND EXISTS (
      SELECT 1
      FROM movimientos m
      WHERE m.empresa_id = li.empresa_id
        AND m.tipo = 'Entrega'
        AND m.persona_id = li.responsable_id
        AND (
            m.observaciones ILIKE ('%levantamiento físico #' || li.id || '%')
            OR m.observaciones ILIKE ('%levantamiento #' || li.id || '%')
        )
  )
  AND NOT EXISTS (
      SELECT 1
      FROM movimientos m
      JOIN activos a ON a.id = m.activo_id
      WHERE m.empresa_id = li.empresa_id
        AND m.tipo = 'Entrega'
        AND m.persona_id = li.responsable_id
        AND (
            m.observaciones ILIKE ('%levantamiento físico #' || li.id || '%')
            OR m.observaciones ILIKE ('%levantamiento #' || li.id || '%')
        )
        AND a.activo IS TRUE
        AND a.estado = 'Prestado'
        AND (a.responsable_id = li.responsable_id OR a.tenedor_id = li.responsable_id)
  );

COMMIT;
