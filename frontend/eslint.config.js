// @ts-check
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import prettier from 'eslint-config-prettier/flat'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'coverage']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      // Type-aware linting. Requires TypeScript < 6.1 — TS 7 ships no compiler
      // API until 7.1, so typescript-eslint cannot support it yet.
      tseslint.configs.strictTypeChecked,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: {
        // `projectService` replaces the older `project: true`.
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
  // Must stay last: turns off stylistic rules that would fight Prettier.
  prettier,
])
