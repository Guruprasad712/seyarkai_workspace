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
