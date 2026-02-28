/**
 * MSAL (Microsoft Authentication Library) configuration.
 *
 * All values are read from Vite environment variables so that no
 * credentials are hard-coded.  Create a `.env` file at the frontend root
 * (see `.env.example`) and restart the dev server after editing it.
 */

import { PublicClientApplication, LogLevel } from "@azure/msal-browser";

// ---------------------------------------------------------------------------
// MSAL instance
// ---------------------------------------------------------------------------

const msalConfig = {
  auth: {
    clientId: import.meta.env.VITE_AZURE_CLIENT_ID ?? "",
    authority: `https://login.microsoftonline.com/${import.meta.env.VITE_AZURE_TENANT_ID ?? "common"}`,
    redirectUri: import.meta.env.VITE_REDIRECT_URI ?? window.location.origin,
    postLogoutRedirectUri: import.meta.env.VITE_REDIRECT_URI ?? window.location.origin,
  },
  cache: {
    cacheLocation: "sessionStorage",
    storeAuthStateInCookie: false,
  },
  system: {
    loggerOptions: {
      logLevel: LogLevel.Warning,
    },
  },
};

export const msalInstance = new PublicClientApplication(msalConfig);

// ---------------------------------------------------------------------------
// Token-request scopes
//
// Use the value of VITE_API_SCOPE when your backend is registered as a
// separate API app (e.g. "api://<client-id>/access_as_user").
// Fall back to "openid profile email" for simpler single-app setups.
// ---------------------------------------------------------------------------

export const loginRequest = {
  scopes: (import.meta.env.VITE_API_SCOPE ?? "openid profile email").split(" "),
};
