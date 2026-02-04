-- ============================================
-- LIA DELIVERY AGENT v2.0
-- Migration: 001_initial_schema
-- Date: 2025-02-03
-- ============================================

-- Extensões necessárias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "unaccent";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================
-- FUNÇÕES AUXILIARES
-- ============================================

-- Função para gerar fingerprint (busca de produtos)
CREATE OR REPLACE FUNCTION make_fingerprint(text_input TEXT)
RETURNS TEXT AS $$
BEGIN
    RETURN lower(regexp_replace(unaccent(COALESCE(text_input, '')), '[^a-z0-9]', '', 'g'));
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Função para normalizar telefone brasileiro
CREATE OR REPLACE FUNCTION normalize_phone(phone TEXT)
RETURNS TEXT AS $$
DECLARE
    digits TEXT;
BEGIN
    digits := regexp_replace(COALESCE(phone, ''), '\D', '', 'g');
    digits := ltrim(digits, '0');
    IF length(digits) > 0 AND NOT digits LIKE '55%' THEN
        digits := '55' || digits;
    END IF;
    RETURN digits;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Trigger para atualizar updated_at automaticamente
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- TABELA: tenants (Multi-restaurante)
-- ============================================
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    
    -- Evolution API (WhatsApp)
    evolution_instance TEXT NOT NULL,
    evolution_base_url TEXT,
    evolution_api_key TEXT,
    
    -- Saipos (PDV)
    saipos_cod_store TEXT,
    saipos_display_id TEXT,
    saipos_partner_id TEXT,
    saipos_partner_secret TEXT,
    saipos_token TEXT,
    saipos_token_expires_at TIMESTAMPTZ,
    
    -- Google Maps
    google_maps_api_key TEXT,
    delivery_city TEXT DEFAULT 'Itajaí',
    delivery_state TEXT DEFAULT 'SC',
    delivery_country TEXT DEFAULT 'BR',
    
    -- Configurações gerais (JSONB para flexibilidade)
    config JSONB DEFAULT '{
        "pix_cnpj": null,
        "metodos_pagamento": ["dinheiro", "cartao_credito", "cartao_debito", "pix"],
        "horario_funcionamento": {
            "seg": {"abertura": "18:00", "fechamento": "23:00"},
            "ter": {"abertura": "18:00", "fechamento": "23:00"},
            "qua": {"abertura": "18:00", "fechamento": "23:00"},
            "qui": {"abertura": "18:00", "fechamento": "23:00"},
            "sex": {"abertura": "18:00", "fechamento": "23:30"},
            "sab": {"abertura": "18:00", "fechamento": "00:00"},
            "dom": {"abertura": "18:00", "fechamento": "23:00"}
        },
        "tempo_estimado_entrega_min": 45,
        "tempo_estimado_retirada_min": 30,
        "pedido_minimo": 0,
        "aceita_troco": true
    }',
    
    -- Prompts customizados (NULL = usa padrão do sistema)
    prompt_agent TEXT,
    prompt_followup TEXT,
    
    -- Status
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TRIGGER trg_tenants_updated_at 
    BEFORE UPDATE ON tenants 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- TABELA: clients (Clientes)
-- ============================================
CREATE TABLE clients (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Identificação
    phone TEXT NOT NULL,
    phone_normalized TEXT NOT NULL,
    name TEXT,
    email TEXT,
    cpf_cnpj TEXT,
    birthday DATE,
    
    -- Métricas calculadas
    total_orders INTEGER DEFAULT 0,
    total_spent NUMERIC(12,2) DEFAULT 0,
    avg_ticket NUMERIC(12,2) DEFAULT 0,
    
    -- Timestamps
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_order_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(tenant_id, phone_normalized)
);

CREATE INDEX idx_clients_phone ON clients(phone_normalized);
CREATE INDEX idx_clients_tenant ON clients(tenant_id);

CREATE TRIGGER trg_clients_updated_at 
    BEFORE UPDATE ON clients 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- TABELA: addresses (Endereços dos clientes)
