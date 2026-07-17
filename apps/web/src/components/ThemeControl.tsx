import { useTheme, type ThemePreference } from "../themeState";

const choices: ThemePreference[] = ["system", "light", "dark"];

export function ThemeControl() {
  const { preference, setPreference } = useTheme();
  return (
    <fieldset aria-label="Theme" className="theme-control">
      <legend className="sr-only">Theme</legend>
      {choices.map((choice) => (
        <button key={choice} type="button" aria-pressed={preference === choice} onClick={() => setPreference(choice)} className="theme-choice">
          {choice}
        </button>
      ))}
    </fieldset>
  );
}
