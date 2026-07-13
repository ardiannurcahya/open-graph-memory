/** Persistent credential storage backed by localStorage. */

import { useCallback, useState } from "react";

import type { Credentials } from "./types";

const PROJECT_KEY = "ogm.projectId";
const API_KEY = "ogm.apiKey";

function load(): Credentials {
  return {
    projectId: localStorage.getItem(PROJECT_KEY) ?? "",
    apiKey: localStorage.getItem(API_KEY) ?? "",
  };
}

export function useCredentials() {
  const [credentials, setCredentials] = useState<Credentials>(load);

  const save = useCallback((next: Credentials) => {
    const trimmed = { projectId: next.projectId.trim(), apiKey: next.apiKey.trim() };
    localStorage.setItem(PROJECT_KEY, trimmed.projectId);
    localStorage.setItem(API_KEY, trimmed.apiKey);
    setCredentials(trimmed);
  }, []);

  const clear = useCallback(() => {
    localStorage.removeItem(PROJECT_KEY);
    localStorage.removeItem(API_KEY);
    setCredentials({ projectId: "", apiKey: "" });
  }, []);

  return { credentials, setCredentials, save, clear };
}
