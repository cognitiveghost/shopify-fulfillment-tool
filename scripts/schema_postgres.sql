-- PostgreSQL schema for shopify-fulfillment-tool
-- Replaces JSON file storage with fully normalized relational tables.
-- Run with: psql -U postgres -d fulfillment_db -f scripts/schema_postgres.sql

BEGIN;

-- ── Drop all tables in reverse FK dependency order ─────────────────────────
DROP TABLE IF EXISTS label_print_events CASCADE;
DROP TABLE IF EXISTS packing_events CASCADE;
DROP TABLE IF EXISTS analysis_events CASCADE;
DROP TABLE IF EXISTS sessions CASCADE;
DROP TABLE IF EXISTS client_sku_labels CASCADE;
DROP TABLE IF EXISTS client_packing_configs CASCADE;
DROP TABLE IF EXISTS client_tag_sku_mappings CASCADE;
DROP TABLE IF EXISTS client_tags CASCADE;
DROP TABLE IF EXISTS client_tag_categories CASCADE;
DROP TABLE IF EXISTS client_rules CASCADE;
DROP TABLE IF EXISTS client_set_decoders CASCADE;
DROP TABLE IF EXISTS client_boxes CASCADE;
DROP TABLE IF EXISTS client_products CASCADE;
DROP TABLE IF EXISTS client_weight_config CASCADE;
DROP TABLE IF EXISTS client_courier_mappings CASCADE;
DROP TABLE IF EXISTS client_column_mappings CASCADE;
DROP TABLE IF EXISTS client_settings CASCADE;
DROP TABLE IF EXISTS client_ui_settings CASCADE;
DROP TABLE IF EXISTS clients CASCADE;
DROP TABLE IF EXISTS groups CASCADE;
-- Legacy stub tables (pre-migration names)
DROP TABLE IF EXISTS client_ui_config CASCADE;
DROP TABLE IF EXISTS client_shopify_config CASCADE;
DROP TABLE IF EXISTS client_groups CASCADE;

-- ── Root entity ────────────────────────────────────────────────────────────
CREATE TABLE clients (
    client_id   TEXT PRIMARY KEY,
    client_name TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now(),
    created_by  TEXT
);

-- ── shopify_config.settings ────────────────────────────────────────────────
CREATE TABLE client_settings (
    client_id             TEXT PRIMARY KEY REFERENCES clients(client_id) ON DELETE CASCADE,
    low_stock_threshold   INT  DEFAULT 5,
    stock_csv_delimiter   TEXT DEFAULT ',',
    orders_csv_delimiter  TEXT DEFAULT ',',
    repeat_detection_days INT  DEFAULT 30,
    default_printer       TEXT,
    updated_at            TIMESTAMPTZ DEFAULT now()
);

-- ── shopify_config.column_mappings.{orders,stock} ─────────────────────────
CREATE TABLE client_column_mappings (
    id             SERIAL PRIMARY KEY,
    client_id      TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    mapping_type   TEXT NOT NULL CHECK (mapping_type IN ('orders', 'stock')),
    external_field TEXT NOT NULL,
    internal_field TEXT NOT NULL,
    UNIQUE (client_id, mapping_type, external_field)
);

-- ── shopify_config.courier_mappings ───────────────────────────────────────
CREATE TABLE client_courier_mappings (
    id             SERIAL PRIMARY KEY,
    client_id      TEXT  NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    courier_name   TEXT  NOT NULL,
    patterns       TEXT[] NOT NULL DEFAULT '{}',
    case_sensitive BOOL   NOT NULL DEFAULT false,
    UNIQUE (client_id, courier_name)
);

-- ── shopify_config.rules / order_rules (deeply nested → kept as JSONB) ────
CREATE TABLE client_rules (
    id              SERIAL PRIMARY KEY,
    client_id       TEXT  NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    rule_definition JSONB NOT NULL,
    display_order   INT   NOT NULL DEFAULT 0
);

-- ── shopify_config.tag_categories ─────────────────────────────────────────
CREATE TABLE client_tag_categories (
    id                   SERIAL PRIMARY KEY,
    client_id            TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    category_key         TEXT NOT NULL,
    label                TEXT NOT NULL,
    color                TEXT NOT NULL DEFAULT '#9E9E9E',
    display_order        INT  NOT NULL DEFAULT 999,
    sku_writeoff_enabled BOOL NOT NULL DEFAULT false,
    UNIQUE (client_id, category_key)
);

CREATE TABLE client_tags (
    id          SERIAL PRIMARY KEY,
    category_id INT  NOT NULL REFERENCES client_tag_categories(id) ON DELETE CASCADE,
    tag_name    TEXT NOT NULL,
    UNIQUE (category_id, tag_name)
);

CREATE TABLE client_tag_sku_mappings (
    id          SERIAL PRIMARY KEY,
    category_id INT  NOT NULL REFERENCES client_tag_categories(id) ON DELETE CASCADE,
    sku         TEXT NOT NULL,
    tag_name    TEXT NOT NULL,
    UNIQUE (category_id, sku)
);

-- ── shopify_config.set_decoders ───────────────────────────────────────────
CREATE TABLE client_set_decoders (
    id            SERIAL PRIMARY KEY,
    client_id     TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    set_sku       TEXT NOT NULL,
    component_sku TEXT NOT NULL,
    quantity      INT  NOT NULL DEFAULT 1,
    UNIQUE (client_id, set_sku, component_sku)
);

-- ── shopify_config.weight_config ──────────────────────────────────────────
CREATE TABLE client_weight_config (
    client_id          TEXT PRIMARY KEY REFERENCES clients(client_id) ON DELETE CASCADE,
    volumetric_divisor INT NOT NULL DEFAULT 6000
);

