-- Supervisor configurations (templates)
CREATE TABLE supervisors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    base_instruction TEXT NOT NULL,
    available_actions TEXT[] DEFAULT ARRAY[
        'message_fulfillment_team',
        'message_payments_team',
        'message_logistics_team',
        'message_customer',
        'create_internal_note'
    ],
    default_wake_interval_minutes INTEGER DEFAULT 2,
    wake_aggressiveness TEXT DEFAULT 'normal',
    model TEXT DEFAULT 'claude-haiku-4-5-20251001',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Order runs
CREATE TABLE runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supervisor_id UUID REFERENCES supervisors(id),
    order_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    wake_at TIMESTAMPTZ,
    state_summary TEXT DEFAULT '',
    additional_instructions TEXT DEFAULT '',
    final_output JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Single activity log for everything
CREATE TABLE activity_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES runs(id),
    entry_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Default supervisor template
INSERT INTO supervisors (name, base_instruction, wake_aggressiveness)
VALUES (
    'Standard Order Supervisor',
    'You are an AI supervisor monitoring an e-commerce order. Your job is to watch the order lifecycle, decide when action is needed, and execute appropriate actions. Be proactive about problems like payment failures, shipment delays, or customer messages. When things are progressing normally, sleep and check back later. Always explain your reasoning before acting.',
    'normal'
);
