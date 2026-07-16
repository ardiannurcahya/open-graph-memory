import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  apiKey: string;
  projectId: string;
  adminKey: string;
  setCredentials: (creds: { apiKey: string; projectId: string }) => void;
  setAdminKey: (key: string) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      apiKey: "",
      projectId: "",
      adminKey: "",
      setCredentials: (creds) =>
        set({ apiKey: creds.apiKey, projectId: creds.projectId }),
      setAdminKey: (adminKey) => set({ adminKey }),
      clear: () => set({ apiKey: "", projectId: "", adminKey: "" }),
    }),
    { name: "ogm-auth" },
  ),
);

export const isAuthenticated = (): boolean => {
  const { apiKey, projectId } = useAuthStore.getState();
  return Boolean(apiKey && projectId);
};
