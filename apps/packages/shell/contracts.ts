/** Auto-generated from src/apps/contracts — do not edit by hand. */
/* eslint-disable */

// JSON Schema for PrepCardPayload
export type PrepCardPayload = {
  entity: {
  name: string;
  path: string;
  entity_type?: string | null;
  aliases?: Array<string>;
  agent_context?: string | null;
  org_id?: string | null;
};
  resolution: {
  matched: boolean;
  confidence?: 'exact' | 'fuzzy' | 'none';
  query: string;
  message?: string | null;
};
  staleness: {
  last_touch?: string | null;
  days_ago?: number | null;
  band?: 'fresh' | 'aging' | 'stale' | null;
  note_path?: string | null;
  note_title?: string | null;
};
  open_questions?: Array<{
  text: string;
  source_note?: string | null;
}>;
  commitments?: Array<{
  text: string;
  due?: string | null;
  overdue?: boolean;
  source_note?: string | null;
}>;
  connections?: Array<{
  name: string;
  entity_type?: string | null;
  edge?: string | null;
  path?: string | null;
}>;
  recent?: Array<{
  date?: string | null;
  title: string;
  type?: string | null;
  path?: string | null;
}>;
  gaps?: Array<string>;
  scope?: string;
};

// JSON Schema for LintQueuePayload
export type LintQueuePayload = {
  scope: string;
  health: {
  notes?: number;
  entities?: number;
  edges?: number;
  orphan_entities?: number;
  broken_links?: number;
  alias_collisions?: number;
};
  findings?: Array<{
  id: string;
  category: string;
  severity?: 'high' | 'medium' | 'low';
  note_path: string;
  detail: string;
  auto_fixable?: boolean;
  proposed_fix?: {
  kind: string;
  before: string;
  after: string;
} | null;
}>;
};

// JSON Schema for LintApplyResult
export type LintApplyResult = {
  applied?: Array<string>;
  skipped?: Array<{

}>;
  stale?: Array<string>;
};

// JSON Schema for SnapshotGridPayload
export type SnapshotGridPayload = {
  tolerance_days?: number;
  metric_keys?: Array<string>;
  orgs?: Array<{
  org_id: string;
  display_name: string;
  engagements?: Array<{
  path: string;
  engagement_date: string;
  engagement_type?: string | null;
  customer_status?: 'prospect' | 'existing' | null;
  windows?: Array<{
  offset: number;
  target_date: string;
  status: 'present' | 'missing' | 'out_of_tolerance';
  snapshot?: {
  date?: string | null;
  mode?: 'live' | 'reconstructed' | null;
  source?: string | null;
  metrics?: {

};
} | null;
}>;
}>;
}>;
  blocked?: Array<{
  path: string;
  reason: string;
}>;
};

// JSON Schema for DebriefFormPayload
export type DebriefFormPayload = {
  date: string;
  customer: {
  query?: string | null;
  resolved?: boolean;
  candidates?: Array<{

}>;
  path?: string | null;
  org_id?: string | null;
};
  entity_gaps?: Array<{
  name: string;
  entity_type: string;
  exists: boolean;
  will_create?: boolean;
  employer?: string | null;
  collision?: string | null;
}>;
  parent_engagements?: Array<{
  path: string;
  title: string;
  engagement_type?: string | null;
  trial_end?: string | null;
}>;
  vocab?: {
  event_types?: Array<string>;
  touchpoint_types?: Array<string>;
  engagement_types?: Array<string>;
  signals?: Array<{
  id: string;
  label: string;
}>;
};
  ontology_version?: string;
  scope?: string;
};

// JSON Schema for TriageBoardPayload
export type TriageBoardPayload = {
  counts: {
  thought?: number;
  post?: number;
  excerpt?: number;
  total?: number;
};
  oldest_days?: number | null;
  items?: Array<{
  path: string;
  title: string;
  capture_type?: string | null;
  spark?: string | null;
  source?: string | null;
  captured?: string | null;
  age_days?: number | null;
  excerpt?: string | null;
  suggested_scope?: string | null;
  gaps?: Array<string>;
}>;
  scopes?: Array<string>;
  target_types?: Array<string>;
};
