export type Depth = "quick" | "guided" | "deep";
export type Role = "new_to_team" | "frontend" | "backend";
export type Familiarity = "brand_new" | "some_exposure" | "comfortable" | "expert";

export interface Preferences {
  role: Role;
  familiarity: Familiarity;
  goals: string[];
  depth: Depth;
  custom_instructions?: string;
}

export interface RepoMeta {
  owner: string;
  name: string;
  default_branch: string;
  description: string;
  primary_language: string;
  languages: string[];
  file_count: number;
  stars: number;
}

export interface ServiceNode {
  id: string;
  label: string;
  path: string;
  language: string;
  role: string;
  summary: string;
  component: string;
  tech: string[];
  inbound: string[];
  outbound: string[];
  layer: string;
}

export interface ServiceEdge {
  source: string;
  target: string;
  label: string;
  kind: "request" | "event" | "support" | "data";
  protocol: string;
}

export interface Architecture {
  summary: string;
  nodes: ServiceNode[];
  edges: ServiceEdge[];
  layers: string[];
}

export interface FlowStep {
  index: number;
  actor: string;
  label: string;
  code: string;
  note: string;
  kind: "sync" | "async";
  detail: string;
  files: string[];
  data_in: string;
  data_out: string;
}

export interface DataFlow {
  title: string;
  trigger: string;
  summary: string;
  steps: FlowStep[];
  rationale: string;
  alternatives: string[];
}

export interface Column {
  name: string;
  type: string;
  key: string;
  ref: string;
}

export interface Table {
  name: string;
  columns: Column[];
}

export interface Relationship {
  source: string;
  target: string;
  cardinality: string;
}

export interface Schema {
  summary: string;
  tables: Table[];
  relationships: Relationship[];
  plain_english: string;
}

export interface Lesson {
  id: string;
  title: string;
  section: string;
  summary: string;
  body: string;
  tags: string[];
  component: string;
  icon: string;
}

export interface Guide {
  title: string;
  intro: string;
  lessons: Lesson[];
}

export interface ScreenElement {
  label: string;
  kind: string;
  note: string;
}

export interface WalkthroughScreen {
  id: string;
  title: string;
  route: string;
  kind: string;
  description: string;
  elements: ScreenElement[];
  user_actions: string[];
  leads_to: string;
}

export interface Sandbox {
  title: string;
  summary: string;
  app_type: string;
  screens: WalkthroughScreen[];
  challenge: string;
}

export interface VideoScene {
  id: string;
  title: string;
  narration: string;
  bullets: string[];
  visual: string;
  accent: string;
}

export interface VideoExplainer {
  title: string;
  persona: string;
  tagline: string;
  scenes: VideoScene[];
}

export interface Component {
  id: string;
  name: string;
  kind: string;
  path: string;
  tech: string[];
  responsibility: string;
  key_files: string[];
}

export interface ResearchBrief {
  what: string;
  does: string;
  how: string;
  entry_points: string[];
  modules: string[];
  languages: string[];
  components: Component[];
  has_database: boolean;
  notes: string;
  file_assignments: Record<string, string[]>;
}

export interface ExplorerFindings {
  summary: string;
  entry_points: string[];
  modules: string[];
  languages: string[];
}

export interface AgentProgress {
  name: string;
  status: "waiting" | "running" | "done" | "error";
  detail: string;
}

export interface RateStatus {
  can_generate: boolean;
  seconds_left: number;
  next_allowed_at: number;
  window_hours: number;
  max_attempts: number;
  used: number;
}

export interface AuthUser {
  token: string;
  username: string;
  is_admin: boolean;
  rate: RateStatus;
}

export interface AnalysisSummary {
  id: string;
  repo_url: string;
  repo_name: string;
  repo_owner: string;
  owner?: string;
  status: "queued" | "running" | "done" | "error" | "cancelled";
  percent: number;
  created_at: number;
  llm_powered: boolean;
}

export interface AnalysisResult {
  id: string;
  repo_url: string;
  status: "queued" | "running" | "done" | "error" | "cancelled";
  progress: AgentProgress[];
  percent: number;
  error: string | null;
  cancel_requested?: boolean;
  llm_powered: boolean;
  repo: RepoMeta;
  preferences: Preferences;
  research: ResearchBrief;
  explorer: ExplorerFindings;
  architecture: Architecture;
  dataflow: DataFlow;
  schema: Schema;
  guide: Guide;
  sandbox: Sandbox;
  video: VideoExplainer;
}
