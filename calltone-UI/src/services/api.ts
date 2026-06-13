import axios from "axios";
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

// Accepted audio MIME types for the /api/calls/upload endpoint.
// Kept in sync with backend ALLOWED_AUDIO_TYPES.
export const ACCEPTED_AUDIO_TYPES = [
  "audio/mpeg",
  "audio/wav",
  "audio/x-wav",
  "audio/mp3",
  "audio/flac",
  "audio/ogg",
  "audio/webm",
] as const;

export const MAX_UPLOAD_SIZE_BYTES = 200 * 1024 * 1024;

/** Pure predicate: does the file look like a supported audio upload? */
export function isAudioFile(file: Pick<File, "name" | "type">): boolean {
  if (file.type && (ACCEPTED_AUDIO_TYPES as readonly string[]).includes(file.type)) {
    return true;
  }
  const ext = file.name.toLowerCase().split(".").pop() ?? "";
  return ["wav", "mp3", "mpeg", "flac", "ogg", "webm", "m4a"].includes(ext);
}

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === "object" && "response" in error) {
    const response = (error as { response?: { data?: { detail?: unknown } } }).response;
    if (typeof response?.data?.detail === "string") return response.data.detail;
  }
  return fallback;
}

export type ApiUserRole = "owner" | "agent" | "qa" | "admin" | "super_admin" | "manager" | "viewer";

export interface UserCapabilities {
  canUseAdmin?: boolean;
  canManageUsers?: boolean;
  canManageClients?: boolean;
  canUseQa?: boolean;
  canUploadCalls?: boolean;
  canManageContext?: boolean;
  canViewAgentDashboard?: boolean;
  canViewAgentCalls?: boolean;
  canPlayAudio?: boolean;
  canViewTranscript?: boolean;
  canViewScores?: boolean;
  canViewEvidence?: boolean;
  canViewAiReport?: boolean;
  canViewTrends?: boolean;
}

export interface AuthApiUser {
  id: number;
  name: string;
  email: string;
  role: ApiUserRole;
  clientId: number | null;
  clientName?: string | null;
  roleScope?: "platform" | "tenant";
  capabilities?: UserCapabilities;
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
  clientName?: string | null;
  roleScope?: "platform" | "tenant";
  capabilities?: UserCapabilities;
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
    completedCalls?: number;
    totalCalls?: number;
    flaggedCalls?: number;
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

export interface CreateClientPayload {
  name: string;
  industry?: string;
  status?: "active" | "trial" | "churned" | "suspended";
  plan?: "starter" | "professional" | "enterprise" | "trial" | string;
}

export interface CreateClientResponse {
  client: AdminClientItem;
}

export interface UploadAgent {
  id: string;
  name: string;
  clientId: number | null;
  clientName: string | null;
  userId: number | null;
  email: string | null;
}

export interface UploadAgentsResponse {
  agents: UploadAgent[];
}

export interface ClientPolicy {
  clientId: number;
  agentPortalEnabled: boolean;
  agentCanViewCallList: boolean;
  agentCanOpenCallDetail: boolean;
  agentCanPlayAudio: boolean;
  agentCanViewTranscript: boolean;
  agentCanViewScores: boolean;
  agentCanViewEvidence: boolean;
  agentCanViewAiReport: boolean;
  agentCanViewTrends: boolean;
  qaCanUploadCalls: boolean;
  qaCanManageContextTickets: boolean;
  qaScope: "company" | "assigned_team" | "own_uploads";
  tenantAdminCanInviteAdmins: boolean;
  updatedAt: string | null;
}

export interface ClientPolicyResponse {
  client: Pick<AdminClientItem, "id" | "name" | "status" | "plan">;
  policy: ClientPolicy;
}

export type AdminTeamRole = "owner" | "super_admin" | "admin" | "manager" | "viewer" | "qa" | "agent";
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
  role: "super_admin" | "admin" | "manager" | "viewer" | "qa" | "agent";
  clientId?: number | null;
}

export interface InviteUserResponse {
  message: string;
  inviteUrl: string;
  emailStatus?: "queued" | "sent" | "failed" | "suppressed";
  emailMessageId?: string | null;
  user: AdminTeamUser;
}

