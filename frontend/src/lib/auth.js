import { InteractionRequiredAuthError } from "@azure/msal-browser";
import { msalInstance, loginRequest } from "../authConfig.js";

/** True when auth is configured (VITE_AZURE_CLIENT_ID is set). */
export const authEnabled = !!import.meta.env.VITE_AZURE_CLIENT_ID;

/**
 * Acquire a bearer token silently.
 * Returns an empty string when auth is not configured (no client ID set).
 *
 * If interactive consent is needed (e.g. a new scope was added), we use a
 * popup so that the current page is NOT navigated away — preserving any
 * in-progress form data.
 *
 * @param {{ forceRefresh?: boolean }} options
 */
export async function getBearerToken({ forceRefresh = false } = {}) {
  if (!authEnabled) return "";

  const account = msalInstance.getActiveAccount() ?? msalInstance.getAllAccounts()[0];
  if (!account) return "";

  try {
    const result = await msalInstance.acquireTokenSilent({
      ...loginRequest,
      account,
      forceRefresh,
    });
    return result.accessToken;
  } catch (error) {
    // Only prompt interactively when the error actually requires it
    // (consent, MFA, expired refresh token, etc.)
    if (error instanceof InteractionRequiredAuthError) {
      try {
        const result = await msalInstance.acquireTokenPopup({
          ...loginRequest,
          account,
        });
        return result.accessToken;
      } catch (popupError) {
        console.error("Interactive token acquisition failed", popupError);
        return "";
      }
    }
    console.error("Silent token acquisition failed", error);
    return "";
  }
}

export async function authHeaders({ forceRefresh = false } = {}) {
  const token = await getBearerToken({ forceRefresh });
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * Force-redirect the user to the login page.
 * Called when a fresh token cannot be obtained and the backend returns 401.
 */
export function redirectToLogin() {
  msalInstance.loginRedirect();
}