-- ============================================
CREATE TABLE addresses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    
    -- Endereço
    street TEXT,
    number TEXT,
    complement TEXT,
    district TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    
    -- Geocoding (Google Maps)
    latitude NUMERIC(10,8),
    longitude NUMERIC(11,8),
    formatted_address TEXT,
    place_id TEXT,
    
    -- Controle
    fingerprint TEXT,
    is_primary BOOLEAN DEFAULT false,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_addresses_client ON addresses(client_id);
CREATE UNIQUE INDEX idx_addresses_dedup ON addresses(client_id, fingerprint) WHERE fingerprint IS NOT NULL;

-- ============================================
-- TABELA: delivery_areas (Taxas de entrega por bairro)
-- ============================================
CREATE TABLE delivery_areas (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    district TEXT NOT NULL,
    city TEXT NOT NULL,
    delivery_fee NUMERIC(10,2) NOT NULL,
    estimated_time_min INTEGER DEFAULT 45,
    
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(tenant_id, district, city)
);

CREATE INDEX idx_delivery_areas_lookup ON delivery_areas(tenant_id, city, district) 
    WHERE is_active = true;

-- ============================================
-- TABELA: menu_items (Cardápio)
-- ============================================
CREATE TABLE menu_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    
    -- Identificação (códigos do Saipos)
    pdv_code TEXT NOT NULL,
    parent_pdv_code TEXT,
    
    -- Dados do item
    name TEXT NOT NULL,
    category TEXT,
    description TEXT,
    price NUMERIC(10,2) NOT NULL DEFAULT 0,
    
    -- Tipo: 'product' (prato principal) ou 'addition' (adicional)
    item_type TEXT NOT NULL DEFAULT 'product',
    
    -- Busca otimizada
    fingerprint TEXT,
    name_normalized TEXT,
    search_tokens TSVECTOR,
    
    -- Sync com Saipos
    saipos_store_item_id BIGINT,
    saipos_data JSONB,
    
    -- Disponibilidade
    is_available BOOLEAN DEFAULT true,
    
    -- Timestamps
    synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(tenant_id, pdv_code)
);

CREATE INDEX idx_menu_tenant_available ON menu_items(tenant_id) WHERE is_available = true;
CREATE INDEX idx_menu_parent ON menu_items(tenant_id, parent_pdv_code) WHERE parent_pdv_code IS NOT NULL;
CREATE INDEX idx_menu_fingerprint ON menu_items(tenant_id, fingerprint);
CREATE INDEX idx_menu_category ON menu_items(tenant_id, category) WHERE is_available = true;
CREATE INDEX idx_menu_search ON menu_items USING GIN(search_tokens);
CREATE INDEX idx_menu_trgm ON menu_items USING GIN(name_normalized gin_trgm_ops);

CREATE TRIGGER trg_menu_items_updated_at 
    BEFORE UPDATE ON menu_items 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Trigger para popular campos de busca automaticamente
CREATE OR REPLACE FUNCTION menu_items_search_trigger()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fingerprint := make_fingerprint(NEW.name);
    NEW.name_normalized := lower(unaccent(NEW.name));
    NEW.search_tokens := to_tsvector('portuguese', COALESCE(NEW.name, '') || ' ' || COALESCE(NEW.category, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_menu_items_search 
    BEFORE INSERT OR UPDATE ON menu_items 
    FOR EACH ROW EXECUTE FUNCTION menu_items_search_trigger();

-- ============================================
-- TABELA: sessions (Conversas ativas)
-- ============================================
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id),
    
    -- Identificação (telefone normalizado)
    session_id TEXT NOT NULL,
    
    -- Estado da Máquina de Estados Finita (FSM)
    fsm_state TEXT NOT NULL DEFAULT 'GREETING',
    fsm_state_data JSONB DEFAULT '{}',
    fsm_state_changed_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Carrinho de compras
    cart JSONB DEFAULT '{"itens": [], "pendencias": []}',
    cart_updated_at TIMESTAMPTZ,
    
    -- Dados coletados durante a conversa
    collected_data JSONB DEFAULT '{}',
    
    -- Última mensagem
    last_message TEXT,
    last_message_type TEXT,
    last_message_id TEXT,
    last_message_at TIMESTAMPTZ,
    
    -- Follow-up (retomada de conversa abandonada)
    followup_count INTEGER DEFAULT 0,
    followup_sent_at TIMESTAMPTZ,
    
    -- Métricas da sessão
    message_count INTEGER DEFAULT 0,
    llm_call_count INTEGER DEFAULT 0,
    total_input_tokens INTEGER DEFAULT 0,
    total_output_tokens INTEGER DEFAULT 0,
    
    -- Status: 'active' | 'completed' | 'abandoned' | 'error'
    status TEXT NOT NULL DEFAULT 'active',
    completed_at TIMESTAMPTZ,
    completion_reason TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(tenant_id, session_id, status)
);

