export interface BundleInfo {
  id: string;
  filename: string;
  upload_time: string;
  status: string;
  file_path: string;
}

export interface Issue {
  id: string;
  severity: 'critical' | 'warning' | 'info';
  title: string;
  category: string;
  resource?: string;
  namespace?: string;
  description: string;
  evidence: string[];
  remediation: string;
  ai_confidence?: number;
  proposed_fixes?: ProposedFix[];
  ai_explanation?: AIExplanation;
  relevant_log_snippets?: LogSnippet[];
}

export interface ClusterHealth {
  score: number;
  node_count: number;
  pod_count: number;
  namespace_count: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
}

export interface LogEntry {
  timestamp?: string;
  source: string;
  level: string;
  message: string;
  namespace?: string;
  pod?: string;
}

export interface TopologyNode {
  id: string;
  label: string;
  type: string;
  status: string;
  namespace: string;
  metadata: Record<string, unknown>;
}

export interface TopologyEdge {
  source: string;
  target: string;
  label?: string;
}

export interface TimelineEvent {
  timestamp: string;
  type: string;
  message: string;
  severity: string;
  resource: string;
}

export interface ProposedFix {
  id: string;
  description: string;
  command?: string;
  is_automated: boolean;
}

export interface AIExplanation {
  root_cause: string;
  impact: string;
  related_issues: string[];
}

export interface LogSnippet {
  source: string;
  lines: string[];
  highlight_indices: number[];
  level: string;
}

export interface CorrelationGroup {
  id: string;
  title: string;
  events: TimelineEvent[];
  explanation: string;
  sparkline_data: { count: number; bucket?: number; timestamp?: string; start?: string; end?: string }[];
}

export interface ResourceHealthDot {
  id: string;
  name: string;
  type: string;
  namespace: string;
  status: string;
}

export interface AnalysisResult {
  bundle_id: string;
  status: string;
  cluster_health: ClusterHealth;
  issues: Issue[];
  log_entries: LogEntry[];
  topology_nodes: TopologyNode[];
  topology_edges: TopologyEdge[];
  summary: string;
  analyzed_at: string;
  raw_events: TimelineEvent[];
  correlations?: CorrelationGroup[];
  resource_health?: ResourceHealthDot[];
  ai_insights?: string[];
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatRequest {
  question: string;
  history: ChatMessage[];
}

export interface ChatResponse {
  answer: string;
  sources: string[];
}

export interface AnalysisHistoryEntry {
  analyzed_at: string;
  health_score: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
  issue_count: number;
}

export interface CompareRequest {
  left_bundle_id: string;
  left_timestamp?: string;
  right_bundle_id: string;
  right_timestamp?: string;
}

export interface CompareResponse {
  left: AnalysisResult;
  right: AnalysisResult;
}
