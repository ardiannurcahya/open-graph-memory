import { afterEach, describe, expect, it } from "vitest";
import { useAuthStore } from "./auth";

describe("authentication storage", () => {
  afterEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    useAuthStore.getState().clear();
  });

  it("keeps credentials in session storage and removes legacy persistent credentials", () => {
    localStorage.setItem("ogm-auth", "legacy-secret");
    useAuthStore.getState().setAdminKey("admin-secret");
    useAuthStore.getState().setCredentials({ apiKey: "api-secret", projectId: "project" });

    expect(sessionStorage.getItem("ogm-auth")).toContain("api-secret");
    expect(sessionStorage.getItem("ogm-auth")).not.toContain("admin-secret");
    expect(localStorage.getItem("ogm-auth")).toBeNull();
  });

  it("clears an admin credential when changing project credentials", () => {
    useAuthStore.getState().setAdminKey("admin-secret");
    useAuthStore.getState().setCredentials({ apiKey: "new-api-secret", projectId: "new-project" });

    expect(useAuthStore.getState()).toMatchObject({
      apiKey: "new-api-secret",
      projectId: "new-project",
      adminKey: "",
    });
  });

  it("clears project credentials when changing to an admin credential", () => {
    useAuthStore.getState().setCredentials({ apiKey: "api-secret", projectId: "project" });
    useAuthStore.getState().setAdminKey("new-admin-secret");

    expect(useAuthStore.getState()).toMatchObject({
      apiKey: "",
      projectId: "",
      adminKey: "new-admin-secret",
    });
  });

  it("tolerates denied persistent storage while updating session credentials", () => {
    const removeItem = localStorage.removeItem;
    localStorage.removeItem = () => {
      throw new DOMException("blocked", "SecurityError");
    };

    try {
      useAuthStore.getState().setCredentials({ apiKey: "api-secret", projectId: "project" });
      expect(useAuthStore.getState()).toMatchObject({ apiKey: "api-secret", projectId: "project" });
    } finally {
      localStorage.removeItem = removeItem;
    }
  });

  it("tolerates denied session storage while updating credentials", () => {
    const setItem = sessionStorage.setItem;
    sessionStorage.setItem = () => {
      throw new DOMException("blocked", "SecurityError");
    };

    try {
      useAuthStore.getState().setCredentials({ apiKey: "api-secret", projectId: "project" });
      expect(useAuthStore.getState()).toMatchObject({ apiKey: "api-secret", projectId: "project" });
    } finally {
      sessionStorage.setItem = setItem;
    }
  });
});
