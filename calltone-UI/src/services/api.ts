import axios from "axios";
import type { Call, Agent, CallDetail } from "@/data/mockData";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 10000,
});

// Request interceptor — attach auth token when available
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("calltone_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor — handle 401 globally
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("calltone_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

// ──── Auth ────
export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post<{ token: string; user: { name: string; role: "agent" | "qa" } }>("/auth/login", { email, password }),

  logout: () => apiClient.post("/auth/logout"),

  me: () => apiClient.get<{ name: string; role: "agent" | "qa"; email: string }>("/auth/me"),
};

// ──── Agent ────
export const agentApi = {
  getDashboard: (range: string) =>
    apiClient.get<{ scores: Record<string, number>; trend: Array<Record<string, number>> }>("/agent/dashboard", { params: { range } }),

  getCalls: (params: { range?: string; sortBy?: "time" | "rating"; page?: number }) =>
    apiClient.get<{ calls: Call[]; total: number }>("/agent/calls", { params }),
};

// ──── QA ────
export const qaApi = {
  getSummary: (range: string) =>
    apiClient.get<{ totalCalls: number; avgScore: number; flaggedCalls: number }>("/qa/summary", { params: { range } }),

  getAgents: (range: string) =>
    apiClient.get<Agent[]>("/qa/agents", { params: { range } }),

  getAgentCalls: (agentId: string, params: { range?: string; sortBy?: "time" | "rating" }) =>
    apiClient.get<Call[]>(`/qa/agents/${agentId}/calls`, { params }),

  getCallDetail: (callId: string) =>
    apiClient.get<CallDetail>(`/qa/calls/${callId}`),
};

export default apiClient;
