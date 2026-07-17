import { useEffect, useState } from "react";
import { readThemePreference, resolveTheme, themeContext, type ResolvedTheme, type ThemePreference } from "./themeState";

function applyTheme(theme: ResolvedTheme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(readThemePreference);
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>(() => resolveTheme(readThemePreference()));

  useEffect(() => {
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!media) return;
    const update = (event?: MediaQueryListEvent) => setResolvedTheme(resolveTheme(preference, event?.matches ?? media.matches));
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [preference]);

  useEffect(() => applyTheme(resolvedTheme), [resolvedTheme]);

  const setPreference = (value: ThemePreference) => {
    try {
      localStorage.setItem("ogm-theme-preference", value);
    } catch {
      setPreferenceState(value);
      return;
    }
    setPreferenceState(value);
  };

  return <themeContext.Provider value={{ preference, resolvedTheme, setPreference }}>{children}</themeContext.Provider>;
}
