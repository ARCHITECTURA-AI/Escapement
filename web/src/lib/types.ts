export type Obj = {
  id: string;
  name: string;
  state?: string[];
  in?: string;
  portable?: boolean;
  operations?: string[];
};

export type Event =
  | { type: "clue_discovered"; clue_id: string }
  | { type: "object_revealed"; object_id: string }
  | { type: "item_taken"; item_id: string }
  | { type: "item_consumed"; item_id: string }
  | { type: "state_changed"; object_id: string; state: string }
  | { type: "moved"; location_id: string }
  | { type: "unlocked"; object_id: string }
  | { type: "wrong_code"; object_id: string; attempts: number }
  | { type: "escaped" };

export type Result = {
  ok: boolean;
  tool: string | null;
  error: string | null;
  message: string;
  events: Event[];
  cost: number;
  malformed?: boolean;
  data?: { clues?: { id: string; text: string }[] };
};

export type Observation = {
  goal: string;
  location: { id: string; name: string; description: string };
  objects: Obj[];
  exits: { id: string; name: string }[];
  inventory: { id: string; name: string }[];
  journal_entries: number;
  actions_used: number;
  action_budget: number;
  actions_remaining: number;
  status: string;
  last_result: Result | null;
};

export type Action = { tool: string | null; arguments?: Record<string, string>; malformed?: boolean };

export type Step = {
  seq: number;
  request: unknown;
  action: Action;
  result: Result;
  observation: Observation;
  state_hash: string;
  chain_hash: string;
  status: string;
  malformed: boolean;
  system: boolean;
  elapsed_ms?: number;
  decision_summary?: string;
  usage?: Usage;
  memory?: Record<string, unknown>;
};

export type Usage = { tokens_in?: number; tokens_out?: number; cost_usd_micros?: number; model_decisions?: number };

export type Declared = {
  agent_version_id?: string;
  name?: string;
  version?: string | null;
  agent_type?: string;
  model?: string | null;
  framework?: string | null;
  memory?: string | null;
  provider?: string | null;
  model_attested?: boolean;
};

export type RoomMeta = {
  id: string;
  title: string;
  kind: string;
  tier: string;
  ranked: boolean;
  season_id: string | null;
  instance_hash: string;
  manifest_public: boolean;
  intro?: string;
  goal?: string;
  action_budget?: number;
  family_title?: string;
  date?: string;
  unlocks_at?: string;
  position?: number;
  min_length?: number;
  optimality?: string;
  malformed_limit?: number;
  locations?: number;
  wrong_code_free_attempts?: number;
  wrong_code_penalty?: number;
};

export type Replay = {
  format: string;
  run_id: string;
  engine_version: string;
  protocol_version: string;
  room: { room_id: string; title: string; tier: string; family: string; instance_hash: string; season: string | null; action_budget: number; kind?: string };
  mode: string;
  agent: Declared;
  self_reported: { note: string; usage: Usage };
  initial_observation: Observation;
  chain_start: string;
  steps: Step[];
  outcome: string;
  final_chain_hash: string;
  started_at: string | null;
  finished_at: string | null;
  wall_time_ms: number | null;
  certificate_id?: string;
};

export type RunSummary = {
  id: string;
  room: { id: string; title: string | null; tier: string | null; kind: string | null; season_id: string | null; instance_hash: string | null; manifest_public: boolean };
  mode: string;
  agent_type: string;
  agent: Declared;
  status: string;
  status_label: string;
  actions_used: number;
  action_budget: number;
  malformed_count: number;
  sequence: number;
  chain_hash: string;
  final_chain_hash: string | null;
  started_at: string;
  finished_at: string | null;
  wall_time_ms: number | null;
  usage: Usage;
  hints_used: number;
  assisted: boolean;
  certificate_id: string | null;
  engine_version: string;
  embargo_until: string | null;
  replay_visible: boolean;
  is_owner: boolean;
  views: number;
  handle?: string;
};

export type Me = {
  user: null | {
    id: string;
    handle: string;
    display_name: string | null;
    avatar_url: string | null;
    email: string | null;
    profile_public: boolean;
    created_at: string;
    is_system: boolean;
    runs: number;
    certified_runs: number;
  };
  mode: "local" | "public";
};

