import { createContext, useCallback, useContext, useState } from "react";
import ConfirmDialog from "./components/ConfirmDialog";

const ConfirmContext = createContext(null);

/**
 * ConfirmDialogProvider — wraps the app tree and renders a single
 * shared ConfirmDialog instance.  Child components call useConfirm()
 * to trigger the dialog imperatively.
 */
export function ConfirmDialogProvider({ children }) {
  const [state, setState] = useState(null);

  const confirm = useCallback(
    ({ title, message, confirmLabel, cancelLabel, destructive } = {}) =>
      new Promise((resolve) => {
        setState({
          title,
          message,
          confirmLabel,
          cancelLabel,
          destructive,
          resolve,
        });
      }),
    []
  );

  const handleConfirm = () => {
    state?.resolve(true);
    setState(null);
  };

  const handleCancel = () => {
    state?.resolve(false);
    setState(null);
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      <ConfirmDialog
        open={!!state}
        title={state?.title}
        message={state?.message}
        confirmLabel={state?.confirmLabel}
        cancelLabel={state?.cancelLabel}
        destructive={state?.destructive}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </ConfirmContext.Provider>
  );
}

/**
 * useConfirm — returns an async function that opens a styled
 * confirm dialog and resolves to true (confirmed) or false (cancelled).
 *
 * Usage:
 *   const confirm = useConfirm();
 *   if (await confirm({ title: "Delete?", destructive: true })) { … }
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm must be used within ConfirmDialogProvider");
  return ctx;
}
