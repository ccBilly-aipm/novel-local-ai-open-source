export interface Timestamped {
  id: string;
  created_at: string;
  updated_at: string;
}

export interface Project extends Timestamped {
  name: string;
  description: string;
  novels?: Novel[];
}

export interface Novel extends Timestamped {
  project_id: string;
  title: string;
  synopsis: string;
  story_outline: string;
  style_guide: string;
  forbidden_content: string;
  status: string;
}

export interface Chapter extends Timestamped {
  novel_id: string;
  parent_id: string | null;
  order_index: number;
  title: string;
  content: string;
  summary: string;
  status: string;
  version: number;
  outline: ChapterOutline | null;
}

export interface ChapterOutline extends Timestamped {
  chapter_id: string;
  goal: string;
  outline_content: string;
  required_plot_points_json: string;
  character_ids_json: string;
  location_ids_json: string;
  style_notes: string;
}

export interface SceneOutline extends Timestamped {
  chapter_outline_id: string;
  order_index: number;
  title: string;
  goal: string;
  outline_content: string;
  character_ids_json: string;
  location_id: string | null;
}

export interface Character extends Timestamped {
  novel_id: string;
  name: string;
  role: string;
  description: string;
  personality: string;
  goals: string;
  arc: string;
  current_state_json: string;
  relationships_json: string;
  notes: string;
}

export interface Location extends Timestamped {
  novel_id: string;
  name: string;
  description: string;
  current_state_json: string;
}

export interface WorldRule extends Timestamped {
  novel_id: string;
  name: string;
  category: string;
  description: string;
  priority: number;
}

export interface TimelineEvent extends Timestamped {
  novel_id: string;
  chapter_id: string | null;
  title: string;
  story_time: string;
  description: string;
  character_ids_json: string;
}

export interface PlotThread extends Timestamped {
  novel_id: string;
  name: string;
  description: string;
  status: string;
  resolution: string;
  related_chapter_ids_json: string;
}

export interface Foreshadowing extends Timestamped {
  novel_id: string;
  description: string;
  status: string;
  planted_chapter_id: string | null;
  resolved_chapter_id: string | null;
  notes: string;
}

export interface CanonState extends Timestamped {
  novel_id: string;
  character_states_json: string;
  relationships_json: string;
  unresolved_conflicts_json: string;
  active_foreshadowing_json: string;
  key_events_json: string;
  chapter_summaries_json: string;
  progress_notes: string;
  pending_character_updates_json: string;
}

