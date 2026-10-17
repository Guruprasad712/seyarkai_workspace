// FILL IN before demo — do not commit real passwords to a public repo.
// Replace every FILL_IN_* value with the actual seeded credentials.
export const DEMO_ACCOUNTS = [
  {
    role: "Builder",
    meaning: "Builds agents and runs work",
    email: "builder@seyarkai.example", // FILL IN
    password: "FILL_IN_PASSWORD",      // FILL IN
  },
  {
    role: "Reviewer",
    meaning: "Approves checkpoints",
    email: "reviewer@seyarkai.example", // FILL IN
    password: "FILL_IN_PASSWORD",       // FILL IN
  },
  {
    role: "Observer",
    meaning: "Read-only, can ask questions",
    email: "observer@seyarkai.example", // FILL IN
    password: "FILL_IN_PASSWORD",       // FILL IN
  },
] as const

export type DemoAccount = (typeof DEMO_ACCOUNTS)[number]
