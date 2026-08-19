-- =============================================================
-- SCHEMA VENTAS - Digital Software Solutions (DSS)
-- Ejecutar en el SQL Editor de Supabase.
-- Idempotente: se puede correr varias veces sin romper nada.
-- =============================================================

-- -------------------------------------------------------------
-- 1. PROSPECTOS
-- -------------------------------------------------------------
create table if not exists prospectos (
    id              bigserial primary key,
    nombre          text not null,
    telefono        text,
    direccion       text,
    ciudad          text default 'Guadalajara',
    giro            text,
    fuente          text not null default 'manual',
    place_id        text unique,
    rating          numeric(2,1),
    total_resenas   integer,
    etapa           text not null default 'nuevo',
    valor_estimado  numeric(12,2) default 0,
    notas           text,
    creado_en       timestamptz not null default now(),
    actualizado_en  timestamptz not null default now(),
    constraint prospectos_etapa_chk check (
        etapa in ('nuevo','contactado','interesado','cotizado','ganado','perdido')
    ),
    constraint prospectos_fuente_chk check (
        fuente in ('manual','google_places','web','referido','facebook','whatsapp')
    )
);

create index if not exists idx_prospectos_etapa   on prospectos (etapa);
create index if not exists idx_prospectos_ciudad  on prospectos (ciudad);
create index if not exists idx_prospectos_creado  on prospectos (creado_en desc);


-- -------------------------------------------------------------
-- 2. CLIENTES
-- -------------------------------------------------------------
create table if not exists clientes (
    id                bigserial primary key,
    prospecto_id      bigint references prospectos(id) on delete set null,
    nombre            text not null,
    razon_social      text,
    rfc               text,
    contacto          text,
    email             text,
    telefono          text,
    direccion         text,
    ciudad            text default 'Guadalajara',
    condiciones_pago  text default 'contado',
    activo            boolean not null default true,
    notas             text,
    creado_en         timestamptz not null default now()
);

create index if not exists idx_clientes_nombre on clientes (nombre);
create index if not exists idx_clientes_rfc    on clientes (rfc);


-- -------------------------------------------------------------
-- 3. IMPRESORAS (parque instalado por cliente)
-- -------------------------------------------------------------
create table if not exists impresoras (
    id            bigserial primary key,
    cliente_id    bigint not null references clientes(id) on delete cascade,
    marca         text,
    modelo        text not null,
    serie         text,
    toner_modelo  text,
    paginas_mes   integer default 0,
    ubicacion     text,
    notas         text,
    creado_en     timestamptz not null default now()
);

create index if not exists idx_impresoras_cliente on impresoras (cliente_id);
create index if not exists idx_impresoras_modelo  on impresoras (modelo);


-- -------------------------------------------------------------
-- 4. PRODUCTOS (toners, licencias, servicios)
-- -------------------------------------------------------------
create table if not exists productos (
    id                   bigserial primary key,
    sku                  text unique,
    nombre               text not null,
    tipo                 text not null default 'toner',
    marca                text,
    modelo_compatible    text,
    rendimiento_paginas  integer,
    costo                numeric(12,2) not null default 0,
    precio               numeric(12,2) not null default 0,
    stock                integer not null default 0,
    activo               boolean not null default true,
    creado_en            timestamptz not null default now(),
    constraint productos_tipo_chk check (tipo in ('toner','licencia','servicio','refaccion'))
);

create index if not exists idx_productos_tipo   on productos (tipo);
create index if not exists idx_productos_activo on productos (activo);


-- -------------------------------------------------------------
-- 5. COTIZACIONES
-- -------------------------------------------------------------
create table if not exists cotizaciones (
    id             bigserial primary key,
    folio          text unique,
    cliente_id     bigint references clientes(id) on delete set null,
    prospecto_id   bigint references prospectos(id) on delete set null,
    fecha          date not null default current_date,
    vigencia_dias  integer not null default 15,
    subtotal       numeric(12,2) not null default 0,
    iva            numeric(12,2) not null default 0,
    total          numeric(12,2) not null default 0,
    costo_total    numeric(12,2) not null default 0,
    estatus        text not null default 'borrador',
    pdf_ruta       text,
    notas          text,
    creado_en      timestamptz not null default now(),
    constraint cotizaciones_estatus_chk check (
        estatus in ('borrador','enviada','aceptada','rechazada','vencida')
    )
);

create index if not exists idx_cotizaciones_estatus on cotizaciones (estatus);
create index if not exists idx_cotizaciones_fecha   on cotizaciones (fecha desc);
create index if not exists idx_cotizaciones_cliente on cotizaciones (cliente_id);


