import { useEffect, useMemo, useState } from "react";

import { getInitialThemePreference, resolveTheme, themeStorageKey } from "../lib/chat";
import { useMediaQuery } from "./useMediaQuery";

export function useThemePreference() {
  const [themePreference, setThemePreference] = useState(getInitialThemePreference);
  const prefersDarkMode = useMediaQuery("(prefers-color-scheme: dark)");

  const resolvedTheme = useMemo(
    () => resolveTheme(themePreference, prefersDarkMode),
    [themePreference, prefersDarkMode],
  );

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.style.colorScheme = resolvedTheme;
  }, [resolvedTheme]);

  function setManualTheme(nextTheme) {
    setThemePreference(nextTheme);
    window.localStorage.setItem(themeStorageKey, nextTheme);
  }

  function toggleTheme() {
    setManualTheme(resolvedTheme === "dark" ? "light" : "dark");
  }

  return {
    resolvedTheme,
    themePreference,
    setManualTheme,
    toggleTheme,
  };
}