export interface InviteDetailsResponse {
  name: string;
  email: string;
  role: "owner" | "super_admin" | "admin" | "manager" | "viewer" | "qa" | "agent";
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
  role: "super_admin" | "admin" | "manager" | "viewer" | "qa" | "agent";
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

export interface MailEventSummary {
  id: string;
  eventType: string;
  recipientEmail: string;
  subject: string;
  status: "queued" | "sent" | "failed" | "suppressed";
  provider: string;
  providerMessageId: string | null;
  error: string | null;
  createdAt: string | null;
  sentAt: string | null;
}

export interface MailSettingsResponse {
  enabled: boolean;
  configured: boolean;
  provider: string;
  fromEmail: string;
  fromName: string | null;
  replyTo: string;
  appBaseUrl: string;
  apiBaseUrl: string;
  logoUrl: string;
  lastEvent: MailEventSummary | null;
}

export interface MailTestResponse {
  ok: boolean;
  event: MailEventSummary;
}

export const agentApi = {
  getDashboard: (range: string) =>
    apiClient.get<{ scores: Record<string, number>; trend: Array<Record<string, number>> }>(
      "/agent/dashboard",
      { params: { range } }
    ),

  getCalls: (params: { range?: string; sortBy?: "time" | "rating"; page?: number }) =>
    apiClient.get<{ calls: QaCallItem[]; total: number }>("/agent/calls", { params }),
};

export const qaApi = {
  getCallsList: () =>
  apiClient.get<QaCallListResponse>("/qa/calls"),

  getCallDetailReal: (callId: string) =>
    apiClient.get<QaCallDetailResponse>(`/qa/calls/${callId}`),
  

  getAgentCalls: (agentId: string, params: { range?: string; sortBy?: "time" | "rating" }) =>
    apiClient.get<QaCallItem[]>(`/qa/agents/${agentId}/calls`, { params }),
};

export interface UploadCallResponse {
  callId: string;
  filename: string;
  status: string;
  message: string;
  queuePosition?: number | null;
  etaSeconds?: number | null;
}

export type AsrEngine = "fasterwhisper" | "sensevoice";

export interface CallStatusResponse {
  callId: string;
  status: string;
  currentStep: string;
  hasTranscript: boolean;
  hasReport: boolean;
  error: string | null;
  queuePosition?: number | null;
  queuedCount?: number | null;
  etaSeconds?: number | null;
}

export const callsApi = {
  upload: (
    file: File,
    agentId?: string,
    asrEngine: AsrEngine = "fasterwhisper",
    companyName?: string,
  ) => {
    const formData = new FormData();
    formData.append("file", file);
    if (agentId) formData.append("agent_id", agentId);
    formData.append("asr_engine", asrEngine);
    if (companyName) formData.append("company_name", companyName);
    return apiClient.post<UploadCallResponse>("/calls/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 600000,
    });
  },

  getStatus: (callId: string) =>
    apiClient.get<CallStatusResponse>(`/calls/${callId}/status`),
};