export interface WritingTask extends Timestamped {
  chapter_id: string;
  provider_id: string | null;
  operation: string;
  status: string;
  progress: number;
  options_json: string;
  pause_requested: boolean;
  error: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface GenerationRun extends Timestamped {
  task_id: string | null;
  chapter_id: string;
  provider_id: string | null;
  prompt_template_key: string;
  prompt: string;
  response: string;
  options_json: string;
  input_tokens: number | null;
  output_tokens: number | null;
  duration_ms: number | null;
  status: string;
  error: string;
  started_at: string;
  finished_at: string | null;
}

export interface ReviewResult extends Timestamped {
  chapter_id: string;
  generation_run_id: string | null;
  score: number | null;
  goal_alignment: string;
  character_consistency: string;
  timeline_consistency: string;
  repetition: string;
  missing_plot_points: string;
  style_issues: string;
  suggestions_json: string;
  raw_response: string;
}

export interface ModelProvider extends Timestamped {
  name: string;
  provider_type: string;
  base_url: string;
  model: string;
  api_key: string;
  default_options_json: string;
  timeout_seconds: number;
  enabled: boolean;
  last_test_status: string;
  last_test_message: string;
}

export interface CreativeRun extends Timestamped {
  novel_id: string;
  provider_id: string | null;
  operation: string;
  idea: string;
  reference_text: string;
  prompt: string;
  response: string;
  options_json: string;
  status: string;
  error: string;
  input_tokens: number | null;
  output_tokens: number | null;
  duration_ms: number | null;
}

export type StoryEngineeringOperation =
  | "framework"
  | "characters"
  | "world_rules"
  | "chapter_plan"
  | "pastiche";

export interface StagedCandidate extends Timestamped {
  project_id: string;
  novel_id: string;
  chapter_id: string | null;
  source_id: string | null;
  record_type: string;
  status: string;
  content_json: string;
  evidence_json: string;
  metadata_json: string;
}

export interface CandidateActionResult {
  candidate_id: string;
  status: string;
  applied: boolean;
  target_type: string;
  target_id: string | null;
  detail: string;
}

export interface ActivityItem {
  kind: string;
  id: string;
  project_id: string | null;
  novel_id: string | null;
  chapter_id: string | null;
  title: string;
  subtitle: string;
  status: string;
  state: string;
  error_code: string;
  created_at: string;
  updated_at: string;
}

export interface DeconstructionRun extends Timestamped {
  project_id: string;
  novel_id: string;
  provider_id: string | null;
  source_chars: number;
  dimensions_json: string;
  chunk_count: number;
  processed_units: number;
  total_units: number;
  current_dimension: string;
  candidate_count: number;
  status: string;
  error_code: string;
  error: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface LocalModelRecommendation {
  level: string;
  label: string;
  tasks: string[];
  reason: string;
  setup: string;
  options: Record<string, unknown>;
}

export interface LocalModelInfo {
  id: string;
  name: string;
  source: string;
  format: string;
  size_bytes: number;
  size_label: string;
  path: string;
  state: string;
  current: boolean;
  usable: boolean;
  recommendation: LocalModelRecommendation;
  details: Record<string, unknown>;
  provider_template: Record<string, unknown> | null;
}

export interface LocalModelInventory {
  scanned_at: string;
  hardware: {
    chip?: string;
    memory_gb?: number;
    disk_free_gb?: number;
    platform?: string;
  };
  current_model: LocalModelInfo | null;
  models: LocalModelInfo[];
  configured_providers: Array<Record<string, unknown>>;
  summary: {
    total?: number;
    generative?: number;
    auxiliary?: number;
    incomplete?: number;
    recommended_primary?: string | null;
  };
  usage_profiles: Array<{
    name: string;
    model: string;
    why: string;
    settings: string;
  }>;
}

export interface PromptTemplate extends Timestamped {
  key: string;
  name: string;
  description: string;
  template_text: string;
  output_schema_json: string;
  version: number;
  active: boolean;
}

export interface ContextPreview {
  estimated_tokens: number;
  budget: number;
  sections: Record<string, string>;
  rendered_context: string;
}

export interface RunStep {
  id: string;
  sequence: number;
  state: string;
  status: string;
  input_json: string;
  output_json: string;
  error_code: string;
  error: string;
  started_at: string;
  finished_at: string | null;
}

export interface ModelCall {
  id: string;
  step_id: string;
  provider_id: string | null;
  agent_name: string;
  prompt: string;
  response: string;
  raw_response_json: string;
  parsed_json: string;
  options_json: string;
  input_tokens: number | null;
  output_tokens: number | null;
  duration_ms: number | null;
  status: string;
  error_code: string;
  error: string;
  started_at: string;
  finished_at: string | null;
}

export interface ChapterVersion {
  id: string;
  chapter_id: string;
  run_id: string;
  parent_version_id: string | null;
  version_number: number;
  kind: string;
  content_markdown: string;
  content_hash: string;
  created_at: string;
}

export interface ChapterLoopRun extends Timestamped {
  project_id: string;
  novel_id: string;
  chapter_id: string;
  provider_id: string | null;
  state: string;
  status: string;
  active_slot: number | null;
  context_budget: number;
  options_json: string;
  assembled_context: string;
  continuity_report_json: string;
  draft_preview: string;
  draft_preview_updated_at: string | null;
  draft_chars: number;
  is_streaming: boolean;
  stream_supported: boolean;
  draft_attempts_json: string;
  draft_warning: string;
  current_step: string;
  raw_output_available: boolean;
  recoverable_raw_output: boolean;
  partial_output_available: boolean;
  failed_step: string | null;
  user_facing_error: string;
  technical_error: string;
  recovery_actions: string[];
  current_version_id: string | null;
  revision_parent_version_id: string | null;
  revision_feedback: string;
  approved_version_id: string | null;
  decision_feedback: string;
  decided_at: string | null;
  cancel_requested: boolean;
  error_code: string;
  error: string;
  started_at: string | null;
  finished_at: string | null;
  steps: RunStep[];
  model_calls: ModelCall[];
  versions: ChapterVersion[];
  auto_policy: AutoRunPolicy | null;
  revision_plans: RevisionPlan[];
}

export interface RunRawOutput {
  run_id: string;
  model_call_id: string;
  agent_name: string;
  content: string;
  characters: number;
  created_at: string;
}

export interface ChapterLoopRunSummary extends Timestamped {
  project_id: string;
  novel_id: string;
  chapter_id: string;
  provider_id: string | null;
  project_name: string;
  novel_title: string;
  chapter_title: string;
  provider_name: string | null;
  model: string | null;
  state: string;
  status: string;
  active_slot: number | null;
  current_version_id: string | null;
  approved_version_id: string | null;
  error_code: string;
  error: string;
  started_at: string | null;
  finished_at: string | null;
  decided_at: string | null;
}

export interface ContinuityIssue {
  issue_id?: string;
  type: "timeline" | "character" | "item" | "location" | "canon" | "causality" | "style" | "plot";
  severity: "minor" | "major" | "blocker";
  evidence: string;
  problem: string;
  suggested_fix: string;
  auto_fixable?: boolean;
  affected_sections?: string[];
  must_pause?: boolean;
}

export interface ContinuityReport {
  passed: boolean;
  severity: "none" | "minor" | "major" | "blocker";
  issues: ContinuityIssue[];
}

export interface ProviderTestResult {
  ok: boolean;
  message: string;
  latency_ms: number;
  response_preview: string;
}

export type ReviewMode =
  | "manual_review"
  | "ai_review_suggest"
  | "ai_auto_revise"
  | "ai_auto_commit"
  | "full_autonomous";

export interface AutoRunPolicy extends Timestamped {
  mode: ReviewMode;
  reference_pack_id: string | null;
  max_revision_rounds_per_chapter: number;
  max_total_model_calls: number;
  stop_on_blocker: boolean;
  stop_on_major_after_rounds: number;
  auto_commit_threshold_json: string;
  update_story_memory: boolean;
  revision_rounds: number;
  status: string;
  pause_reason: string;
  metadata_json: string;
}

export interface RevisionPlan extends Timestamped {
  target_version_id: string;
  status: string;
  goals_json: string;
  fixes_json: string;
  risk_notes_json: string;
  metadata_json: string;
}

export interface ReferenceSearchItem {
  id: string;
  type: "chapter" | "chapter_version";
  title: string;
  subtitle: string;
  chapter_id: string;
  token_estimate: number;
}

export interface ReferenceSelection {
  type: "chapter" | "chapter_version";
  source_id: string;
  title: string;
  reason: string;
  token_estimate: number;
}

export interface MultiChapterRun extends Timestamped {
  project_id: string;
  novel_id: string;
  start_chapter_id: string;
  provider_id: string | null;
  mode: ReviewMode;
  chapter_count: number;
  chapter_ids_json: string;
  current_index: number;
  current_chapter_id: string | null;
  current_loop_run_id: string | null;
  completed_chapter_ids_json: string;
  loop_run_ids_json: string;
  policy_json: string;
  references_json: string;
  context_budget: number;
  checkpoint_every: number;
  status: string;
  active_slot: number | null;
  pause_requested: boolean;
  stop_requested: boolean;
  pause_reason: string;
  error_code: string;
  error: string;
  started_at: string | null;
  finished_at: string | null;
}

// ───────────────────────── 故事地图（Story Map）——与后端 schemas/story_map.py 一一对应 ─────────────────────────

export interface StoryMapChapter {
  id: string;
  order_index: number;
  title: string;
  status: string;
  word_count: number;
  summary: string;
}

export interface StoryMapCharacter {
  id: string;
  name: string;
  role: string;
  arc: string;
  presence_chapters: number[];
}

export interface StoryMapTimelineEvent {
  id: string;
  chapter_id: string | null;
  title: string;
  story_time: string;
  story_order: number | null;
  description: string;
  character_ids: string[];
}

export interface StoryMapPlotThread {
  id: string;
  name: string;
  description: string;
  status: string;
  resolution: string;
  related_chapter_ids: string[];
}

export interface StoryMapForeshadowing {
  id: string;
  description: string;
  status: string;
  planted_chapter_id: string | null;
  resolved_chapter_id: string | null;
  notes: string;
}

export interface StoryMapRelationship {
  source_id: string;
  target_id: string;
  type: string;
  description: string;
  mutual: boolean;
}

export interface StoryMapUnmatchedRelationship {
  source_id: string;
  target_name: string;
  description: string;
}

export interface StoryMapStats {
  review_scores: Array<{ chapter_id: string; score: number | null }>;
  foreshadow_counts: { open: number; resolved: number; overdue: number };
}

export interface StoryMap {
  chapters: StoryMapChapter[];
  characters: StoryMapCharacter[];
  timeline_events: StoryMapTimelineEvent[];
  plot_threads: StoryMapPlotThread[];
  foreshadowing: StoryMapForeshadowing[];
  relationships: StoryMapRelationship[];
  unmatched: StoryMapUnmatchedRelationship[];
  stats: StoryMapStats;
}

export interface StoryMapExtractRun extends Timestamped {
  project_id: string;
  novel_id: string;
  provider_id: string | null;
  chapter_ids_json: string;
  total_chapters: number;
  processed_chapters: number;
  current_chapter_title: string;
  candidate_count: number;
  options_json: string;
  status: string;
  error_code: string;
  error: string;
  started_at: string | null;
  finished_at: string | null;
}

// 复用 story-engineering 候选结构（staged_storymap_*）
export interface StagedCandidate extends Timestamped {
  project_id: string;
  novel_id: string;
  chapter_id: string | null;
  source_id: string | null;
  record_type: string;
  status: string;
  content_json: string;
  evidence_json: string;
  metadata_json: string;
}
