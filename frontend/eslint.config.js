// @ts-check
import js from '@eslint/js';
import eslintReact from '@eslint-react/eslint-plugin';
import { defineConfig, globalIgnores } from 'eslint/config';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default defineConfig([
  globalIgnores(['dist/', 'node_modules/']),
  {
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      eslintReact.configs['recommended-typescript'],
      // Identifier naming is style the codebase has not adopted (refs such as `mounted`).
      eslintReact.configs['disable-naming-convention'],
      reactHooks.configs.flat.recommended,
      // No eslint-plugin-react-refresh: its only rule was off because several component
      // modules also export helpers or contexts (e.g. LoginScreen's role helpers).
    ],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      // eslint-plugin-react-hooks owns the hook and React Compiler rules (disable comments in
      // src name them). @eslint-react ships copies of the same checks; turn those off so each
      // finding is reported once, under the name the comments use.
      '@eslint-react/error-boundaries': 'off',
      '@eslint-react/exhaustive-deps': 'off',
      '@eslint-react/purity': 'off',
      '@eslint-react/rules-of-hooks': 'off',
      '@eslint-react/set-state-in-effect': 'off',
      '@eslint-react/set-state-in-render': 'off',
      '@eslint-react/static-components': 'off',
      '@eslint-react/unsupported-syntax': 'off',
      '@eslint-react/use-memo': 'off',
      '@eslint-react/dom-no-unknown-property': 'error',
      '@eslint-react/dom-no-unsafe-target-blank': 'error',
      '@eslint-react/jsx-no-children-prop': 'error',
      '@eslint-react/jsx-no-comment-textnodes': 'error',
      '@eslint-react/no-missing-component-display-name': 'error',
      // Index keys are flagged even for static message lists, where messages can repeat and
      // the position is the only stable identity; that is every current use.
      '@eslint-react/no-array-index-key': 'off',
      // Keep the lazy-initial-state check; setter names follow the state they set, not a
      // naming rule (NotificationsPage's `scopeChoice` is set by `setScope`).
      '@eslint-react/use-state': ['warn', { enforceSetterName: false }],
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/no-explicit-any': 'warn',
      'no-console': 'off',
    },
  },
]);