export const adminApi = {
  getDashboard: () => apiClient.get<AdminDashboardResponse>("/admin/dashboard"),
  getClients: () => apiClient.get<AdminClientsResponse>("/admin/clients"),
  createClient: (payload: CreateClientPayload) =>
    apiClient.post<CreateClientResponse>("/admin/clients", payload),
  getClientPolicy: (clientId?: number | null) =>
    apiClient.get<ClientPolicyResponse>("/admin/client-policy", {
      params: clientId ? { client_id: clientId } : undefined,
    }),
  updateClientPolicy: (payload: Partial<ClientPolicy> & { clientId?: number | null }) =>
    apiClient.put<ClientPolicyResponse>("/admin/client-policy", payload),
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

export const agentsApi = {
  list: (clientId?: number | null) =>
    apiClient.get<UploadAgentsResponse>("/agents", {
      params: clientId ? { client_id: clientId } : undefined,
    }),
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
  audioUrl: string | null;
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
      profile?: string;
      role?: string;
      text: string;
      emotion?: string;
      audio_emotion?: string;
      signals?: string[];
      event?: string;
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

// ── Pipeline Settings ──────────────────────────────────────────────────────

export interface PipelineSettingsResponse {
  audioMode:     "none" | "denoise" | "enhance";
  injectionScan: "static" | "llm";
  numSpeakers:   number | null;
  reportMode:    "none" | "simple" | "narrative" | "both";
  useConsensus:  boolean;
  companyName:   string;
}

export interface PipelineQueueResponse {
  activeCallId: string | null;
  queuedCount: number;
  queuedCallIds: string[];
  runningCallIds: string[];
  failedCount: number;
  failedCallIds: string[];
  etaSecondsPerJob: number;
  estimatedDrainSeconds: number;
}

export interface PipelineJobResponse {
  id: string;
  callId: string;
  audioPath: string;
  asrEngine: AsrEngine;
  companyName: string | null;
  status: "queued" | "running" | "completed" | "failed";
  priority: number;
  attempts: number;
  maxAttempts: number;
  errorMessage: string | null;
  lockedAt: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface PipelineJobsResponse {
  jobs: PipelineJobResponse[];
}

export const pipelineApi = {
  getSettings: () =>
    apiClient.get<PipelineSettingsResponse>("/settings/pipeline"),
  updateSettings: (payload: Partial<PipelineSettingsResponse>) =>
    apiClient.put<PipelineSettingsResponse>("/settings/pipeline", payload),
  getQueue: () =>
    apiClient.get<PipelineQueueResponse>("/pipeline/queue"),
  getJobs: (statusFilter?: PipelineJobResponse["status"], limit = 50) =>
    apiClient.get<PipelineJobsResponse>("/pipeline/jobs", {
      params: { status_filter: statusFilter, limit },
    }),
  retryJob: (callId: string) =>
    apiClient.post<{ ok: boolean; job: PipelineJobResponse }>(`/pipeline/jobs/${callId}/retry`),
  deadLetterJob: (callId: string) =>
    apiClient.post<{ ok: boolean; job: PipelineJobResponse }>(`/pipeline/jobs/${callId}/dead-letter`),
};

export const mailApi = {
  getSettings: () =>
    apiClient.get<MailSettingsResponse>("/settings/mail"),
  sendTest: () =>
    apiClient.post<MailTestResponse>("/settings/mail/test"),
};

// ── Company Context ────────────────────────────────────────────────────────

export interface CompanyContextSummary {
  name:       string;
  version:    string;
  updated:    string;
  file:       string;
  fieldCount: number;
}

export interface ContextTicket {
  ticket_id:    string;
  submitted_by: string;
  submitted_at: string;
  status:       "pending" | "approved" | "rejected";
  company_name: string;
  field_name:   string;
  old_text:     string;
  new_text:     string;
  reason:       string;
  reviewed_by?: string;
  reviewed_at?: string;
  review_note?: string;
}

export interface IngestResult {
  success:          boolean;
  company:          string;
  jsonPath:         string;
  atomicNodesCount: number;
  validation:       Record<string, unknown> | null;
  schema:           Record<string, string> | null;
}

export interface IngestJobStatus {
  status:     "running" | "completed" | "failed";
  progress:   string;
  result:     IngestResult | null;
  error:      string | null;
  company:    string;
  started_at: string;
}

export const contextApi = {
  listCompanies: () =>
    apiClient.get<{ companies: CompanyContextSummary[] }>("/context/companies"),

  getCompany: (name: string) =>
    apiClient.get<Record<string, unknown>>(`/context/companies/${encodeURIComponent(name)}`),

  ingest: (file: File, companyName: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("company_name", companyName);
    return apiClient.post<{ jobId: string; status: string }>("/context/ingest", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  ingestStatus: (jobId: string) =>
    apiClient.get<IngestJobStatus>(`/context/ingest/${jobId}/status`),

  listTickets: () =>
    apiClient.get<{ tickets: ContextTicket[] }>("/context/tickets"),

  createTicket: (payload: {
    companyName: string;
    fieldName:   string;
    oldText:     string;
    newText:     string;
    reason:      string;
  }) => apiClient.post<ContextTicket>("/context/tickets", payload),

  updateTicket: (ticketId: string, status: "approved" | "rejected", note?: string) =>
    apiClient.patch<ContextTicket>(`/context/tickets/${ticketId}`, { status, note }),
};

export default apiClient;
