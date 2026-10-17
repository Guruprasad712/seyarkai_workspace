// intentionally public demo credentials — safe to commit
export const DEMO_ACCOUNTS = [
  {
    role: "Builder",
    meaning: "Builds agents and runs work",
    email: "builder@seyarkai.example",
    password: "builder123",
  },
  {
    role: "Reviewer",
    meaning: "Approves checkpoints",
    email: "reviewer@seyarkai.example",
    password: "reviewer123",
  },
  {
    role: "Observer",
    meaning: "Read-only, can ask questions",
    email: "observer@seyarkai.example",
    password: "observer123",
  },
] as const

export type DemoAccount = (typeof DEMO_ACCOUNTS)[number]
