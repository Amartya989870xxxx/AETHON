import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { AnimatePresence, motion } from "framer-motion";
import { cx } from "../lib/cx";

type ToastKind = "info" | "success" | "error" | "alert";

interface Toast {
  id: number;
  kind: ToastKind;
  title: string;
  body?: string;
}

interface ToastApi {
  push: (t: Omit<Toast, "id">) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

const KIND_STYLES: Record<ToastKind, string> = {
  info: "border-white/10",
  success: "border-signal-ok/40",
  error: "border-signal-critical/40",
  alert: "border-violet-500/50",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = nextId.current++;
    setToasts((prev) => [...prev, { ...t, id }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((x) => x.id !== id));
    }, 5200);
  }, []);

  const api = useMemo<ToastApi>(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
        <AnimatePresence initial={false}>
          {toasts.map((t) => (
            <motion.div
              key={t.id}
              layout
              initial={{ opacity: 0, x: 40, scale: 0.96 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 40, scale: 0.96 }}
              transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
              className={cx(
                "glass pointer-events-auto p-3.5",
                KIND_STYLES[t.kind],
              )}
              onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
            >
              <p className="text-sm font-medium text-ink-100">{t.title}</p>
              {t.body && (
                <p className="mt-0.5 text-xs leading-relaxed text-ink-400">
                  {t.body}
                </p>
              )}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside ToastProvider");
  return ctx;
}