CREATE TABLE client_products (
    id        SERIAL PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    sku       TEXT NOT NULL,
    weight_kg NUMERIC(10, 4),
    length_cm NUMERIC(10, 4),
    width_cm  NUMERIC(10, 4),
    height_cm NUMERIC(10, 4),
    UNIQUE (client_id, sku)
);

CREATE TABLE client_boxes (
    id        SERIAL PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    name      TEXT NOT NULL,
    weight_kg NUMERIC(10, 4),
    length_cm NUMERIC(10, 4),
    width_cm  NUMERIC(10, 4),
    height_cm NUMERIC(10, 4),
    UNIQUE (client_id, name)
);

-- ── shopify_config.sku_label_config ───────────────────────────────────────
CREATE TABLE client_sku_labels (
    id         SERIAL PRIMARY KEY,
    client_id  TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    sku        TEXT NOT NULL,
    label_name TEXT NOT NULL,
    UNIQUE (client_id, sku)
);

-- ── shopify_config.packing_list_configs + stock_export_configs ────────────
-- Kept as JSONB: complex generator configs with many optional fields
CREATE TABLE client_packing_configs (
    client_id            TEXT PRIMARY KEY REFERENCES clients(client_id) ON DELETE CASCADE,
    packing_list_configs JSONB NOT NULL DEFAULT '[]',
    stock_export_configs JSONB NOT NULL DEFAULT '[]',
    updated_at           TIMESTAMPTZ DEFAULT now()
);

-- ── groups.json ───────────────────────────────────────────────────────────
CREATE TABLE groups (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    color         TEXT NOT NULL DEFAULT '#2196F3',
    display_order INT  NOT NULL DEFAULT 0,
    collapsible   BOOL NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

-- ── client_config.json ui_settings ────────────────────────────────────────
-- table_view stays JSONB: deeply nested per-view column config
CREATE TABLE client_ui_settings (
    client_id     TEXT PRIMARY KEY REFERENCES clients(client_id) ON DELETE CASCADE,
    is_pinned     BOOL         NOT NULL DEFAULT false,
    group_id      TEXT         REFERENCES groups(id) ON DELETE SET NULL,
    custom_color  TEXT,
    custom_badges TEXT[]       DEFAULT '{}',
    display_order INT          DEFAULT 0,
    table_view    JSONB        DEFAULT '{}',
    last_accessed TIMESTAMPTZ
);

-- ── session_info.json ─────────────────────────────────────────────────────
CREATE TABLE sessions (
    id                      SERIAL PRIMARY KEY,
    client_id               TEXT  NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    session_name            TEXT  NOT NULL,
    status                  TEXT  NOT NULL DEFAULT 'active'
                                CHECK (status IN ('active', 'completed', 'abandoned', 'archived')),
    pc_name                 TEXT,
    analysis_completed      BOOL  NOT NULL DEFAULT false,
    orders_file             TEXT,
    stock_file              TEXT,
    packing_lists_generated TEXT[] DEFAULT '{}',
    stock_exports_generated TEXT[] DEFAULT '{}',
    total_orders            INT    DEFAULT 0,
    total_items             INT    DEFAULT 0,
    packing_lists_count     INT    DEFAULT 0,
    packing_list_names      TEXT[] DEFAULT '{}',
    comments                TEXT   DEFAULT '',
    created_at              TIMESTAMPTZ DEFAULT now(),
    last_modified           TIMESTAMPTZ DEFAULT now(),
    status_updated_at       TIMESTAMPTZ,
    UNIQUE (client_id, session_name)
);

-- ── global_stats.json → event tables ─────────────────────────────────────
CREATE TABLE analysis_events (
    id           SERIAL PRIMARY KEY,
    client_id    TEXT  NOT NULL REFERENCES clients(client_id),
    session_name TEXT  NOT NULL,
    orders_count INT   NOT NULL DEFAULT 0,
    metadata     JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE packing_events (
    id           SERIAL PRIMARY KEY,
    client_id    TEXT  NOT NULL REFERENCES clients(client_id),
    session_name TEXT  NOT NULL,
    worker_id    TEXT,
    orders_count INT   NOT NULL DEFAULT 0,
    items_count  INT   NOT NULL DEFAULT 0,
    metadata     JSONB NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE label_print_events (
    id         SERIAL PRIMARY KEY,
    client_id  TEXT NOT NULL REFERENCES clients(client_id),
    sku        TEXT NOT NULL,
    copies     INT  NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- ── Indexes ────────────────────────────────────────────────────────────────
CREATE INDEX idx_col_mappings_client   ON client_column_mappings(client_id);
CREATE INDEX idx_courier_client        ON client_courier_mappings(client_id);
CREATE INDEX idx_rules_client          ON client_rules(client_id);
CREATE INDEX idx_tag_categories_client ON client_tag_categories(client_id);
CREATE INDEX idx_set_decoders_client   ON client_set_decoders(client_id);
CREATE INDEX idx_products_client       ON client_products(client_id);
CREATE INDEX idx_boxes_client          ON client_boxes(client_id);
CREATE INDEX idx_sku_labels_client     ON client_sku_labels(client_id);
CREATE INDEX idx_sessions_client       ON sessions(client_id);
CREATE INDEX idx_sessions_created      ON sessions(created_at DESC);
CREATE INDEX idx_analysis_client       ON analysis_events(client_id);
CREATE INDEX idx_analysis_created      ON analysis_events(created_at DESC);
CREATE INDEX idx_packing_client        ON packing_events(client_id);
CREATE INDEX idx_packing_created       ON packing_events(created_at DESC);
CREATE INDEX idx_labels_client         ON label_print_events(client_id);
CREATE INDEX idx_labels_created        ON label_print_events(created_at DESC);

COMMIT;
