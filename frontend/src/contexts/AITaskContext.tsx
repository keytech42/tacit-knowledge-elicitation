import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ai, type AITask } from "@/api/client";
import { useToast } from "@/components/ToastContext";

const TASK_TYPE_LABELS: Record<string, string> = {
  generate_questions: "Question Generation",
  extract_questions: "Question Extraction",
  scaffold_options: "Answer Scaffolding",
  review_assist: "Review Assist",
};

function taskLabel(taskType: string): string {
  return TASK_TYPE_LABELS[taskType] || taskType;
}

function isActive(status: string): boolean {
  return status === "pending" || status === "running";
}

interface AITaskContextValue {
  tasks: Map<string, AITask>;
  activeCount: number;
  addTask: (task: AITask) => void;
  cancelTask: (id: string) => Promise<void>;
  getTask: (id: string) => AITask | undefined;
  getTasksByType: (taskType: string) => AITask[];
}

const AITaskContext = createContext<AITaskContextValue | null>(null);

const POLL_INTERVAL = 3000;

export function AITaskProvider({ children }: { children: ReactNode }) {
  const toast = useToast();
  const [tasks, setTasks] = useState<Map<string, AITask>>(new Map());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Track tasks we've already notified about to avoid duplicate toasts
  const notifiedRef = useRef<Set<string>>(new Set());

  // Single interval that polls all active tasks
  useEffect(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    const activeIds = Array.from(tasks.values())
      .filter((t) => isActive(t.status))
      .map((t) => t.id);

    if (activeIds.length === 0) return;

    intervalRef.current = setInterval(async () => {
      const updates: AITask[] = [];

      await Promise.all(
        activeIds.map(async (id) => {
          try {
            const fresh = await ai.getTaskStatus(id);
            updates.push(fresh);
          } catch {
            // If fetch fails, mark as failed
            updates.push({
              ...tasks.get(id)!,
              status: "failed",
              error: "Lost connection to task",
            });
          }
        })
      );

      if (updates.length === 0) return;

      setTasks((prev) => {
        const next = new Map(prev);
        for (const task of updates) {
          const old = next.get(task.id);
          next.set(task.id, task);

          // Notify on terminal state transitions
          if (old && isActive(old.status) && !isActive(task.status)) {
            if (!notifiedRef.current.has(task.id)) {
              notifiedRef.current.add(task.id);
            }
            const label = taskLabel(task.task_type);
            if (task.status === "completed") {
              toast.success(`${label} completed`);
            } else if (task.status === "failed") {
              const snippet = task.error ? `: ${task.error.slice(0, 80)}` : "";
              toast.error(`${label} failed${snippet}`);
            } else if (task.status === "cancelled") {
              toast.info(`${label} cancelled`);
            }
          }
        }
        return next;
      });
    }, POLL_INTERVAL);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [tasks, toast]);

  const addTask = useCallback((task: AITask) => {
    setTasks((prev) => {
      const next = new Map(prev);
      next.set(task.id, task);
      return next;
    });
  }, []);

  const cancelTaskFn = useCallback(async (id: string) => {
    try {
      const updated = await ai.cancelTask(id);
      setTasks((prev) => {
        const next = new Map(prev);
        next.set(id, updated);
        return next;
      });
      toast.info(`${taskLabel(updated.task_type)} cancelled`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to cancel task");
    }
  }, [toast]);

  const getTask = useCallback(
    (id: string) => tasks.get(id),
    [tasks]
  );

  const getTasksByType = useCallback(
    (taskType: string) =>
      Array.from(tasks.values()).filter((t) => t.task_type === taskType),
    [tasks]
  );

  const activeCount = Array.from(tasks.values()).filter((t) =>
    isActive(t.status)
  ).length;

  return (
    <AITaskContext.Provider
      value={{ tasks, activeCount, addTask, cancelTask: cancelTaskFn, getTask, getTasksByType }}
    >
      {children}
    </AITaskContext.Provider>
  );
}

export function useAITasks() {
  const ctx = useContext(AITaskContext);
  if (!ctx) throw new Error("useAITasks must be used within AITaskProvider");
  return ctx;
}

export { TASK_TYPE_LABELS, taskLabel };