CREATE INDEX idx_sessions_active ON sessions(tenant_id, status, updated_at DESC) 
    WHERE status = 'active';
CREATE INDEX idx_sessions_followup ON sessions(tenant_id, updated_at, followup_sent_at) 
    WHERE status = 'active';
CREATE INDEX idx_sessions_client ON sessions(client_id);

CREATE TRIGGER trg_sessions_updated_at 
    BEFORE UPDATE ON sessions 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Constraint para estados FSM válidos
ALTER TABLE sessions ADD CONSTRAINT valid_fsm_state CHECK (
    fsm_state IN (
        'GREETING',
        'COLLECTING_ITEMS',
        'CONFIRMING_ITEMS',
        'RESOLVING_PENDING',
        'COLLECTING_DELIVERY_TYPE',
        'COLLECTING_ADDRESS',
        'CONFIRMING_ADDRESS',
        'COLLECTING_PAYMENT',
        'COLLECTING_PAYMENT_DETAILS',
        'AWAITING_PIX_PROOF',
        'CONFIRMING_ORDER',
        'ORDER_SENT',
        'CANCELLED'
    )
);

-- ============================================
-- TABELA: messages (Histórico de mensagens)
-- ============================================
CREATE TABLE messages (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    
    -- Mensagem
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    
    -- Metadados da mensagem
    message_id TEXT,
    message_type TEXT,
    
    -- Se for tool call
    tool_name TEXT,
    tool_input JSONB,
    tool_output JSONB,
    tool_error TEXT,
    
    -- Métricas
    input_tokens INTEGER,
    output_tokens INTEGER,
    latency_ms INTEGER,
    
    -- FSM state no momento da mensagem
    fsm_state TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_session ON messages(session_id, created_at DESC);
CREATE INDEX idx_messages_role ON messages(session_id, role);

-- Constraint para roles válidos
ALTER TABLE messages ADD CONSTRAINT valid_role CHECK (
    role IN ('human', 'ai', 'system', 'tool')
);

-- ============================================
-- TABELA: message_queue (Fila de processamento)
-- ============================================
CREATE TABLE message_queue (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    
    -- Dados da mensagem
    message_id TEXT NOT NULL,
    remote_jid TEXT,
    content TEXT,
    message_type TEXT,
    raw_payload JSONB,
    message_timestamp TIMESTAMPTZ,
    
    -- Controle de processamento
    status TEXT DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    
    -- Lock para processamento concorrente
    locked_at TIMESTAMPTZ,
    locked_by TEXT,
    lock_expires_at TIMESTAMPTZ,
    
    -- Resultado
    processed_at TIMESTAMPTZ,
    error TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(tenant_id, session_id, message_id)
);

CREATE INDEX idx_queue_pending ON message_queue(tenant_id, status, priority DESC, created_at) 
    WHERE status = 'pending';
CREATE INDEX idx_queue_session ON message_queue(tenant_id, session_id, created_at DESC);

-- ============================================
-- TABELA: orders (Pedidos)
-- ============================================
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    client_id UUID NOT NULL REFERENCES clients(id),
    session_id UUID REFERENCES sessions(id),
    
    -- Identificação
    external_order_id TEXT,
    display_id TEXT,
    
    -- Tipo: 'delivery' | 'pickup'
    order_type TEXT NOT NULL,
    
    -- Endereço (se delivery)
    delivery_address JSONB,
    
    -- Valores
    subtotal NUMERIC(10,2) NOT NULL,
    delivery_fee NUMERIC(10,2) DEFAULT 0,
    discount NUMERIC(10,2) DEFAULT 0,
    total NUMERIC(10,2) NOT NULL,
    
    -- Pagamento
    payment_method TEXT,
    payment_details JSONB,
    
    -- Status do pedido
    status TEXT NOT NULL DEFAULT 'created',
    status_history JSONB DEFAULT '[]',
    
    -- Payloads Saipos
    saipos_payload JSONB,
    saipos_response JSONB,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ,
    ready_at TIMESTAMPTZ,
    dispatched_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    cancel_reason TEXT
);

