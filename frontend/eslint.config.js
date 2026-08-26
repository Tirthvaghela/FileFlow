import js from "@eslint/js";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

export default [
  { ignores: ["dist/**", "node_modules/**", "coverage/**"] },
  {
    files: ["**/*.{js,jsx}"],
    ...js.configs.recommended,
  },
  {
    files: ["**/*.{js,jsx}"],
    ...react.configs.flat.recommended,
  },
  {
    files: ["**/*.{js,jsx}"],
    ...react.configs.flat["jsx-runtime"],
  },
  {
    files: ["**/*.{js,jsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      // Just the two classic hook-correctness rules. eslint-plugin-react-hooks
      // v7's own "recommended"/"recommended-latest" presets bundle in a much
      // larger, React-Compiler-oriented rule set (immutability, purity,
      // gating, set-state-in-render, ...) that this project was never written
      // against and doesn't use the Compiler at all -- hand-picking these two
      // keeps the check scoped to real hook bugs (conditional/looped hook
      // calls, a wrong dependency array causing a stale closure) instead of
      // an unrelated style migration.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
  {
    files: ["**/*.{js,jsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: { ...globals.browser, ...globals.node },
    },
    settings: { react: { version: "detect" } },
    rules: {
      // No PropTypes anywhere in this project (plain JS/JSX, no `prop-types`
      // dependency) -- leaving this rule on would flag every component's
      // props as "unvalidated", which isn't a bug here, just a convention
      // this project doesn't follow.
      "react/prop-types": "off",
      // Flags every raw `'`/`"` inside JSX text (contractions, possessives,
      // quoted phrases) -- both render completely correctly in JSX/the
      // browser as-is, so this doesn't catch a real bug, only a stylistic
      // preference for HTML-entity-escaped punctuation. Off rather than
      // spending this task rewriting prose across ~6 unrelated files.
      "react/no-unescaped-entities": "off",
    },
  },
  {
    // Vitest injects describe/it/expect/vi/... as real globals (vite.config.js
    // sets test.globals: true) -- without this, every test file would report
    // them as undefined.
    files: ["**/*.test.{js,jsx}", "src/test/**/*.js"],
    languageOptions: {
      globals: { ...globals.vitest },
    },
  },
];
