export interface Client {
  id: string;
  name: string;
  industry: string;
  plan: "starter" | "professional" | "enterprise";
  status: "active" | "trial" | "churned" | "suspended";
  agents: number;
  callsThisMonth: number;
  avgScore: number;
  mrr: number;
  joinedDate: string;
  lastActive: string;
}

export type AdminRole = "super_admin" | "admin" | "manager" | "viewer";

export interface AdminUser {
  id: string;
  name: string;
  email: string;
  role: AdminRole;
  avatar?: string;
  status: "active" | "invited" | "disabled";
  lastLogin: string;
  createdAt: string;
  permissions: string[];
}

export interface Permission {
  id: string;
  label: string;
  description: string;
  category: "clients" | "analytics" | "team" | "billing" | "settings";
}

export const roleConfig: Record<AdminRole, { label: string; color: string; bg: string; rank: number }> = {
  super_admin: { label: "Super Admin", color: "text-accent", bg: "bg-accent/10", rank: 0 },
  admin: { label: "Admin", color: "text-primary", bg: "bg-primary/10", rank: 1 },
  manager: { label: "Manager", color: "text-warning", bg: "bg-warning/10", rank: 2 },
  viewer: { label: "Viewer", color: "text-muted-foreground", bg: "bg-muted/40", rank: 3 },
};

export const allPermissions: Permission[] = [
  { id: "clients.view", label: "View Clients", description: "View client list and details", category: "clients" },
  { id: "clients.manage", label: "Manage Clients", description: "Create, edit, suspend, or delete clients", category: "clients" },
  { id: "clients.billing", label: "Client Billing", description: "View and manage client subscriptions and billing", category: "clients" },
  { id: "analytics.view", label: "View Analytics", description: "Access platform-wide analytics and reports", category: "analytics" },
  { id: "analytics.export", label: "Export Reports", description: "Export analytics data and generate reports", category: "analytics" },
  { id: "team.view", label: "View Team", description: "View admin team members and roles", category: "team" },
  { id: "team.manage", label: "Manage Team", description: "Invite, edit roles, or remove team members", category: "team" },
  { id: "team.roles", label: "Manage Roles", description: "Create and modify role permissions", category: "team" },
  { id: "billing.view", label: "View Billing", description: "View platform billing and revenue data", category: "billing" },
  { id: "billing.manage", label: "Manage Billing", description: "Update payment methods and billing settings", category: "billing" },
  { id: "settings.general", label: "General Settings", description: "Manage platform-wide settings and configuration", category: "settings" },
  { id: "settings.security", label: "Security Settings", description: "Configure authentication, SSO, and security policies", category: "settings" },
];

export const rolePermissions: Record<AdminRole, string[]> = {
  super_admin: allPermissions.map(p => p.id),
  admin: [
    "clients.view", "clients.manage", "clients.billing",
    "analytics.view", "analytics.export",
    "team.view", "team.manage",
    "billing.view",
    "settings.general",
  ],
  manager: [
    "clients.view", "clients.manage",
    "analytics.view",
    "team.view",
  ],
  viewer: [
    "clients.view",
    "analytics.view",
  ],
};

export const currentAdmin: AdminUser = {
  id: "admin-1",
  name: "Sarah Chen",
  email: "sarah@calltone.ai",
  role: "super_admin",
  status: "active",
  lastLogin: "2026-03-01T09:30:00Z",
  createdAt: "2024-01-15",
  permissions: allPermissions.map(p => p.id),
};

export const adminUsers: AdminUser[] = [
  currentAdmin,
  { id: "admin-2", name: "Marcus Johnson", email: "marcus@calltone.ai", role: "admin", status: "active", lastLogin: "2026-03-01T08:15:00Z", createdAt: "2024-06-10", permissions: rolePermissions.admin },
  { id: "admin-3", name: "Emily Rodriguez", email: "emily@calltone.ai", role: "admin", status: "active", lastLogin: "2026-02-28T14:45:00Z", createdAt: "2024-09-22", permissions: rolePermissions.admin },
  { id: "admin-4", name: "David Kim", email: "david@calltone.ai", role: "manager", status: "active", lastLogin: "2026-02-27T11:20:00Z", createdAt: "2025-02-01", permissions: rolePermissions.manager },
  { id: "admin-5", name: "Lisa Patel", email: "lisa@calltone.ai", role: "manager", status: "active", lastLogin: "2026-03-01T07:50:00Z", createdAt: "2025-04-15", permissions: rolePermissions.manager },
  { id: "admin-6", name: "James Wilson", email: "james@calltone.ai", role: "viewer", status: "active", lastLogin: "2026-02-25T16:30:00Z", createdAt: "2025-08-20", permissions: rolePermissions.viewer },
  { id: "admin-7", name: "Nina Andersen", email: "nina@calltone.ai", role: "viewer", status: "invited", lastLogin: "", createdAt: "2026-02-28", permissions: rolePermissions.viewer },
  { id: "admin-8", name: "Tom Baker", email: "tom@calltone.ai", role: "admin", status: "disabled", lastLogin: "2025-12-10T09:00:00Z", createdAt: "2024-11-05", permissions: [] },
];

