-- =====================================================================
-- AI Resume OS / JobOS v1.1 — Baseline Schema SKELETON (v0-draft)
-- 目标库: PostgreSQL 16 + pgvector
-- 语义真源: docs/architecture/12-数据库设计.md（字段清单以此文件为准）
--
-- 警告: 本文件是 P0/P1 对账用 DDL 草案，不是最终迁移。
--   1) P1 冻结时必须与 12 篇逐字段对账后改写为首个 Alembic 迁移；
--   2) 仅包含 v1.1 新增 16 表 + 关联表；v1.0 既有表用 ALTER 注释列出新增列；
--   3) 所有表带 id/created_at/updated_at；时间一律 timestamptz（UTC）。
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector（既有 evidence 表使用）

-- ---------- 枚举 ----------
CREATE TYPE capture_kind      AS ENUM ('list', 'detail', 'chat');
CREATE TYPE batch_status      AS ENUM ('queued', 'running', 'completed', 'aborted', 'risk_halted', 'failed');
CREATE TYPE salary_unit       AS ENUM ('month_K', 'month_yuan', 'day', 'hour', 'year', 'unknown');
CREATE TYPE job_source_status AS ENUM ('draft', 'analyzing', 'ready', 'archived');
CREATE TYPE screen_verdict    AS ENUM ('pass', 'reject', 'recovered');
CREATE TYPE shortlist_status  AS ENUM ('confirmed', 'removed');
CREATE TYPE package_status    AS ENUM ('draft', 'ready', 'used');
CREATE TYPE greeting_status   AS ENUM ('generated', 'blocked', 'selected', 'used');
CREATE TYPE app_stage         AS ENUM (
  'saved', 'shortlisted', 'packaged', 'greeted', 'chat_read', 'chat_replied',
  'interview_scheduled', 'interview_done',
  'offered', 'interview_rejected', 'chat_rejected', 'withdrawn');
CREATE TYPE event_source      AS ENUM ('extension', 'manual');
CREATE TYPE review_status     AS ENUM ('draft', 'confirmed', 'rejected');
CREATE TYPE app_event_type    AS ENUM (
  'shortlisted', 'packaged', 'greeted', 'chat_read', 'chat_replied', 'chat_rejected',
  'interview_scheduled', 'interview_done', 'interview_rejected', 'offered', 'withdrawn');
CREATE TYPE msg_direction     AS ENUM ('inbound', 'outbound');
CREATE TYPE chat_msg_type     AS ENUM ('text', 'image', 'voice', 'video', 'interview', 'notify', 'article', 'action');
CREATE TYPE decode_source     AS ENUM ('network', 'dom');
CREATE TYPE template_channel  AS ENUM ('ats', 'showcase');
CREATE TYPE version_channel   AS ENUM ('ats', 'showcase', 'online');
CREATE TYPE template_source   AS ENUM ('builtin', 'docx_import', 'user_copy');
CREATE TYPE quality_grade     AS ENUM ('A', 'B', 'C');
CREATE TYPE import_status     AS ENUM ('running', 'done', 'partial');
CREATE TYPE retro_kind        AS ENUM ('single', 'stage');
CREATE TYPE strategy_scope    AS ENUM ('screen', 'greeting', 'resume', 'template');
CREATE TYPE strategy_status   AS ENUM ('proposed', 'approved', 'rejected', 'applied');

