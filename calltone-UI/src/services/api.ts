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

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("calltone_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("calltone_token");
      localStorage.removeItem("calltone_user");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

export type ApiUserRole = "agent" | "qa" | "admin" | "super_admin" | "manager" | "viewer";

export interface AuthApiUser {
  id: number;
  name: string;
  email: string;
  role: ApiUserRole;
  clientId: number | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthApiUser;
}

export interface MeResponse {
  id: number;
  name: string;
  email: string;
  role: ApiUserRole;
  clientId: number | null;
  isActive: boolean;
  lastLoginAt: string | null;
}

export interface AdminDashboardResponse {
  kpis: {
    activeClients: number;
    trialClients: number;
    totalClients: number;
    totalAgents: number;
    callsThisMonth: number;
    monthlyRevenue: number;
  };
  health: {
    avgQualityScore: number;
    activeClients: number;
    trialConversions: number;
    churnRate: number;
    uptime: number;
  };
  trends: {
    revenue: Array<{ month: string; revenue: number }>;
    calls: Array<{ month: string; calls: number }>;
  };
}

export interface AdminClientItem {
  id: number;
  name: string;
  industry: string;
  status: "active" | "trial" | "churned" | "suspended";
  plan: "starter" | "professional" | "enterprise" | string;
  agents: number;
  qaCount: number;
  callsThisMonth: number;
  mrr: number;
  avgScore: number;
}

export interface AdminClientsResponse {
  summary: {
    totalClients: number;
    activeClients: number;
    trialClients: number;
    totalAgents: number;
    totalCalls: number;
    totalMRR: number;
  };
  clients: AdminClientItem[];
}

export type AdminTeamRole = "super_admin" | "admin" | "manager" | "viewer" | "qa" | "agent";
export type AdminTeamStatus = "active" | "disabled" | "invited";

export interface AdminTeamUser {
  id: number;
  name: string;
  email: string;
  role: AdminTeamRole;
  status: AdminTeamStatus;
  lastLogin: string | null;
  clientId: number | null;
}

export interface AdminUsersResponse {
  currentUserId: number;
  users: AdminTeamUser[];
}

export interface InviteUserPayload {
  name: string;
  email: string;
  role: "admin" | "manager" | "viewer" | "qa" | "agent";
}

export interface InviteUserResponse {
  message: string;
  inviteUrl: string;
  user: AdminTeamUser;
}

export interface InviteDetailsResponse {
  name: string;
  email: string;
  role: "admin" | "manager" | "viewer" | "qa" | "agent" | "super_admin";
  expiresAt: string;
}

export interface AcceptInvitePayload {
  token: string;
  password: string;
  confirmPassword: string;
}

export interface AcceptInviteResponse {
  message: string;
}


export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post<LoginResponse>("/auth/login", { email, password }),

  logout: () => apiClient.post("/auth/logout"),

  me: () => apiClient.get<MeResponse>("/auth/me"),

  getInviteDetails: (token: string) =>
    apiClient.get<InviteDetailsResponse>(`/auth/invite/${encodeURIComponent(token)}`),

  acceptInvite: (payload: AcceptInvitePayload) =>
    apiClient.post<AcceptInviteResponse>("/auth/invite/accept", payload),
};

export interface UpdateUserRolePayload {
  role: "admin" | "manager" | "viewer" | "qa" | "agent";
}

export interface UpdateUserStatusPayload {
  status: "active" | "disabled";
}

export interface InviteLinkResponse {
  inviteUrl: string;
}

export interface DeleteUserResponse {
  message: string;
  deletedType: "invitation" | "user";
  name: string;
}

export const agentApi = {
  getDashboard: (range: string) =>
    apiClient.get<{ scores: Record<string, number>; trend: Array<Record<string, number>> }>(
      "/agent/dashboard",
      { params: { range } }
    ),

  getCalls: (params: { range?: string; sortBy?: "time" | "rating"; page?: number }) =>
    apiClient.get<{ calls: Call[]; total: number }>("/agent/calls", { params }),
};

export const qaApi = {
  getSummary: (range: string) =>
    apiClient.get<{ totalCalls: number; avgScore: number; flaggedCalls: number }>(
      "/qa/summary",
      { params: { range } }
    ),
  getCallsList: () =>
  apiClient.get<QaCallListResponse>("/qa/calls"),

  getCallDetailReal: (callId: string) =>
    apiClient.get<QaCallDetailResponse>(`/qa/calls/${callId}`),
  

  getAgents: (range: string) => apiClient.get<Agent[]>("/qa/agents", { params: { range } }),

  getAgentCalls: (agentId: string, params: { range?: string; sortBy?: "time" | "rating" }) =>
    apiClient.get<Call[]>(`/qa/agents/${agentId}/calls`, { params }),

  getCallDetail: (callId: string) => apiClient.get<CallDetail>(`/qa/calls/${callId}`),
};

export const adminApi = {
  getDashboard: () => apiClient.get<AdminDashboardResponse>("/admin/dashboard"),
  getClients: () => apiClient.get<AdminClientsResponse>("/admin/clients"),
  getUsers: () => apiClient.get<AdminUsersResponse>("/admin/users"),
  inviteUser: (payload: InviteUserPayload) =>
    apiClient.post<InviteUserResponse>("/admin/users/invite", payload),

  updateUserRole: (userId: number, payload: UpdateUserRolePayload) =>
    apiClient.patch(`/admin/users/${userId}/role`, payload),

  updateUserStatus: (userId: number, payload: UpdateUserStatusPayload) =>
    apiClient.patch(`/admin/users/${userId}/status`, payload),

  getInviteLink: (userId: number) =>
    apiClient.get<InviteLinkResponse>(`/admin/users/${userId}/invite-link`),

  deleteUser: (userId: number) =>
    apiClient.delete<DeleteUserResponse>(`/admin/users/${userId}`),
};


export interface QaCallItem {
  callId: string;
  filename: string;
  callTime: string | null;
  status: string;
  agentName: string;
  overallScore: number | null;
  severity: string | null;
}

export interface QaCallListResponse {
  calls: QaCallItem[];
}

export interface QaCallDetailResponse {
  callId: string;
  filename: string;
  driveFileId: string;
  drivePreviewUrl: string | null;
  driveDownloadUrl: string | null;
  callTime: string | null;
  durationSeconds: number | null;
  status: string;
  agentName: string;
  transcript: {
    fullText: string;
    speakerTurns: Array<{
      start: number;
      end: number;
      speaker: string;
      profile: string;
      text: string;
    }>;
  };
  report: {
    overallScore: number | null;
    grade: string | null;
    severity: string | null;
    dimensionScores: Record<string, number>;
    dimensionReports: Record<string, string>;
    evidence: Array<{
      dimension: string;
      quote: string;
      speaker: string;
      reason: string;
    }>;
    confidenceScores: Record<string, number>;
    reportJson: {
      summary?: string;
      strengths?: string[];
      weaknesses?: string[];
      recommended_actions?: string[];
    };
  };
}

export default apiClient;