CREATE INDEX idx_orders_tenant ON orders(tenant_id, created_at DESC);
CREATE INDEX idx_orders_client ON orders(client_id, created_at DESC);
CREATE INDEX idx_orders_external ON orders(tenant_id, external_order_id) WHERE external_order_id IS NOT NULL;
CREATE INDEX idx_orders_status ON orders(tenant_id, status, created_at DESC);

CREATE TRIGGER trg_orders_updated_at 
    BEFORE UPDATE ON orders 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- TABELA: order_items (Itens do pedido)
-- ============================================
CREATE TABLE order_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    
    -- Item
    pdv_code TEXT NOT NULL,
    name TEXT NOT NULL,
    item_type TEXT NOT NULL,
    
    -- Hierarquia (para adicionais)
    parent_item_id UUID REFERENCES order_items(id),
    
    -- Valores
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price NUMERIC(10,2) NOT NULL,
    total_price NUMERIC(10,2) NOT NULL,
    
    -- Observações
    notes TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_order_items_order ON order_items(order_id);

-- ============================================
-- TABELA: order_audit (Auditoria de pedidos)
-- ============================================
CREATE TABLE order_audit (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID REFERENCES tenants(id),
    session_id TEXT,
    order_id UUID REFERENCES orders(id),
    
    -- Dados para debug
    event_type TEXT NOT NULL,
    agent_payload JSONB,
    saipos_payload JSONB,
    saipos_response JSONB,
    error TEXT,
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_order_audit_session ON order_audit(session_id, created_at DESC);
CREATE INDEX idx_order_audit_order ON order_audit(order_id);

-- ============================================
-- VIEWS
-- ============================================

-- View: Cardápio para busca (com adicionais agrupados)
CREATE OR REPLACE VIEW v_menu_search AS
SELECT 
    mi.id,
    mi.tenant_id,
    mi.pdv_code,
    mi.parent_pdv_code,
    mi.name,
    mi.category,
    mi.price,
    mi.item_type,
    mi.fingerprint,
    mi.name_normalized,
    mi.is_available,
    CASE 
        WHEN mi.item_type = 'product' THEN (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'pdv_code', a.pdv_code,
                    'name', a.name,
                    'price', a.price,
                    'fingerprint', a.fingerprint
                ) ORDER BY a.name
            )
            FROM menu_items a 
            WHERE a.parent_pdv_code = mi.pdv_code 
              AND a.tenant_id = mi.tenant_id
              AND a.is_available = true
        )
        ELSE NULL
    END as available_additions
FROM menu_items mi
WHERE mi.is_available = true;

