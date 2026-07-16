import { create } from "zustand";
import { persist } from "zustand/middleware";

interface MemoryUserRef {
  id: string;
  external_id: string;
  display_name: string | null;
}

interface MemoryAgentRef {
  id: string;
  name: string;
}

interface MemorySessionRef {
  id: string;
  user_id: string;
  agent_id: string;
  title: string | null;
}

interface MemoryStoreState {
  users: MemoryUserRef[];
  agents: MemoryAgentRef[];
  sessions: MemorySessionRef[];
  addUser: (user: MemoryUserRef) => void;
  addAgent: (agent: MemoryAgentRef) => void;
  addSession: (session: MemorySessionRef) => void;
  clear: () => void;
}

export const useMemoryStore = create<MemoryStoreState>()(
  persist(
    (set) => ({
      users: [],
      agents: [],
      sessions: [],
      addUser: (user) => set((s) => ({ users: [...s.users, user] })),
      addAgent: (agent) => set((s) => ({ agents: [...s.agents, agent] })),
      addSession: (session) => set((s) => ({ sessions: [...s.sessions, session] })),
      clear: () => set({ users: [], agents: [], sessions: [] }),
    }),
    { name: "ogm-memory-refs" },
  ),
);
