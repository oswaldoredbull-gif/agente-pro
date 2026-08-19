-- =============================================================
-- SCHEMA LICENCIAS - Digital Software Solutions (DSS)
-- Ejecutar DESPUES de schema_ventas.sql (depende de clientes y productos).
-- Idempotente.
-- =============================================================

create table if not exists licencias_activas (
    id                bigserial primary key,
    cliente_id        bigint references clientes(id) on delete cascade,
    producto_id       bigint references productos(id) on delete set null,
    paquete           text not null,
    software          text,
    edicion           text,
    puestos           integer not null default 1,
    fecha_inicio      date not null default current_date,
    fecha_fin         date not null,
    periodicidad      text not null default 'anual',
    costo_total       numeric(12,2) not null default 0,
    precio_total      numeric(12,2) not null default 0,
    renovacion_auto   boolean not null default false,
    estatus           text not null default 'activa',
    clave_activacion  text,
    notas             text,
    creado_en         timestamptz not null default now(),
    constraint licencias_estatus_chk check (
        estatus in ('activa','por_vencer','vencida','cancelada')
    ),
    constraint licencias_periodicidad_chk check (
        periodicidad in ('mensual','anual','perpetua')
    ),
    constraint licencias_fechas_chk check (fecha_fin >= fecha_inicio)
);

create index if not exists idx_licencias_cliente on licencias_activas (cliente_id);
create index if not exists idx_licencias_fin     on licencias_activas (fecha_fin);
create index if not exists idx_licencias_estatus on licencias_activas (estatus);


-- =============================================================
-- VISTAS
-- =============================================================

-- Renovaciones: licencias vigentes ordenadas por cercania de vencimiento.
-- Filtrar desde la app con ?dias_restantes=lte.45
create or replace view renovaciones as
select
    l.id,
    l.cliente_id,
    c.nombre                                        as cliente,
    c.email,
    c.telefono,
    l.paquete,
    l.software,
    l.puestos,
    l.fecha_inicio,
    l.fecha_fin,
    (l.fecha_fin - current_date)::integer           as dias_restantes,
    l.precio_total,
    l.costo_total,
    (l.precio_total - l.costo_total)::numeric(12,2) as margen,
    case
        when l.precio_total > 0
        then round(((l.precio_total - l.costo_total) / l.precio_total) * 100, 1)
        else 0
    end                                             as margen_pct,
    l.renovacion_auto,
    l.estatus
from licencias_activas l
left join clientes c on c.id = l.cliente_id
where l.estatus in ('activa','por_vencer')
  and l.periodicidad <> 'perpetua'
order by l.fecha_fin asc;


-- Ingreso recurrente normalizado a mensual y anual, por cliente
create or replace view ingreso_recurrente as
select
    l.cliente_id,
    coalesce(c.nombre, 'Sin cliente')  as cliente,
    count(*)::bigint                   as licencias,
    sum(l.puestos)::bigint             as puestos,
    round(sum(
        case l.periodicidad
            when 'mensual' then l.precio_total
            when 'anual'   then l.precio_total / 12.0
            else 0
        end
    ), 2)                              as mrr,
    round(sum(
        case l.periodicidad
            when 'mensual' then l.precio_total * 12.0
            when 'anual'   then l.precio_total
            else 0
        end
    ), 2)                              as arr,
    round(sum(
        case l.periodicidad
            when 'mensual' then (l.precio_total - l.costo_total) * 12.0
            when 'anual'   then (l.precio_total - l.costo_total)
            else 0
        end
    ), 2)                              as margen_anual
from licencias_activas l
left join clientes c on c.id = l.cliente_id
where l.estatus in ('activa','por_vencer')
group by l.cliente_id, c.nombre
order by arr desc;
