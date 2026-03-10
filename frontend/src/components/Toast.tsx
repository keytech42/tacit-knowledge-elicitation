import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Toast as ToastType } from "./ToastContext";

function ToastItem({ toast, onDismiss }: { toast: ToastType; onDismiss: () => void }) {
  const [state, setState] = useState<"entering" | "visible" | "exiting">("entering");
  const timerRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    const frame = requestAnimationFrame(() => setState("visible"));
    return () => cancelAnimationFrame(frame);
  }, []);

  const startExit = useCallback(() => {
    if (state === "exiting") return;
    setState("exiting");
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(onDismiss, 300);
  }, [state, onDismiss]);

  useEffect(() => {
    const duration = toast.type === "error" ? 5000 : 3000;
    const timer = setTimeout(startExit, duration);
    return () => clearTimeout(timer);
  }, [toast.type, startExit]);

  useEffect(() => {
    return () => clearTimeout(timerRef.current);
  }, []);

  const accentClass =
    toast.type === "success" ? "border-l-status-green" :
    toast.type === "info" ? "border-l-status-blue" :
    "border-l-status-red";

  const transformClass =
    state === "entering"
      ? "translate-x-full opacity-0"
      : state === "exiting"
        ? "translate-x-full opacity-0"
        : "translate-x-0 opacity-100";

  return (
    <div
      className={`flex items-start gap-3 bg-background border border-border shadow-lg rounded-lg px-4 py-3 min-w-[300px] border-l-4 ${accentClass} transition-all duration-300 ease-out ${transformClass}`}
    >
      <p className="text-sm text-foreground flex-1">{toast.message}</p>
      {toast.type === "error" && (
        <button
          onClick={startExit}
          className="shrink-0 text-muted-foreground hover:text-foreground transition-colors"
        >
          <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        </button>
      )}
    </div>
  );
}

export function ToastContainer({ toasts, dismiss }: { toasts: ToastType[]; dismiss: (id: string) => void }) {
  if (toasts.length === 0) return null;

  return createPortal(
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={() => dismiss(toast.id)} />
      ))}
    </div>,
    document.body,
  );
}