-- -------------------------------------------------------------
-- 6. COTIZACION_ITEMS
-- -------------------------------------------------------------
create table if not exists cotizacion_items (
    id               bigserial primary key,
    cotizacion_id    bigint not null references cotizaciones(id) on delete cascade,
    producto_id      bigint references productos(id) on delete set null,
    descripcion      text not null,
    cantidad         numeric(12,2) not null default 1,
    precio_unitario  numeric(12,2) not null default 0,
    costo_unitario   numeric(12,2) not null default 0,
    importe          numeric(12,2) not null default 0
);

create index if not exists idx_cotitems_cotizacion on cotizacion_items (cotizacion_id);


-- -------------------------------------------------------------
-- 7. CONTRATOS
-- -------------------------------------------------------------
create table if not exists contratos (
    id             bigserial primary key,
    cliente_id     bigint not null references clientes(id) on delete cascade,
    cotizacion_id  bigint references cotizaciones(id) on delete set null,
    tipo           text not null default 'suministro',
    fecha_inicio   date not null default current_date,
    fecha_fin      date,
    monto_mensual  numeric(12,2) not null default 0,
    estatus        text not null default 'activo',
    notas          text,
    creado_en      timestamptz not null default now(),
    constraint contratos_estatus_chk check (estatus in ('activo','suspendido','vencido','cancelado'))
);

create index if not exists idx_contratos_cliente on contratos (cliente_id);
create index if not exists idx_contratos_estatus on contratos (estatus);


-- -------------------------------------------------------------
-- 8. ENTREGAS
-- -------------------------------------------------------------
create table if not exists entregas (
    id                bigserial primary key,
    cliente_id        bigint not null references clientes(id) on delete cascade,
    cotizacion_id     bigint references cotizaciones(id) on delete set null,
    fecha_programada  date,
    fecha_entrega     date,
    estatus           text not null default 'programada',
    guia              text,
    notas             text,
    creado_en         timestamptz not null default now(),
    constraint entregas_estatus_chk check (
        estatus in ('programada','en_ruta','entregada','cancelada')
    )
);

create index if not exists idx_entregas_estatus on entregas (estatus);
create index if not exists idx_entregas_fecha   on entregas (fecha_programada);


-- -------------------------------------------------------------
-- 9. ACTIVIDAD (bitacora comercial)
-- -------------------------------------------------------------
create table if not exists actividad (
    id            bigserial primary key,
    tipo          text not null default 'nota',
    prospecto_id  bigint references prospectos(id) on delete cascade,
    cliente_id    bigint references clientes(id) on delete cascade,
    descripcion   text not null,
    usuario       text default 'oswaldo',
    creado_en     timestamptz not null default now(),
    constraint actividad_tipo_chk check (
        tipo in ('llamada','visita','correo','whatsapp','cotizacion','nota')
    )
);

create index if not exists idx_actividad_creado    on actividad (creado_en desc);
create index if not exists idx_actividad_prospecto on actividad (prospecto_id);


-- =============================================================
-- VISTAS
-- =============================================================

-- Embudo: cuantos prospectos y cuanto valor hay en cada etapa
create or replace view embudo as
select
    etapa,
    count(*)::bigint                       as prospectos,
    coalesce(sum(valor_estimado), 0)::numeric(12,2) as valor_estimado,
    max(actualizado_en)                    as ultima_actualizacion
from prospectos
group by etapa;


-- Metricas de los ultimos 7 dias
create or replace view metricas_semana as
select
    (select count(*) from prospectos
        where creado_en >= now() - interval '7 days')                     as prospectos_nuevos,
    (select count(*) from actividad
        where creado_en >= now() - interval '7 days')                     as actividades,
    (select count(*) from cotizaciones
        where fecha >= current_date - 7)                                  as cotizaciones_emitidas,
    (select coalesce(sum(total), 0)::numeric(12,2) from cotizaciones
        where fecha >= current_date - 7)                                  as monto_cotizado,
    (select count(*) from cotizaciones
        where estatus = 'aceptada' and fecha >= current_date - 7)         as cotizaciones_ganadas,
    (select coalesce(sum(total), 0)::numeric(12,2) from cotizaciones
        where estatus = 'aceptada' and fecha >= current_date - 7)         as monto_ganado,
    (select coalesce(sum(total - costo_total), 0)::numeric(12,2) from cotizaciones
        where estatus = 'aceptada' and fecha >= current_date - 7)         as margen_ganado,
    (select count(*) from entregas
        where estatus = 'entregada'
          and fecha_entrega >= current_date - 7)                          as entregas_realizadas;
