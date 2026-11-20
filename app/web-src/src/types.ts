export type SourceType = "peer_reviewed" | "grey" | "web" | "unknown";

export interface ResearchQuestion {
  question: string;
  why: string;
}

export interface Theme {
  name: string;
  keywords_en: string[];
  keywords_other: string[];
  sources: string[];
}

export interface Viewpoint {
  label: string;
  description: string;
  proponents: string[];
}

export interface Deliverable {
  template: string;
  sections: string[];
  length_words: number;
  tone: string;
  citation_style: "numeric" | "author-year";
  bibtex: boolean;
  max_rounds: number;
  cost_cap_usd: number;
}

export interface Brief {
  title: string;
  topic: string;
  disciplines: string[];
  year_from: number | null;
  year_to: number | null;
  geography: string;
  lit_languages: string[];
  output_language: string;
  rqs: ResearchQuestion[];
  themes: Theme[];
  include_peer_reviewed: boolean;
  include_grey: boolean;
  exclude_terms: string[];
  min_sources: number;
  max_candidates: number;
  max_fetches: number;
  viewpoints: Viewpoint[];
  deliverable: Deliverable;
  checkpoints: { candidates: boolean; outline: boolean; review: boolean };
  sources_enabled: string[];
}

export interface ProjectMeta {
  slug: string;
  title: string;
  created_at: string;
  updated_at: string;
  status: "draft" | "ready" | "running" | "done";
  sources?: number;
  last_run?: RunState | null;
}

export interface Paper {
  id: string;
  title: string;
  authors: string[];
  year: number | null;
  venue: string;
  doi: string | null;
  url: string | null;
  source: string;
  source_type: SourceType;
  full_text: string;
  abstract: string;
  verified: "yes" | "no" | "mismatch" | "unchecked";
  verification_note: string;
  evidence_count?: number;
}

export interface Checkpoint {
  kind: "candidates" | "outline" | "review";
  summary: string;
  data: Record<string, unknown>;
}

export interface RunState {
  run_id: string;
  started_at: string;
  finished_at: string | null;
  phase: string;
  status: "running" | "waiting" | "done" | "failed" | "cancelled";
  checkpoint: Checkpoint | null;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  error: string | null;
  provider: string;
  model: string;
  rounds: number;
}

export interface RunEvent {
  ts: string;
  phase: string;
  kind: string;
  message: string;
  data: Record<string, unknown>;
}

export interface AgentSection {
  heading: string;
  body: string;
}

export interface AgentFile {
  agent_id: string;
  meta: Record<string, unknown>;
  preamble: string;
  sections: AgentSection[];
  raw: string;
  parse_warnings: string[];
  contract: string;
  contract_title: string;
  revisions?: string[];
}

export interface Finding {
  severity: "blocker" | "major" | "minor" | "info";
  target: "researcher" | "author" | "none";
  location: string;
  issue: string;
  suggestion: string;
}

export interface Ledger {
  verdict: "pass" | "unverified" | "fail";
  citations_total: number;
  citations_resolved: number;
  missing: string[];
  paragraphs_without_citation: string[];
  quote_checks: number;
  quote_mismatches: string[];
  page_mismatches: string[];
  sections_required: string[];
  sections_missing: string[];
  viewpoints_required: string[];
  viewpoints_covered: string[];
  sources_total: number;
  sources_peer_reviewed: number;
  sources_grey: number;
  sources_doi_verified: number;
}

export interface Report {
  run_id: string;
  finished_at: string;
  provider: string;
  model: string;
  calls: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  ledger: Ledger;
  findings: Finding[];
  validation: { id: string; doi: string; status: string; note: string }[];
  warnings: string[];
}

export interface Settings {
  provider: string;
  model: string;
  base_url: string;
  temperature: number;
  max_output_tokens: number;
  timeout_seconds: number;
  ui_language: string;
  workspace: string;
  contact_email: string;
  has_api_key: boolean;
  secret_backend: string;
  openalex_key_set: boolean;
  default_cost_cap_usd: number;
}

export interface ProviderPreset {
  label: string;
  base_url: string;
  default_model: string;
}

export interface SourceReport {
  name: string;
  calls: number;
  hits: number;
  status: number | null;
  seconds: number;
  errors: string[];
}

export interface Diagnosis {
  queries: { theme: string; query: string }[];
  sources: SourceReport[];
  hits: number;
  filtered_out: number;
  filters: string;
  warnings: string[];
  explanation: string;
  examples: { title: string; year: number | null; venue: string; doi: string | null; source: string }[];
}

export interface ProjectDetail {
  meta: ProjectMeta;
  brief: Brief;
  brief_md: string;
  workplan_md: string;
  papers: Paper[];
  evidence_count: number;
  runs: RunState[];
}
