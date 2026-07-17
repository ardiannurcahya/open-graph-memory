import { createContext, useContext } from "react";

export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const themeContext = createContext<{ preference: ThemePreference; resolvedTheme: ResolvedTheme; setPreference: (value: ThemePreference) => void } | null>(null);

export function readThemePreference(): ThemePreference {
  try {
    const value = localStorage.getItem("ogm-theme-preference");
    return value === "light" || value === "dark" || value === "system" ? value : "system";
  } catch {
    return "system";
  }
}

function systemPrefersDark(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ?? false;
}

export function resolveTheme(preference: ThemePreference, dark = systemPrefersDark()): ResolvedTheme {
  return preference === "system" ? (dark ? "dark" : "light") : preference;
}

export function useTheme() {
  const theme = useContext(themeContext);
  if (!theme) throw new Error("useTheme must be used within ThemeProvider");
  return theme;
}