-- View: Snapshot completo do cliente
CREATE OR REPLACE VIEW v_client_snapshot AS
SELECT 
    c.id as client_id,
    c.tenant_id,
    c.phone,
    c.phone_normalized,
    c.name,
    c.email,
    c.cpf_cnpj,
    c.birthday,
    c.total_orders,
    c.total_spent,
    c.avg_ticket,
    c.first_seen_at,
    c.last_seen_at,
    c.last_order_at,
    
    -- Endereço principal
    a.id as address_id,
    a.street,
    a.number,
    a.complement,
    a.district,
    a.city,
    a.state,
    a.postal_code,
    a.latitude,
    a.longitude,
    
    -- Último pedido
    o.id as last_order_id,
    o.external_order_id,
    o.order_type as last_order_type,
    o.payment_method as last_payment_method,
    o.total as last_order_total,
    o.status as last_order_status,
    o.created_at as last_order_created_at,
    
    -- Itens do último pedido
    (
        SELECT jsonb_agg(
            jsonb_build_object(
                'name', oi.name,
                'quantity', oi.quantity,
                'unit_price', oi.unit_price
            ) ORDER BY oi.created_at
        )
        FROM order_items oi 
        WHERE oi.order_id = o.id AND oi.item_type = 'product'
    ) as last_order_items,
    
    -- Itens favoritos (top 5)
    (
        SELECT jsonb_agg(fav ORDER BY fav->>'count' DESC)
        FROM (
            SELECT jsonb_build_object(
                'name', oi.name,
                'pdv_code', oi.pdv_code,
                'count', SUM(oi.quantity)
            ) as fav
            FROM order_items oi
            JOIN orders ord ON ord.id = oi.order_id
            WHERE ord.client_id = c.id AND oi.item_type = 'product'
            GROUP BY oi.name, oi.pdv_code
            ORDER BY SUM(oi.quantity) DESC
            LIMIT 5
        ) favorites
    ) as favorite_items

FROM clients c
LEFT JOIN LATERAL (
    SELECT * FROM addresses 
    WHERE client_id = c.id 
    ORDER BY is_primary DESC, created_at DESC 
    LIMIT 1
) a ON true
LEFT JOIN LATERAL (
    SELECT * FROM orders 
    WHERE client_id = c.id 
    ORDER BY created_at DESC 
    LIMIT 1
) o ON true;

-- View: Sessões ativas com dados do cliente
CREATE OR REPLACE VIEW v_active_sessions AS
SELECT 
    s.id,
    s.tenant_id,
    s.session_id,
    s.fsm_state,
    s.fsm_state_data,
    s.cart,
    s.collected_data,
    s.message_count,
    s.llm_call_count,
    s.status,
    s.created_at,
    s.updated_at,
    s.last_message_at,
    
    -- Dados do cliente
    c.name as client_name,
    c.total_orders as client_total_orders,
    
    -- Tempo desde última mensagem
    EXTRACT(EPOCH FROM (NOW() - s.last_message_at)) / 60 as minutes_since_last_message
FROM sessions s
LEFT JOIN clients c ON c.id = s.client_id
WHERE s.status = 'active';

-- ============================================
-- SEED DATA: Tenant inicial (Marcio Lanches)
-- ============================================
INSERT INTO tenants (slug, name, evolution_instance, delivery_city, delivery_state, config)
VALUES (
    'marcio-lanches',
    'Marcio Lanches & Pizzas',
    'Lia',
    'Itajaí',
    'SC',
    '{
        "pix_cnpj": "09103543000109",
        "metodos_pagamento": ["dinheiro", "cartao_credito", "cartao_debito", "pix"],
        "horario_funcionamento": {
            "seg": {"abertura": "18:00", "fechamento": "23:00"},
            "ter": {"abertura": "18:00", "fechamento": "23:00"},
            "qua": {"abertura": "18:00", "fechamento": "23:00"},
            "qui": {"abertura": "18:00", "fechamento": "23:00"},
            "sex": {"abertura": "18:00", "fechamento": "23:30"},
            "sab": {"abertura": "18:00", "fechamento": "00:00"},
            "dom": {"abertura": "18:00", "fechamento": "23:00"}
        },
        "tempo_estimado_entrega_min": 45,
        "tempo_estimado_retirada_min": 30,
        "pedido_minimo": 0,
        "aceita_troco": true
    }'::jsonb
)
ON CONFLICT (slug) DO NOTHING;

-- ============================================
-- GRANTS (RLS será configurado separadamente se necessário)
-- ============================================
-- Por padrão, Supabase usa service_role para operações backend

-- FIM DA MIGRATION 001
