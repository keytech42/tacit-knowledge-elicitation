import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { ToastContainer } from "./Toast";

export interface Toast {
  id: string;
  message: string;
  type: "success" | "error";
}

interface ToastContextValue {
  toasts: Toast[];
  success: (message: string) => void;
  error: (message: string) => void;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const MAX_VISIBLE = 3;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((message: string, type: "success" | "error") => {
    const id = crypto.randomUUID();

    setToasts((prev) => {
      const next = [...prev, { id, message, type }];
      if (next.length > MAX_VISIBLE) {
        const overflow = next.slice(0, next.length - MAX_VISIBLE);
        overflow.forEach((t) => {
          setTimeout(() => dismiss(t.id), 0);
        });
      }
      return next;
    });
  }, [dismiss]);

  const success = useCallback((message: string) => addToast(message, "success"), [addToast]);
  const error = useCallback((message: string) => addToast(message, "error"), [addToast]);

  return (
    <ToastContext.Provider value={{ toasts, success, error, dismiss }}>
      {children}
      <ToastContainer toasts={toasts} dismiss={dismiss} />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
