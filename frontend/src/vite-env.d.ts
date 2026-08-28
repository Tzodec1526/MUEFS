/* eslint-disable @typescript-eslint/no-unused-vars */
/// <reference types="vite/client" />



interface ImportMetaEnv {

  readonly VITE_API_URL?: string;

  /** When true, send X-Demo-User-Id for local role-picker (must match backend ALLOW_DEMO_MODE). */

  readonly VITE_ALLOW_DEMO_MODE?: string;
  readonly VITE_DEMO_MODE_SECRET?: string;

  readonly VITE_KEYCLOAK_URL?: string;

  readonly VITE_KEYCLOAK_REALM?: string;

  readonly VITE_KEYCLOAK_CLIENT_ID?: string;

  readonly VITE_KEYCLOAK_REDIRECT_URI?: string;

}



interface ImportMeta {

  readonly env: ImportMetaEnv;

}



/** WebMCP declarative API attributes (experimental). */

declare module 'react' {

  interface FormHTMLAttributes<T> {

    toolname?: string;

    tooldescription?: string;

  }

  interface InputHTMLAttributes<T> {

    toolparamdescription?: string;

  }

  interface SelectHTMLAttributes<T> {

    toolparamdescription?: string;

  }

}



export {};


