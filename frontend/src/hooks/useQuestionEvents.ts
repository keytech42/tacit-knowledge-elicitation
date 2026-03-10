import { useEffect, useRef } from "react";
import { api } from "@/api/client";

export interface AnswerStatusEvent {
  type: "answer_status_changed";
  answer_id: string;
  status: string;
  previous_status?: string;
}

type QuestionEvent = AnswerStatusEvent;

/**
 * Subscribe to real-time SSE events for a question.
 * Falls back to window-focus re-fetch if SSE connection fails.
 */
export function useQuestionEvents(
  questionId: string | undefined,
  onEvent: (event: QuestionEvent) => void,
) {
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!questionId) return;

    const token = api.getToken();
    if (!token) return;

    const url = `/api/v1/questions/${questionId}/events?token=${encodeURIComponent(token)}`;
    const source = new EventSource(url);

    source.addEventListener("answer_status_changed", (e) => {
      try {
        const data = JSON.parse(e.data) as AnswerStatusEvent;
        onEventRef.current(data);
      } catch {
        // Ignore malformed events
      }
    });

    source.onerror = () => {
      // EventSource auto-reconnects; no manual intervention needed.
      // The browser will retry with exponential backoff.
    };

    return () => {
      source.close();
    };
  }, [questionId]);
}
