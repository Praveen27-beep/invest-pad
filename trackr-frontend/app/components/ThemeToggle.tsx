"use client";

import { useTheme } from "@/lib/theme-context";

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const isDark = theme === "dark";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className="press-scale relative flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-navy-100 text-navy-600 transition-colors hover:bg-cream-50 hover:text-navy-900"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        className={`absolute h-4 w-4 transition-all duration-300 ease-smooth ${
          isDark ? "-translate-y-6 opacity-0" : "translate-y-0 opacity-100"
        }`}
      >
        <circle cx="12" cy="12" r="4.5" stroke="currentColor" strokeWidth="1.6" />
        <path
          d="M12 2.5v2M12 19.5v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2.5 12h2M19.5 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
      </svg>
      <svg
        viewBox="0 0 24 24"
        fill="none"
        className={`absolute h-4 w-4 transition-all duration-300 ease-smooth ${
          isDark ? "translate-y-0 opacity-100" : "translate-y-6 opacity-0"
        }`}
      >
        <path
          d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5Z"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  );
}
