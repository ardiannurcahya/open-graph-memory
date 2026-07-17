import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ThemeControl } from "./components/ThemeControl";
import { ThemeProvider } from "./theme";

let listener: ((event: MediaQueryListEvent) => void) | undefined;
let dark = false;

function renderControl() {
  return render(<ThemeProvider><ThemeControl /></ThemeProvider>);
}

describe("theme", () => {
  beforeEach(() => {
    localStorage.clear();
    dark = false;
    listener = undefined;
    vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: dark, media: "(prefers-color-scheme: dark)", addEventListener: (_: string, fn: (event: MediaQueryListEvent) => void) => { listener = fn; }, removeEventListener: vi.fn() })));
    document.documentElement.className = "";
    delete document.documentElement.dataset.theme;
  });

  it("persists preference and applies root state", async () => {
    renderControl();
    await userEvent.click(screen.getByRole("button", { name: "dark" }));
    expect(localStorage.getItem("ogm-theme-preference")).toBe("dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("follows live system changes only for system preference", () => {
    renderControl();
    act(() => listener?.({ matches: true } as MediaQueryListEvent));
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    act(() => listener?.({ matches: false } as MediaQueryListEvent));
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });

  it("mounts with system theme when preference read fails", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    renderControl();
    expect(screen.getByRole("group", { name: "Theme" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "system" })).toHaveAttribute("aria-pressed", "true");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });

  it("updates theme in memory when preference write fails", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    renderControl();
    await userEvent.click(screen.getByRole("button", { name: "dark" }));
    expect(screen.getByRole("button", { name: "dark" })).toHaveAttribute("aria-pressed", "true");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  });
});
