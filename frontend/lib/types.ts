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
