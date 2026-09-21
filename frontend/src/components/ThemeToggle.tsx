import { useEffect, useState } from "react";

type Theme = "light" | "dark";
const STORAGE_KEY = "azuregos_theme";

function systemPrefersDark(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

function storedTheme(): Theme | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
}

// A two-state light/dark toggle. On first visit (no stored choice) the app
// follows the OS preference via CSS; once toggled, the choice is persisted.
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(
    () => storedTheme() ?? (systemPrefersDark() ? "dark" : "light"),
  );

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore storage failures (private mode etc.) */
    }
  };

  return (
    <button
      className="btn secondary small"
      onClick={toggle}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
    >
      {theme === "dark" ? "☀️" : "🌙"}
    </button>
  );
}
