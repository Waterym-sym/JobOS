-- ADR-013 comparison contract only; NEVER execute this file.
-- Executable migration belongs in migrations/versions and must support downgrade.
-- capture_source is the only shared recruitment-platform catalog in current schema.

CREATE TABLE account_user (
  id uuid PRIMARY KEY,
  email text NOT NULL UNIQUE,
  password_hash text NOT NULL,
  role text NOT NULL CHECK (role IN ('seeker', 'recruiter')),
  is_admin boolean NOT NULL DEFAULT false,
  display_name text NOT NULL,
  created_at timestamptz NOT NULL,
  deleted_at timestamptz
);

CREATE TABLE account_session (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES account_user(id),
  token_hash text NOT NULL UNIQUE,
  csrf_hash text NOT NULL,
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL
);

CREATE TABLE account_invite (
  id uuid PRIMARY KEY,
  token_hash text NOT NULL UNIQUE,
  role text NOT NULL CHECK (role IN ('seeker', 'recruiter')),
  created_by uuid NOT NULL REFERENCES account_user(id),
  expires_at timestamptz NOT NULL,
  used_at timestamptz
);

CREATE TABLE account_reset (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES account_user(id),
  token_hash text NOT NULL UNIQUE,
  created_by uuid NOT NULL REFERENCES account_user(id),
  expires_at timestamptz NOT NULL,
  used_at timestamptz
);

CREATE TABLE account_profile (
  user_id uuid PRIMARY KEY REFERENCES account_user(id),
  basic_json jsonb NOT NULL DEFAULT '{}',
  education_json jsonb NOT NULL DEFAULT '{}',
  preference_json jsonb NOT NULL DEFAULT '{}',
  onboarding_step text NOT NULL DEFAULT 'entry',
  updated_at timestamptz NOT NULL
);

CREATE TABLE resume_file (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES account_user(id),
  filename text NOT NULL,
  content_type text NOT NULL,
  storage_key text NOT NULL UNIQUE,
  sha256 text NOT NULL,
  status text NOT NULL DEFAULT 'stored',
  created_at timestamptz NOT NULL
);

-- Add owner_user_id to batch_run, raw_job, raw_company, shortlist,
-- screening_entry and ws_event_inbox; then scope existing unique constraints
-- and every query by the authenticated user. Existing rows are unassigned until
-- the server-side first-admin bootstrap transaction claims them. The deployment
-- gate rejects any unassigned private row. RLS is a second boundary; the normal
-- runtime DB role must not be superuser or BYPASSRLS.
