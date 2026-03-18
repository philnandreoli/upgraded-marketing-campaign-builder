import { InteractionRequiredAuthError } from "@azure/msal-browser";
import { msalInstance, loginRequest } from "../authConfig.js";

/**
 * Acquire a bearer token silently.
 * Returns an empty string when auth is not configured (no client ID set).
 *
 * If interactive consent is needed (e.g. a new scope was added), we use a
 * popup so that the current page is NOT navigated away — preserving any
 * in-progress form data.
 */
export async function getBearerToken() {
  const clientId = import.meta.env.VITE_AZURE_CLIENT_ID;
  if (!clientId) return "";

  const account = msalInstance.getActiveAccount() ?? msalInstance.getAllAccounts()[0];
  if (!account) return "";

  try {
    const result = await msalInstance.acquireTokenSilent({
      ...loginRequest,
      account,
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

export async function authHeaders() {
  const token = await getBearerToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