export type Meta = {
  mode: "local" | "public";
  engine_version: string;
  protocol_version: string;
  github_login: boolean;
  local_login: boolean;
  limits: Record<string, number>;
  tiers: Record<string, { locations: number; irrelevant_objects: number; clue_composition_depth: number; code_digits: number; action_budget: number; ranked: boolean }>;
  tools: { name: string; description: string; parameters: { properties: Record<string, unknown>; required: string[] } }[];
  failure_codes: string[];
  endings: { id: string; label: string }[];
  certificate: { proves: string; does_not_prove: string };
  support: string;
};

export type RateSummary = {
  runs: number;
  escapes: number;
  instances: number;
  rate: number | null;
  ci_low: number | null;
  ci_high: number | null;
  pass3: number | null;
  pass3_instances: number;
  median_actions_success: number | null;
  method: string;
};

export type Cost = { self_reported: boolean; runs_reporting_cost: number; median_cost_usd: number | null; median_tokens: number | null };

export type VersionPublic = {
  id: string;
  name: string;
  version: string;
  agent_type: string;
  model: string | null;
  framework: string | null;
  memory: string | null;
  provider: string | null;
  config_hash: string | null;
  self_reported: string[];
  created_at: string;
  notes: string | null;
};

export type VersionResults = {
  agent_version: VersionPublic;
  results: { mode: string; season_id: string | null; tier: string; summary: RateSummary; endings: Record<string, number>; cost: Cost }[];
  endings: Record<string, number>;
  total_runs: number;
};

export type LeaderRow = {
  agent_version_id: string | null;
  handle: string | null;
  agent: { name: string; version: string | null };
  agent_type: string;
  reference: boolean;
  model: string | null;
  provider: string | null;
  model_label: string;
  framework: string | null;
  memory: string | null;
  summary: RateSummary;
  rate_text: string;
  interval_text: string;
  endings: Record<string, number>;
  cost: Cost;
  last_run_at: string;
  stale: boolean;
  band: number;
};

export type Leaderboard = { season_id: string; tier: string; instances: number; rows: LeaderRow[]; generated_at: string; notes: string[] };

export type SeasonPublic = {
  id: string;
  name: string;
  status: "scheduled" | "open" | "ended" | "closed";
  starts_at: string;
  ends_at: string;
  released_at: string | null;
  tiers: string[];
  instances_per_tier: number;
  days_left: number;
  rules: { certified_runs_per_instance: number; budgets: Record<string, number>; embargo: string };
  instances: { id: string; title: string; tier: string; position: number; instance_hash: string; manifest_public: boolean; action_budget: number }[];
  has_report: boolean;
};

export type CertificateBody = {
  format: string;
  certificate_id: string;
  run_id: string;
  issued_at: string;
  room: { room_id: string; title: string; tier: string; kind: string; family: string; season: string | null; instance_hash: string };
  mode: string;
  engine_version: string;
  protocol_version: string;
  outcome: string;
  actions_used: number;
  action_budget: number;
  malformed_count: number;
  wall_time_ms: number;
  chain_length: number;
  final_chain_hash: string;
  run_set: { runs: number; escapes: number };
  agent: { name: string; version: string | null; agent_type: string; model: string | null; framework: string | null; memory: string | null; provider: string | null; model_attested: boolean };
  usage: { tokens_in: number | null; tokens_out: number | null; cost_usd_micros: number | null; model_decisions: number | null };
  assisted: boolean;
  self_reported_fields: string[];
  proves: string;
  does_not_prove: string;
  key_id: string;
  signature: string;
  tombstone?: boolean;
  reason?: string;
};

export type CertificatePage = {
  certificate: CertificateBody;
  revoked: boolean;
  revoked_at: string | null;
  revocation_reason: string | null;
  verification: { available: string; explanation: string; manifest_public: boolean };
  issued_at: string;
  run?: { id: string; embargo_until: string | null };
};

export type DailyBoard = {
  date: string;
  board: "humans" | "agents";
  unlocked: boolean;
  unlocks_at: string;
  participants: number;
  attempts: number;
  my_attempts: DailyRow[];
  rows: DailyRow[] | null;
  message?: string;
  assisted_excluded?: number;
};

export type DailyRow = {
  run_id: string;
  handle: string | null;
  agent: { name: string; version: string | null } | null;
  model: string | null;
  outcome: string;
  escaped: boolean;
  actions_used: number;
  wall_time_ms: number | null;
  assisted: boolean;
  hints_used: number;
  finished_at: string | null;
  rank?: number | null;
};

export type Finding = { kind: string; title: string; detail: string; steps: number[]; severity: "info" | "warn"; heuristic: boolean };
