import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { MsalProvider } from "@azure/msal-react";
import App from "./App.jsx";
import { msalInstance } from "./authConfig.js";
import "./index.css";

/**
 * Render the React tree.  Called once MSAL is ready (or on error so the
 * user is never stuck on a blank page).
 */
function render() {
  createRoot(document.getElementById("root")).render(
    <StrictMode>
      <MsalProvider instance={msalInstance}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </MsalProvider>
    </StrictMode>
  );
}

// MSAL Browser v3+ requires initialize() before any other API call.
// handleRedirectPromise() must also resolve before rendering so that
// returning from login/logout redirect doesn't flash unauthenticated UI.
msalInstance
  .initialize()
  .then(() => msalInstance.handleRedirectPromise())
  .then((response) => {
    // If we just came back from a redirect login, set the account active.
    if (response?.account) {
      msalInstance.setActiveAccount(response.account);
    } else if (
      !msalInstance.getActiveAccount() &&
      msalInstance.getAllAccounts().length > 0
    ) {
      msalInstance.setActiveAccount(msalInstance.getAllAccounts()[0]);
    }
    render();
  })
  .catch((error) => {
    console.error("MSAL initialisation failed – rendering app anyway", error);
    render();
  });
