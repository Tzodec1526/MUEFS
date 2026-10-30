interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_ALLOW_DEMO_MODE?: string;
  readonly VITE_DEMO_MODE_SECRET?: string;
  readonly VITE_KEYCLOAK_URL?: string;
  readonly VITE_KEYCLOAK_REALM?: string;
  readonly VITE_KEYCLOAK_CLIENT_ID?: string;
  readonly VITE_KEYCLOAK_REDIRECT_URI?: string;
}

declare module 'node:fs' {
  export function readdirSync(path: URL): string[];
  export function readFileSync(path: URL, encoding: 'utf8'): string;
}
