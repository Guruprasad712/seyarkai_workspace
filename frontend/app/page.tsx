"use client";

import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";

type Status = "loading" | "ok" | "error";

export default function HomePage() {
  const [status, setStatus] = useState<Status>("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    apiFetch<{ status: string }>("/health")
      .then(() => setStatus("ok"))
      .catch((err) => {
        setStatus("error");
        setErrorMsg(err instanceof ApiError ? err.message : String(err));
      });
  }, []);

  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <h1 className="text-2xl font-semibold">Dashboard</h1>
      <div className="mt-6 inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm">
        <span className="font-medium text-muted-foreground">Backend</span>
        {status === "loading" && (
          <span className="text-muted-foreground">Checking…</span>
        )}
        {status === "ok" && (
          <span className="flex items-center gap-1.5 text-green-600 dark:text-green-400">
            <span className="inline-block h-2 w-2 rounded-full bg-green-500" />
            Online
          </span>
        )}
        {status === "error" && (
          <span className="flex items-center gap-1.5 text-red-600 dark:text-red-400">
            <span className="inline-block h-2 w-2 rounded-full bg-red-500" />
            Offline{errorMsg ? ` — ${errorMsg}` : ""}
          </span>
        )}
      </div>
    </div>
  );
}
