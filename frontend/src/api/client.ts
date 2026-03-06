const API_BASE = "/api/v1";

function getToken(): string | null {
  return localStorage.getItem("token");
}

function setToken(token: string) {
  localStorage.setItem("token", token);
}

function clearToken() {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    clearToken();
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  setToken,
  getToken,
  clearToken,
};

export interface User {
  id: string;
  user_type: string;
  display_name: string;
  email: string | null;
  avatar_url: string | null;
  is_active: boolean;
  roles: { id: string; name: string }[];
  created_at: string;
}

export interface Question {
  id: string;
  title: string;
  body: string;
  category: string | null;
  status: string;
  confirmation: string;
  review_policy: Record<string, unknown> | null;
  show_suggestions: boolean;
  quality_score: number | null;
  created_by: User;
  confirmed_by: User | null;
  assigned_respondent: User | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  answer_options: AnswerOption[];
}

export interface AnswerOption {
  id: string;
  body: string;
  display_order: number;
  created_by: User;
  created_at: string;
}

export interface Answer {
  id: string;
  question_id: string;
  author: User;
  body: string;
  selected_option_id: string | null;
  status: string;
  current_version: number;
  confirmed_by: User | null;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Review {
  id: string;
  target_type: string;
  target_id: string;
  reviewer: User;
  assigned_by: User | null;
  verdict: string;
  comment: string | null;
  answer_version: number | null;
  question_title: string | null;
  comments: ReviewComment[];
  created_at: string;
  updated_at: string;
}

export interface ReviewComment {
  id: string;
  review_id: string;
  author: User;
  body: string;
  parent_id: string | null;
  created_at: string;
}

export interface AnswerRevision {
  id: string;
  answer_id: string;
  version: number;
  body: string;
  created_by: User;
  trigger: string;
  previous_status: string | null;
  created_at: string;
}

// AI-related types

export interface TaskAccepted {
  task_id: string;
  status: string;
}

export interface TaskStatus {
  task_id: string;
  status: string; // accepted, running, completed, failed
  result?: Record<string, unknown>;
  error?: string;
}

export interface Recommendation {
  user_id: string;
  display_name: string;
  score: number;
  reasoning: string;
}

export interface RecommendationResponse {
  items: Recommendation[];
  reason: string | null;
}

// AI-related API functions

export const ai = {
  generateQuestions: (topic: string, domain = "", count = 3, context?: string) =>
    api.post<TaskAccepted>("/ai/generate-questions", { topic, domain, count, context }),

  scaffoldOptions: (questionId: string, numOptions = 4) =>
    api.post<TaskAccepted>("/ai/scaffold-options", {
      question_id: questionId,
      num_options: numOptions,
    }),

  reviewAssist: (answerId: string) =>
    api.post<TaskAccepted>("/ai/review-assist", { answer_id: answerId }),

  recommend: (questionId: string, topK = 5) =>
    api.post<RecommendationResponse>("/ai/recommend", {
      question_id: questionId,
      top_k: topK,
    }),

  getTaskStatus: (taskId: string) =>
    api.get<TaskStatus>(`/ai/tasks/${taskId}`),

  assignRespondent: (questionId: string, userId: string) =>
    api.post<Question>(`/questions/${questionId}/assign-respondent`, { user_id: userId }),
};
