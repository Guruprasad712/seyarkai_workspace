export type Role = "admin" | "builder" | "reviewer" | "observer"

export const can = {
  manageUsers:   (r: string) => r === "admin",
  editAgents:    (r: string) => r === "admin" || r === "builder",
  editProjects:  (r: string) => r === "admin" || r === "builder",
  editPolicy:    (r: string) => r === "admin" || r === "builder",
  publishPolicy: (r: string) => r === "admin" || r === "builder" || r === "reviewer",
  execute:       (r: string) => r !== "observer",
  sendGuidance:  (r: string) => r !== "observer",
  addKnowledge:  (r: string) => r !== "observer",
}
