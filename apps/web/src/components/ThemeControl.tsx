import { Sun, Moon } from "lucide-react";
import { useTheme } from "../themeState";

export function ThemeControl() {
  const { resolvedTheme, setPreference } = useTheme();
  const isDark = resolvedTheme === "dark";

  const toggleTheme = () => {
    const nextTheme = isDark ? "light" : "dark";
    setPreference(nextTheme);
  };

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="flex items-center gap-1.5 rounded-lg border border-mac px-2.5 py-1 text-xs font-medium bg-surface text-main hover:bg-muted transition-all duration-150 cursor-pointer shadow-sm active:scale-95"
      title={`Switch to macOS ${isDark ? "Light" : "Dark"} Mode`}
    >
      {isDark ? (
        <>
          <Sun className="h-3.5 w-3.5 text-amber-400" />
          <span>Light Mode</span>
        </>
      ) : (
        <>
          <Moon className="h-3.5 w-3.5 text-mac-accent" />
          <span>Dark Mode</span>
        </>
      )}
    </button>
  );
}
