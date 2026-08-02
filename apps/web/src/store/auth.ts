import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

const safely = <T>(operation: () => T, fallback: T): T => {
  try {
    return operation();
  } catch (error) {
    if (error instanceof DOMException && error.name === "SecurityError") {
      return fallback;
    }
    throw error;
  }
};

const removeLegacyCredentials = (): void => {
  // Migrate credentials written by pre-session-storage releases before hydration.
  safely(() => localStorage.removeItem("ogm-auth"), undefined);
};

removeLegacyCredentials();

const safeSessionStorage: Storage = {
  getItem: (key) => safely(() => sessionStorage.getItem(key), null),
  setItem: (key, value) => safely(() => sessionStorage.setItem(key, value), undefined),
  removeItem: (key) => safely(() => sessionStorage.removeItem(key), undefined),
  clear: () => safely(() => sessionStorage.clear(), undefined),
  key: (index) => safely(() => sessionStorage.key(index), null),
  get length() {
    return safely(() => sessionStorage.length, 0);
  },
};

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
      setCredentials: (creds) => {
        removeLegacyCredentials();
        set({ apiKey: creds.apiKey, projectId: creds.projectId, adminKey: "" });
      },
      setAdminKey: (adminKey) => {
        removeLegacyCredentials();
        set({ apiKey: "", projectId: "", adminKey });
      },
      clear: () => set({ apiKey: "", projectId: "", adminKey: "" }),
    }),
    {
      name: "ogm-auth",
      storage: createJSONStorage(() => safeSessionStorage),
      onRehydrateStorage: () => {
        // Credentials from older releases must not survive in persistent storage.
        removeLegacyCredentials();
      },
    },
  ),
);

export const isAuthenticated = (): boolean => {
  const { apiKey, projectId } = useAuthStore.getState();
  return Boolean(apiKey && projectId);
};
