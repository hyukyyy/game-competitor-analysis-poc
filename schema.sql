-- Game Competitor Analysis PoC — Postgres schema
-- Requires: CREATE EXTENSION IF NOT EXISTS vector;

CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================
-- Raw layer — 원본 보존, 재처리 가능성 확보
-- ============================================================

CREATE TABLE IF NOT EXISTS raw_games (
    id              BIGSERIAL PRIMARY KEY,
    platform        VARCHAR(32) NOT NULL,
    external_id     VARCHAR(128) NOT NULL,
    payload         JSONB NOT NULL,
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (platform, external_id, collected_at)
);
CREATE INDEX IF NOT EXISTS idx_raw_games_platform_ext ON raw_games (platform, external_id);

CREATE TABLE IF NOT EXISTS raw_reviews (
    id              BIGSERIAL PRIMARY KEY,
    platform        VARCHAR(32) NOT NULL,
    external_id     VARCHAR(128) NOT NULL,
    review_id       VARCHAR(128) NOT NULL,
    text            TEXT,
    rating          INT,
    posted_at       TIMESTAMPTZ,
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (platform, review_id)
);
CREATE INDEX IF NOT EXISTS idx_raw_reviews_game ON raw_reviews (platform, external_id);

-- ============================================================
-- Normalized layer
-- ============================================================

CREATE TABLE IF NOT EXISTS games (
    id              SERIAL PRIMARY KEY,
    platform        VARCHAR(32) NOT NULL,
    external_id     VARCHAR(128) NOT NULL,
    title           TEXT,
    description     TEXT,
    raw_tags        TEXT[],
    is_my_game      BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (platform, external_id)
);
CREATE INDEX IF NOT EXISTS idx_games_my ON games (is_my_game) WHERE is_my_game = TRUE;

-- ============================================================
-- Feature Store (SCD Type 2)
-- ============================================================

CREATE TABLE IF NOT EXISTS game_features (
    id                      SERIAL PRIMARY KEY,
    game_id                 INT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    genre                   VARCHAR(64),
    subgenre                VARCHAR(64),
    bm_dist                 JSONB,          -- {gacha:0.6, ads:0.2, premium:0.1, sub:0.1}
    play_style              TEXT[],
    session_length_minutes  FLOAT,
    core_loop               TEXT,
    feature_version         INT NOT NULL,
    valid_from              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to                TIMESTAMPTZ,    -- NULL = current
    UNIQUE (game_id, valid_from)
);
CREATE INDEX IF NOT EXISTS idx_game_features_current
    ON game_features (game_id) WHERE valid_to IS NULL;

CREATE TABLE IF NOT EXISTS game_embeddings (
    game_id                 INT PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,
    description_embedding   vector(384),
    review_embedding        vector(384),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Similarity results (weekly snapshot)
-- ============================================================

CREATE TABLE IF NOT EXISTS game_similarities_weekly (
    week_of             DATE NOT NULL,
    base_game_id        INT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    target_game_id      INT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    similarity_score    FLOAT NOT NULL,
    rank                INT NOT NULL,
    component_scores    JSONB,              -- explainability
    calculated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (week_of, base_game_id, target_game_id)
);
CREATE INDEX IF NOT EXISTS idx_similarities_base_week
    ON game_similarities_weekly (base_game_id, week_of, rank);

-- ============================================================
-- PM feedback (implicit signals → weight tuning)
-- ============================================================

CREATE TABLE IF NOT EXISTS pm_feedback (
    id              BIGSERIAL PRIMARY KEY,
    base_game_id    INT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    target_game_id  INT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    week_of         DATE NOT NULL,
    signal          VARCHAR(32) NOT NULL,   -- upvote/downvote/clicked/added
    user_id         VARCHAR(128),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_pm_feedback_base_week
    ON pm_feedback (base_game_id, week_of);

-- ============================================================
-- Caches
-- ============================================================

CREATE TABLE IF NOT EXISTS llm_cache (
    input_hash      VARCHAR(64) PRIMARY KEY,    -- sha256 hex
    model           VARCHAR(64) NOT NULL,
    output          JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    hit_count       INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS embedding_cache (
    text_hash       VARCHAR(64) PRIMARY KEY,
    model           VARCHAR(64) NOT NULL,
    embedding       vector(384) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Pipeline observability
-- ============================================================

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id              BIGSERIAL PRIMARY KEY,
    stage           VARCHAR(64) NOT NULL,       -- collector/normalizer/feature/similarity/report
    week_of         DATE NOT NULL,
    status          VARCHAR(16) NOT NULL,       -- running/success/failed
    rows_in         INT,
    rows_out        INT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_stage_week
    ON pipeline_runs (stage, week_of, started_at DESC);

-- ============================================================
-- Weekly reports
-- ============================================================

CREATE TABLE IF NOT EXISTS weekly_reports (
    id              BIGSERIAL PRIMARY KEY,
    week_of         DATE NOT NULL,
    base_game_id    INT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    content         JSONB NOT NULL,             -- {top_n, new_entrants, rank_changes, updates_summary}
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (week_of, base_game_id)
);

-- ============================================================
-- Weight history (튜닝된 가중치 이력)
-- ============================================================

CREATE TABLE IF NOT EXISTS weight_history (
    id              BIGSERIAL PRIMARY KEY,
    week_of         DATE NOT NULL,
    weights         JSONB NOT NULL,             -- {semantic, genre, tier, bm}
    ndcg_score      FLOAT,                      -- NDCG@10 on gold set
    label_count     INT,                        -- 학습에 사용된 라벨 수
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_weight_history_week
    ON weight_history (week_of DESC);

-- ============================================================
-- Weak similarities (플랫폼 "similar games" signal)
-- ============================================================

CREATE TABLE IF NOT EXISTS weak_similarities (
    base_game_id    INT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    target_game_id  INT NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    source          VARCHAR(32) NOT NULL,        -- steam_morelike / playstore_similar / tag_overlap
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (base_game_id, target_game_id, source)
);
CREATE INDEX IF NOT EXISTS idx_weak_similarities_base
    ON weak_similarities (base_game_id);