-- =====================================================================
-- 一、采集与岗位池
-- =====================================================================
CREATE TABLE capture_source (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code             text NOT NULL UNIQUE,                   -- 'boss'；业务唯一键
  display_name     text NOT NULL,
  enabled          boolean NOT NULL DEFAULT true,
  config_json      jsonb NOT NULL DEFAULT '{}'::jsonb,
  protocol_version integer NOT NULL DEFAULT 1,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE batch_run (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id    uuid NOT NULL REFERENCES capture_source(id),
  kind         capture_kind NOT NULL,
  status       batch_status NOT NULL DEFAULT 'queued',
  stats_json   jsonb NOT NULL DEFAULT '{}'::jsonb,
  risk_halted  boolean NOT NULL DEFAULT false,
  trigger      text NOT NULL DEFAULT 'manual',
  started_at   timestamptz,
  finished_at  timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE raw_job (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id       uuid NOT NULL REFERENCES capture_source(id),
  ext_id          text NOT NULL,
  batch_id        uuid REFERENCES batch_run(id),
  fingerprint     text NOT NULL,
  list_json       jsonb,
  detail_json     jsonb,
  jd_text         text,
  title           text,
  company         text,
  city            text,
  salary_text     text,
  low_salary      numeric,
  high_salary     numeric,
  salary_unit     salary_unit NOT NULL DEFAULT 'unknown',
  exp_text        text,
  degree          text,
  industry        text,
  stage           text,
  scale           text,
  address         text,
  list_tags       text[] NOT NULL DEFAULT '{}',
  skill_tags      text[] NOT NULL DEFAULT '{}',
  ats_direct_post boolean,
  boss_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
  active_time     text,
  active_at       timestamptz,
  list_at         timestamptz,
  detail_at       timestamptz,
  migrated_from   text,                                  -- 'mysql8789' 一次性迁移标记
  deleted_at      timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_id, ext_id)
);
CREATE INDEX idx_rawjob_fingerprint ON raw_job USING gin (to_tsvector('simple', fingerprint));
CREATE INDEX idx_rawjob_active_at ON raw_job (active_at);

-- 既有 job 表扩展（v1.0 已存在，冻结时以 ALTER 落迁移）:
--   ALTER TABLE job ADD COLUMN raw_job_id uuid REFERENCES raw_job(id);
--   ALTER TABLE job ADD COLUMN source text NOT NULL DEFAULT 'boss';
--   ALTER TABLE job ADD COLUMN status job_source_status NOT NULL DEFAULT 'draft';
--   ALTER TABLE job ADD COLUMN profile_revision_id uuid;

-- =====================================================================
-- 二、筛选与候选区
-- =====================================================================
CREATE TABLE filter_set (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  version     integer NOT NULL DEFAULT 1,
  rule_json   jsonb NOT NULL,   -- 形状见 contracts/filters/filter-set.schema.json
  is_default  boolean NOT NULL DEFAULT false,
  archived    boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE screen_result (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  filter_set_id   uuid NOT NULL REFERENCES filter_set(id),
  filter_version  integer NOT NULL,
  raw_job_id      uuid NOT NULL REFERENCES raw_job(id),
  batch_run_id    uuid REFERENCES batch_run(id),
  verdict         screen_verdict NOT NULL,
  reasons_json    jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{rule_id,group,field,operator,expected,actual}]
  recover_reason  text,
  screened_at     timestamptz NOT NULL DEFAULT now(),
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (filter_set_id, filter_version, raw_job_id)
);
CREATE INDEX idx_screen_verdict ON screen_result (verdict);

CREATE TABLE shortlist (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  raw_job_id      uuid NOT NULL REFERENCES raw_job(id),
  job_id          uuid,                       -- REFERENCES job(id)（既有表，冻结时补 FK）
  match_result_id uuid,                       -- REFERENCES match_result(id)
  status          shortlist_status NOT NULL DEFAULT 'confirmed',
  decided_at      timestamptz NOT NULL DEFAULT now(),
  note            text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
-- 一个岗位同批仅一条有效 confirmed（冻结时用部分唯一索引实现）

-- =====================================================================
-- 三、触达与投递
-- =====================================================================
CREATE TABLE application (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source        text NOT NULL DEFAULT 'boss',   -- boss | manual
  raw_job_id    uuid REFERENCES raw_job(id),
  job_id        uuid,                            -- REFERENCES job(id)
  current_stage app_stage NOT NULL DEFAULT 'saved',
  package_id    uuid,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE application_package (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id       uuid NOT NULL REFERENCES application(id),
  match_result_id      uuid,
  online_payload       jsonb,
  ats_version_id       uuid,                    -- REFERENCES resume_version(id)
  showcase_version_id  uuid,
  guard_run_id         uuid,
  status               package_status NOT NULL DEFAULT 'draft',
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE application ADD CONSTRAINT fk_app_package
  FOREIGN KEY (package_id) REFERENCES application_package(id);

CREATE TABLE greeting_variant (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  package_id    uuid NOT NULL REFERENCES application_package(id),
  variant_no    integer NOT NULL,
  text          text NOT NULL CHECK (char_length(text) <= 300),
  slots_json    jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence_ids  uuid[] NOT NULL DEFAULT '{}',
  length_check  jsonb NOT NULL DEFAULT '{}'::jsonb,
  risk_flags    text[] NOT NULL DEFAULT '{}',
  selected_at   timestamptz,
  status        greeting_status NOT NULL DEFAULT 'generated',
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
-- 校验：status='used' 时必须存在 evidence 或全部陈述为变量槽/自述偏好（应用层断言）

CREATE TABLE application_event (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id uuid NOT NULL REFERENCES application(id),
  type           app_event_type NOT NULL,
  source         event_source NOT NULL,
  confidence     numeric CHECK (confidence BETWEEN 0 AND 1),
  review_status  review_status NOT NULL DEFAULT 'draft',
  payload        jsonb NOT NULL DEFAULT '{}'::jsonb,
  chat_message_id uuid,                          -- REFERENCES chat_message(id)
  occurred_at    timestamptz NOT NULL DEFAULT now(),
  confirmed_at   timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_app_event_app_time ON application_event (application_id, occurred_at);

-- =====================================================================
-- 四、聊天（最高 PII：加密列 + 本机密钥）
-- =====================================================================
CREATE TABLE chat_thread (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id    uuid NOT NULL REFERENCES application(id),
  source            text NOT NULL DEFAULT 'boss',
  ext_chat_id       text NOT NULL,
  counterpart_name  text,
  job_ext_id        text,
  last_msg_at       timestamptz,
  cursor_json       jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source, ext_chat_id)
);

CREATE TABLE chat_message (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id        uuid NOT NULL REFERENCES chat_thread(id),
  ext_msg_id       text NOT NULL,
  direction        msg_direction NOT NULL,
  type             chat_msg_type NOT NULL,
  text_or_caption  text,
  structured       jsonb NOT NULL DEFAULT '{}'::jsonb,
  payload_enc      bytea,                         -- 本机 KEK 加密的原始包
  payload_enc_meta jsonb NOT NULL DEFAULT '{}'::jsonb,
  decode_source    decode_source NOT NULL,
  raw_object_key   text,
  sent_at          timestamptz NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (thread_id, ext_msg_id)
  -- 刻意不建任何到 evidence 的关联路径（12 篇硬约束）
);
CREATE INDEX idx_chat_msg_thread_time ON chat_message (thread_id, sent_at);
ALTER TABLE application_event
  ADD CONSTRAINT fk_event_chatmsg FOREIGN KEY (chat_message_id) REFERENCES chat_message(id);

-- =====================================================================
-- 五、模板子域
-- =====================================================================
CREATE TABLE resume_template (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code            text NOT NULL UNIQUE,
  name            text NOT NULL,
  channel         template_channel NOT NULL,
  layout_type     text NOT NULL CHECK (layout_type ~ '^P(0[1-9]|1[0-9]|2[0-3])$'),
  style_preset    text NOT NULL CHECK (style_preset ~ '^S(0[1-9]|[12][0-9]|3[0-4])$'),
  default_modules jsonb NOT NULL DEFAULT '[]'::jsonb,
  slot_map        jsonb NOT NULL DEFAULT '{}'::jsonb,
  tags            jsonb NOT NULL DEFAULT '[]'::jsonb,
  lang            text NOT NULL DEFAULT 'zh',
  color           text,
  columns         smallint NOT NULL DEFAULT 1,
  pages           smallint,
  license         text NOT NULL,                  -- 免费授权/自有必填；未知不允许入库
  license_note    text,
  source          template_source NOT NULL,
  quality_grade   quality_grade NOT NULL DEFAULT 'B',
  thumbnail_key   text,
  enabled         boolean NOT NULL DEFAULT true,
  version         integer NOT NULL DEFAULT 1,
  deleted_at      timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_template_tags ON resume_template USING gin (tags);

CREATE TABLE template_blueprint (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  template_id    uuid NOT NULL REFERENCES resume_template(id),
  version        integer NOT NULL DEFAULT 1,
  spec_json      jsonb NOT NULL,
  parser_engine  text NOT NULL CHECK (parser_engine IN ('openxml', 'python-docx')),
  fidelity_grade quality_grade NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE template_import_batch (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_dir    text NOT NULL,
  engine        text NOT NULL DEFAULT 'openxml',
  total         integer NOT NULL DEFAULT 0,
  succeeded     integer NOT NULL DEFAULT 0,
  failed        integer NOT NULL DEFAULT 0,
  failed_report jsonb NOT NULL DEFAULT '[]'::jsonb,
  status        import_status NOT NULL DEFAULT 'running',
  resume_cursor text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  finished_at   timestamptz
);

CREATE TABLE template_pack (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name         text NOT NULL,
  license_note text,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE template_pack_item (
  pack_id     uuid NOT NULL REFERENCES template_pack(id),
  template_id uuid NOT NULL REFERENCES resume_template(id),
  PRIMARY KEY (pack_id, template_id)
);

-- 既有 resume_version 表扩展（冻结时 ALTER）:
--   template_id uuid REFERENCES resume_template(id);
--   template_version integer;
--   render_params_json jsonb;
--   channel version_channel NOT NULL;
--   renderer_version text;
--   input_claim_hash text;
--   output_hash text;
-- 校验：channel='ats' 时其 resume_template.channel 必须为 'ats'（触发器或应用层断言）

-- =====================================================================
-- 六、复盘与策略
-- =====================================================================
CREATE TABLE retrospective (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  application_id  uuid NOT NULL REFERENCES application(id),
  kind            retro_kind NOT NULL,
  period_start    timestamptz,
  period_end      timestamptz,
  content_json    jsonb NOT NULL,
  funnel_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  model_run_id    uuid,
  version         integer NOT NULL DEFAULT 1,   -- 不可变，重跑新建 version
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE strategy_suggestion (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  retrospective_id uuid NOT NULL REFERENCES retrospective(id),
  scope            strategy_scope NOT NULL,
  content_json     jsonb NOT NULL,
  expected_effect  text,
  status           strategy_status NOT NULL DEFAULT 'proposed',
  reviewed_at      timestamptz,
  applied_note     text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_strategy_status ON strategy_suggestion (status);

-- =====================================================================
-- 待冻结备忘（P1 Alembic 迁移处理）
-- 1. 对既有 v1.0 表的 ALTER（job/application/resume_version/experience/project/
--    artifact/evidence/job_requirement/job_constraint/match_result 等，见 12 篇第七节）；
-- 2. 部分唯一索引：同岗位同批仅一条 shortlist confirmed；
-- 3. updated_at 触发器统一维护；中文全文分词配置；
-- 4. outbox/audit_log 沿用 v1.0 定义。
-- =====================================================================
