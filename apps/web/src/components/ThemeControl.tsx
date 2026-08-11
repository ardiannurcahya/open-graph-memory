import { useTheme } from "../themeState";

export function ThemeControl() {
  const { preference, setPreference } = useTheme();

  return (
    <div role="group" aria-label="Theme" className="inline-flex rounded-lg border border-mac bg-muted/60 p-0.5 shadow-sm">
      {(["system", "light", "dark"] as const).map((mode) => (
        <button
          key={mode}
          type="button"
          aria-pressed={preference === mode}
          onClick={() => setPreference(mode)}
          className={`rounded-md px-2 py-0.5 text-xs font-medium capitalize transition-all ${
            preference === mode
              ? "bg-mac-accent !text-white shadow-sm font-semibold"
              : "text-subdued hover:text-main"
          }`}
        >
          {mode}
        </button>
      ))}
    </div>
  );
}