export const adminUser = {
  name: currentAdmin.name,
  role: "admin" as const,
  email: currentAdmin.email,
};

export const clients: Client[] = [
  { id: "client-1", name: "TeleCorp Solutions", industry: "Telecom", plan: "enterprise", status: "active", agents: 120, callsThisMonth: 28400, avgScore: 84, mrr: 11880, joinedDate: "2024-06-15", lastActive: "2026-03-01" },
  { id: "client-2", name: "ConnectPlus", industry: "Insurance", plan: "professional", status: "active", agents: 45, callsThisMonth: 9200, avgScore: 79, mrr: 4455, joinedDate: "2024-09-01", lastActive: "2026-03-01" },
  { id: "client-3", name: "CloudTalk Inc.", industry: "SaaS", plan: "professional", status: "active", agents: 32, callsThisMonth: 6800, avgScore: 91, mrr: 3168, joinedDate: "2025-01-10", lastActive: "2026-03-01" },
  { id: "client-4", name: "HealthLine Services", industry: "Healthcare", plan: "enterprise", status: "active", agents: 78, callsThisMonth: 18500, avgScore: 87, mrr: 7722, joinedDate: "2024-11-20", lastActive: "2026-03-01" },
  { id: "client-5", name: "RetailMax", industry: "Retail", plan: "starter", status: "active", agents: 8, callsThisMonth: 1200, avgScore: 76, mrr: 392, joinedDate: "2025-08-05", lastActive: "2026-02-28" },
  { id: "client-6", name: "BankServ Global", industry: "Finance", plan: "enterprise", status: "active", agents: 200, callsThisMonth: 52000, avgScore: 82, mrr: 19800, joinedDate: "2024-03-22", lastActive: "2026-03-01" },
  { id: "client-7", name: "TravelEase", industry: "Travel", plan: "professional", status: "trial", agents: 15, callsThisMonth: 2100, avgScore: 88, mrr: 0, joinedDate: "2026-02-15", lastActive: "2026-03-01" },
  { id: "client-8", name: "QuickSupport Co.", industry: "Tech", plan: "starter", status: "churned", agents: 5, callsThisMonth: 0, avgScore: 0, mrr: 0, joinedDate: "2025-04-12", lastActive: "2025-12-15" },
  { id: "client-9", name: "EduCall Academy", industry: "Education", plan: "professional", status: "active", agents: 22, callsThisMonth: 4300, avgScore: 90, mrr: 2178, joinedDate: "2025-05-18", lastActive: "2026-02-28" },
  { id: "client-10", name: "AutoDial Motors", industry: "Automotive", plan: "starter", status: "suspended", agents: 10, callsThisMonth: 0, avgScore: 65, mrr: 0, joinedDate: "2025-07-01", lastActive: "2026-01-20" },
  { id: "client-11", name: "GovConnect", industry: "Government", plan: "enterprise", status: "active", agents: 95, callsThisMonth: 22000, avgScore: 85, mrr: 9405, joinedDate: "2024-08-30", lastActive: "2026-03-01" },
  { id: "client-12", name: "FreshDesk Pro", industry: "SaaS", plan: "professional", status: "trial", agents: 18, callsThisMonth: 1800, avgScore: 83, mrr: 0, joinedDate: "2026-02-20", lastActive: "2026-03-01" },
];

export const platformRevenueTrend = [
  { month: "Sep", revenue: 38200 },
  { month: "Oct", revenue: 41500 },
  { month: "Nov", revenue: 44800 },
  { month: "Dec", revenue: 46200 },
  { month: "Jan", revenue: 51000 },
  { month: "Feb", revenue: 55400 },
  { month: "Mar", revenue: 59000 },
];

export const platformCallsTrend = [
  { month: "Sep", calls: 98000 },
  { month: "Oct", calls: 112000 },
  { month: "Nov", calls: 125000 },
  { month: "Dec", calls: 118000 },
  { month: "Jan", calls: 134000 },
  { month: "Feb", calls: 146300 },
  { month: "Mar", calls: 152000 },
];

export const activityLog = [
  { id: "log-1", userId: "admin-1", action: "Updated role for Marcus Johnson to Admin", timestamp: "2026-03-01T09:15:00Z" },
  { id: "log-2", userId: "admin-2", action: "Suspended client AutoDial Motors", timestamp: "2026-02-28T16:30:00Z" },
  { id: "log-3", userId: "admin-1", action: "Invited Nina Andersen as Viewer", timestamp: "2026-02-28T14:00:00Z" },
  { id: "log-4", userId: "admin-3", action: "Exported monthly analytics report", timestamp: "2026-02-27T11:45:00Z" },
  { id: "log-5", userId: "admin-1", action: "Disabled account for Tom Baker", timestamp: "2026-02-25T10:00:00Z" },
  { id: "log-6", userId: "admin-4", action: "Updated client HealthLine Services plan to Enterprise", timestamp: "2026-02-24T15:20:00Z" },
];
