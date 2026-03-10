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
    cache: "no-store",
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
  question_status: string | null;
  answer_status: string | null;
  approval_count: number | null;
  min_approvals: number | null;
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

// Source document types

export interface SourceDocument {
  id: string;
  title: string;
  domain: string | null;
  document_summary: string | null;
  question_count: number;
  uploaded_by: User;
  created_at: string;
  updated_at: string;
}

export interface SourceDocumentDetail extends SourceDocument {
  body: string;
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

export interface AITask {
  id: string;
  task_type: string;
  status: string; // pending, running, completed, failed, cancelled
  worker_task_id: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface AITaskListResponse {
  items: AITask[];
  total: number;
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
  strategy: "llm" | "embedding" | null;
}

// AI-related API functions

export const ai = {
  generateQuestions: (topic: string, domain = "", count = 3, context?: string) =>
    api.post<AITask>("/ai/generate-questions", { topic, domain, count, context }),

  scaffoldOptions: (questionId: string, numOptions = 4) =>
    api.post<AITask>("/ai/scaffold-options", {
      question_id: questionId,
      num_options: numOptions,
    }),

  reviewAssist: (answerId: string) =>
    api.post<AITask>("/ai/review-assist", { answer_id: answerId }),

  recommend: (questionId: string, topK = 5) =>
    api.post<RecommendationResponse>("/ai/recommend", {
      question_id: questionId,
      top_k: topK,
    }),

  getTaskStatus: (taskId: string) =>
    api.get<AITask>(`/ai/tasks/${taskId}`),

  listTasks: (status?: string) =>
    api.get<AITaskListResponse>(`/ai/tasks${status ? `?status=${status}` : ""}`),

  cancelTask: (id: string) =>
    api.post<AITask>(`/ai/tasks/${id}/cancel`, {}),

  extractQuestions: (sourceText: string, documentTitle = "", domain = "", maxQuestions = 10) =>
    api.post<AITask>("/ai/extract-questions", {
      source_text: sourceText,
      document_title: documentTitle,
      domain: domain,
      max_questions: maxQuestions,
    }),

  extractFromFile: async (file: File, documentTitle = "", domain = "", maxQuestions = 10) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("document_title", documentTitle);
    formData.append("domain", domain);
    formData.append("max_questions", String(maxQuestions));

    const token = localStorage.getItem("token");
    const resp = await fetch(`${API_BASE}/ai/extract-from-file`, {
      method: "POST",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: formData,
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || resp.statusText);
    }
    return resp.json() as Promise<AITask>;
  },

  assignRespondent: (questionId: string, userId: string) =>
    api.post<Question>(`/questions/${questionId}/assign-respondent`, { user_id: userId }),

  assignReviewer: (answerId: string, reviewerId: string) =>
    api.post<Review>(`/reviews/assign/${answerId}`, { reviewer_id: reviewerId }),

  searchUsers: (q = "", role?: string, limit = 20) => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (role) params.set("role", role);
    if (limit !== 20) params.set("limit", String(limit));
    return api.get<{ users: User[]; total: number }>(`/users/search?${params}`);
  },
};

// Source document API functions

export const sourceDocuments = {
  list: () => api.get<{ items: SourceDocument[]; total: number }>("/source-documents"),
  get: (id: string) => api.get<SourceDocumentDetail>(`/source-documents/${id}`),
  delete: (id: string) => api.delete(`/source-documents/${id}`),
};
