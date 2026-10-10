export type User = {
  id: string
  email: string
  name: string
  role: string
  status: string
}

export type McpTool = {
  id: string
  name: string
  tool_name: string
  server_key: string
  description: string
  status: string
}

export type PublishFailure = {
  code: string
  message: string
}

export type Capability = {
  name: string
  description: string
}

export type AgentVersion = {
  id: string
  agent_id: string
  version: string
  instructions: string
  capabilities: Capability[]
  status: "draft" | "published" | "retired"
  published_at: string | null
  tool_ids: string[]
}

export type Agent = {
  id: string
  agent_code: string
  name: string
  description: string
  role_purpose: string
  status: string
  versions: AgentVersion[]
}

export type AgentSummary = Omit<Agent, "versions">

export type Project = {
  id: string
  name: string
  description: string
  status: string
  created_by: string
  created_at: string
  work_item_count: number
}

export type WorkerOut = {
  type: "ai_agent" | "human"
  id: string
  agent_name: string | null
  agent_version: string | null
  user_name: string | null
  user_email: string | null
}

export type WorkItem = {
  id: string
  project_id: string
  name: string
  objective: string
  description: string
  expected_outcome: string
  status: string
  previous_output: string | null
  created_by: string
  created_at: string
  workers: WorkerOut[]
}

export type StageOut = {
  id: string
  policy_id: string
  sequence: number
  name: string
  description: string
  expected_output: string
  agent_version_id: string
  created_at: string
}

export type CheckpointOut = {
  id: string
  policy_id: string
  stage_id: string | null
  type: "approval" | "review" | "input" | "final_review"
  assigned_user_id: string
  instruction: string
  created_at: string
}

export type PolicyOut = {
  id: string
  work_item_id: string
  version: number
  status: "draft" | "published"
  generated_by: string
  published_by: string | null
  published_at: string | null
  created_at: string
  stages: StageOut[]
  checkpoints: CheckpointOut[]
}

export type StageSummary = {
  sequence: number
  name: string
  description: string
  expected_output: string
  agent_output: string | null
  checkpoint_decision: string | null
  checkpoint_comment: string | null
  checkpoint_type: string | null
}

export type ExecutionSummaryOut = {
  execution_id: string
  execution_number: number
  status: string
  started_at: string | null
  completed_at: string | null
  error: string | null
  work_item_objective: string
  work_item_description: string
  work_item_expected_outcome: string
  stages: StageSummary[]
  final_review_decision: string | null
  final_review_comment: string | null
}

export type EventOut = {
  id: string
  execution_id: string
  stage_id: string | null
  event_type: string
  actor_type: string
  actor_id: string | null
  payload: Record<string, unknown>
  created_at: string
}

export type CheckpointBrief = {
  id: string
  type: string
  assigned_user_id: string
  instruction: string
  stage_id: string | null
}

export type ExecutionOut = {
  id: string
  work_item_id: string
  policy_id: string
  execution_number: number
  status: string
  current_stage_id: string | null
  blocking_checkpoint: CheckpointBrief | null
  started_at: string | null
  completed_at: string | null
  error: string | null
  pending_summary: string | null
  created_at: string
}

export type KnowledgeDocument = {
  id: string
  title: string
  content: string
  source: string
  last_verified_at: string
  verified_by: string | null
  external_id: string | null
  age_days: number
  freshness: "fresh" | "ageing" | "stale"
  created_at: string
  updated_at: string
}
