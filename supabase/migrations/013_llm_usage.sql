-- Per-call LLM usage log. One row per HTTP request (success OR failure).
-- Lets us report real cost per run, per stage, per episode, and per model.

CREATE TABLE IF NOT EXISTS llm_usage (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at           timestamptz NOT NULL DEFAULT now(),
    episode_id           uuid REFERENCES episodes(id) ON DELETE CASCADE,
    stage                text NOT NULL,
    provider             text NOT NULL,
    model                text NOT NULL,
    request_id           text,
    prompt_tokens        integer NOT NULL DEFAULT 0,
    completion_tokens    integer NOT NULL DEFAULT 0,
    reasoning_tokens     integer NOT NULL DEFAULT 0,
    cached_input_tokens  integer NOT NULL DEFAULT 0,
    total_tokens         integer NOT NULL DEFAULT 0,
    cost_usd             numeric(14, 10) NOT NULL DEFAULT 0,
    status_code          integer NOT NULL,
    finish_reason        text,
    duration_ms          integer,
    error                text,
    raw_usage            jsonb
);

CREATE INDEX IF NOT EXISTS llm_usage_episode_idx
    ON llm_usage(episode_id);

CREATE INDEX IF NOT EXISTS llm_usage_created_idx
    ON llm_usage(created_at DESC);

CREATE INDEX IF NOT EXISTS llm_usage_stage_idx
    ON llm_usage(stage);
