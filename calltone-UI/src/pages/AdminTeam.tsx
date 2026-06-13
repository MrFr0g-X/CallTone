import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Plus,
  Mail,
  Shield,
  CheckCircle2,
  XCircle,
  X,
  Copy,
  Trash2,
  Ban,
  Building2,
  Users,
  UserCheck,
} from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { AdminTeamUser } from "@/services/api";
import { adminApi, apiErrorMessage } from "@/services/api";
import GlassCard from "@/components/GlassCard";
import BubbleToggle from "@/components/BubbleToggle";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/contexts/AuthContext";
import { canManageAdminUsers, isPlatformScope } from "@/lib/roles";

type AdminRole = "owner" | "super_admin" | "admin" | "manager" | "viewer" | "qa" | "agent";
type AssignableRole = "super_admin" | "admin" | "manager" | "viewer" | "qa" | "agent";

const roleConfig: Record<
  AdminRole,
  { label: string; color: string; bg: string; rank: number }
> = {
  owner: {
    label: "Owner",
    color: "text-emerald-300",
    bg: "bg-emerald-400/10",
    rank: 0,
  },
  super_admin: {
    label: "Super Admin",
    color: "text-accent",
    bg: "bg-accent/10",
    rank: 1,
  },
  admin: {
    label: "Admin",
    color: "text-primary",
    bg: "bg-primary/10",
    rank: 2,
  },
  manager: {
    label: "Manager",
    color: "text-warning",
    bg: "bg-warning/10",
    rank: 3,
  },
  viewer: {
    label: "Viewer",
    color: "text-muted-foreground",
    bg: "bg-muted/30",
    rank: 4,
  },
  qa: {
    label: "QA",
    color: "text-success",
    bg: "bg-success/10",
    rank: 5,
  },
  agent: {
    label: "Agent",
    color: "text-muted-foreground",
    bg: "bg-muted/30",
    rank: 6,
  },
};

const statusIcons = {
  active: { icon: CheckCircle2, color: "text-success", label: "Active" },
  invited: { icon: Mail, color: "text-warning", label: "Invited" },
  disabled: { icon: XCircle, color: "text-destructive", label: "Disabled" },
} as const;

const baseRoleOptions = ["admin", "manager", "viewer", "qa", "agent"] as const satisfies readonly AssignableRole[];
const ownerRoleOptions = ["super_admin", ...baseRoleOptions] as const satisfies readonly AssignableRole[];
// Tenant admins may assign the five company-level roles only (never owner/super_admin).
const tenantRoleOptions = ["admin", "manager", "viewer", "qa", "agent"] as const satisfies readonly AssignableRole[];

const AdminTeam = () => {
  const { toast } = useToast();
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();
  const canMutateUsers = currentUser?.capabilities?.canManageUsers ?? canManageAdminUsers(currentUser?.role);
  const isOwner = currentUser?.role === "owner";
  const platformScope = isPlatformScope(currentUser);
  const visibleRoleOptions = platformScope ? (isOwner ? ownerRoleOptions : baseRoleOptions) : tenantRoleOptions;

  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("All");
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Pick<
    AdminTeamUser,
    "id" | "name" | "email" | "status"
  > | null>(null);
  const [inviteForm, setInviteForm] = useState({
    name: "",
    email: "",
    role: (platformScope ? "viewer" : "qa") as AssignableRole,
    clientId: null as number | null,
  });

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-users"],
    queryFn: async () => {
      const response = await adminApi.getUsers();
      return response.data;
    },
  });

  const { data: clientsData } = useQuery({
    queryKey: ["admin-clients-for-invite"],
    queryFn: async () => {
      const response = await adminApi.getClients();
      return response.data;
    },
    enabled: platformScope,
  });

  const inviteMutation = useMutation({
    mutationFn: async (payload: {
      name: string;
      email: string;
      role: AssignableRole;
      clientId?: number | null;
    }) => {
      const response = await adminApi.inviteUser(payload);
      return response.data;
    },
    onSuccess: async (data) => {
      try {
        await navigator.clipboard.writeText(data.inviteUrl);
        toast({
          title: data.emailStatus === "sent" ? "Invitation email sent" : "Invitation created",
          description:
            data.emailStatus === "sent"
              ? "The activation email was sent. The fallback invite link is also copied to clipboard."
              : "Email is not confirmed as sent; fallback invite link copied to clipboard.",
        });
      } catch {
        toast({
          title: data.emailStatus === "sent" ? "Invitation email sent" : "Invitation created",
          description:
            data.emailStatus === "sent"
              ? "The activation email was sent."
              : data.inviteUrl,
        });
      }

      setShowInviteModal(false);
      setInviteForm({ name: "", email: "", role: platformScope ? "viewer" : "qa", clientId: null });
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (error: unknown) => {
      toast({
        title: "Invite failed",
        description: apiErrorMessage(error, "Failed to create invitation."),
        variant: "destructive",
      });
    },
  });

  const updateRoleMutation = useMutation({
    mutationFn: async (payload: {
      userId: number;
      role: AssignableRole;
    }) => {
      const response = await adminApi.updateUserRole(payload.userId, {
        role: payload.role,
      });
      return response.data;
    },
    onSuccess: () => {
      toast({ title: "Role updated" });
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (error: unknown) => {
      toast({
        title: "Role update failed",
        description: apiErrorMessage(error, "Failed to update role."),
        variant: "destructive",
      });
    },
  });

  const updateStatusMutation = useMutation({
    mutationFn: async (payload: {
      userId: number;
      status: "active" | "disabled";
    }) => {
      const response = await adminApi.updateUserStatus(payload.userId, {
        status: payload.status,
      });
      return response.data;
    },
    onSuccess: () => {
      toast({ title: "User status updated" });
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (error: unknown) => {
      toast({
        title: "Status update failed",
        description: apiErrorMessage(error, "Failed to update status."),
        variant: "destructive",
      });
    },
  });

  const copyInviteLinkMutation = useMutation({
    mutationFn: async (userId: number) => {
      const response = await adminApi.getInviteLink(userId);
      return response.data;
    },
    onSuccess: async (data) => {
      try {
        await navigator.clipboard.writeText(data.inviteUrl);
        toast({
          title: "Invite link copied",
          description: "The invitation link has been copied to clipboard.",
        });
      } catch {
        toast({
          title: "Invite link",
          description: data.inviteUrl,
        });
      }
    },
    onError: (error: unknown) => {
      toast({
        title: "Copy failed",
        description: apiErrorMessage(error, "Failed to get invite link."),
        variant: "destructive",
      });
    },
  });

  const deleteUserMutation = useMutation({
    mutationFn: async (userId: number) => {
      const response = await adminApi.deleteUser(userId);
      return response.data;
    },
    onSuccess: (data) => {
      toast({
        title:
          data.deletedType === "invitation" ? "Invitation deleted" : "User deleted",
        description: `${data.name} was removed successfully.`,
      });
      setDeleteTarget(null);
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (error: unknown) => {
      toast({
        title: "Delete failed",
        description: apiErrorMessage(error, "Failed to delete."),
        variant: "destructive",
      });
    },
  });

  const handleInvite = () => {
    if (!inviteForm.name || !inviteForm.email) {
      toast({
        title: "Missing fields",
        description: "Please fill in name and email.",
        variant: "destructive",
      });
      return;
    }
    if (platformScope && inviteForm.role !== "super_admin" && !inviteForm.clientId) {
      toast({
        title: "Client required",
        description: "Select the client/company this user belongs to.",
        variant: "destructive",
      });
      return;
    }

    inviteMutation.mutate({
      name: inviteForm.name,
      email: inviteForm.email,
      role: inviteForm.role,
      clientId: platformScope && inviteForm.role !== "super_admin" ? inviteForm.clientId : null,
    });
  };

  const handleRoleChange = (
    userId: number,
    role: AssignableRole
  ) => {
    updateRoleMutation.mutate({ userId, role });
  };

  const handleToggleStatus = (user: AdminTeamUser) => {
    const newStatus = user.status === "active" ? "disabled" : "active";
    updateStatusMutation.mutate({ userId: user.id, status: newStatus });
  };

  const handleCopyInviteLink = (userId: number) => {
    copyInviteLinkMutation.mutate(userId);
  };

  const confirmDeleteUser = () => {
    if (!deleteTarget) return;
    deleteUserMutation.mutate(deleteTarget.id);
  };

  const clientNameById = useMemo(() => {
    return new Map((clientsData?.clients ?? []).map((client) => [client.id, client.name]));
  }, [clientsData]);

  const clientMetaById = useMemo(() => {
    return new Map((clientsData?.clients ?? []).map((client) => [client.id, client]));
  }, [clientsData]);

  const getCompanyLabel = (user: AdminTeamUser) => {
    if (!user.clientId) return "Platform account";
    return (
      clientNameById.get(user.clientId) ||
      (user.clientId === currentUser?.clientId ? currentUser?.clientName : undefined) ||
      `Company ID ${user.clientId}`
    );
  };

  const filteredUsers = useMemo(() => {
    if (!data) return [];
    const query = search.trim().toLowerCase();

    return data.users.filter((u) => {
      if (roleFilter !== "All" && u.role !== roleFilter) return false;
      const company = !u.clientId
        ? "platform account"
        : clientNameById.get(u.clientId) ||
          (u.clientId === currentUser?.clientId ? currentUser?.clientName : "") ||
          `company id ${u.clientId}`;
      if (query && ![u.name, u.email, u.role, u.status, company].join(" ").toLowerCase().includes(query)) {
        return false;
      }
      return true;
    });
  }, [data, search, roleFilter, clientNameById, currentUser?.clientId, currentUser?.clientName]);

  const groupedUsers = useMemo(() => {
    const sortUsers = (users: AdminTeamUser[]) =>
      [...users].sort((a, b) => {
        const rankDiff = roleConfig[a.role].rank - roleConfig[b.role].rank;
        return rankDiff || a.name.localeCompare(b.name);
      });

    const groups: Array<{
      key: string;
      title: string;
      subtitle: string;
      users: AdminTeamUser[];
      accent: "platform" | "tenant";
    }> = [];

    const platformUsers = filteredUsers.filter((user) => !user.clientId);
    if (platformUsers.length) {
      groups.push({
        key: "platform",
        title: "Platform Operators",
        subtitle: "CallTone owner and internal administration accounts.",
        users: sortUsers(platformUsers),
        accent: "platform",
      });
    }

    const tenantGroups = new Map<number, AdminTeamUser[]>();
    filteredUsers
      .filter((user) => user.clientId)
      .forEach((user) => {
        const list = tenantGroups.get(user.clientId!) ?? [];
        list.push(user);
        tenantGroups.set(user.clientId!, list);
      });

    [...tenantGroups.entries()]
      .sort(([a], [b]) => {
        const nameA = clientNameById.get(a) || `Company ID ${a}`;
        const nameB = clientNameById.get(b) || `Company ID ${b}`;
        return nameA.localeCompare(nameB);
      })
      .forEach(([clientId, users]) => {
        const meta = clientMetaById.get(clientId);
        groups.push({
          key: `client-${clientId}`,
          title: meta?.name || (clientId === currentUser?.clientId ? currentUser?.clientName : undefined) || `Company ID ${clientId}`,
          subtitle: meta
            ? `${meta.industry || "Client company"} · ${meta.status} · ${meta.plan}`
            : "Tenant users scoped to this company only.",
          users: sortUsers(users),
          accent: "tenant",
        });
      });

    return groups;
  }, [filteredUsers, clientMetaById, clientNameById, currentUser?.clientId, currentUser?.clientName]);

  const activeCount =
    data?.users.filter((u) => u.status === "active").length ?? 0;
  const invitedCount = data?.users.filter((u) => u.status === "invited").length ?? 0;
  const platformAccountCount = data?.users.filter((u) => !u.clientId).length ?? 0;
  const companyCount = new Set(data?.users.filter((u) => u.clientId).map((u) => u.clientId)).size;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <span className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="text-destructive text-sm">
        Failed to load team members.
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl sm:text-4xl font-light text-foreground">
            Team <span className="font-bold gradient-text">Management</span>
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {data.users.length} team members · {activeCount} active
            {platformScope ? ` · ${platformAccountCount} platform account${platformAccountCount === 1 ? "" : "s"}` : ""}
          </p>
        </div>

        {canMutateUsers ? (
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowInviteModal(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground text-sm font-semibold shadow-lg shadow-primary/20 hover:brightness-110 transition-all"
          >
            <Plus className="w-4 h-4" />
            Invite Member
          </motion.button>
        ) : (
          <span className="rounded-xl border border-border/60 bg-muted/30 px-3 py-2 text-xs font-medium text-muted-foreground">
            Read-only access
          </span>
        )}
      </header>

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[
          { label: "Total members", value: data.users.length, icon: Users },
          { label: "Active", value: activeCount, icon: UserCheck },
          { label: "Invited", value: invitedCount, icon: Mail },
          { label: platformScope ? "Companies" : "Company scope", value: platformScope ? companyCount : 1, icon: Building2 },
        ].map((stat) => (
          <GlassCard key={stat.label} className="rounded-2xl p-4">
            <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-xl bg-accent/10">
              <stat.icon className="h-4 w-4 text-accent" />
            </div>
            <p className="text-2xl font-semibold text-foreground">{stat.value}</p>
            <p className="mt-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              {stat.label}
            </p>
          </GlassCard>
        ))}
      </section>

      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            placeholder="Search members..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-9 pl-9 pr-4 rounded-xl text-sm glass-input w-full"
          />
        </div>

        <BubbleToggle
          options={["All", ...(platformScope ? ["owner", "super_admin"] : []), "admin", "manager", "viewer", "qa", "agent"]}
          value={roleFilter}
          onChange={setRoleFilter}
          labels={{
            All: "All",
            owner: "Owner",
            super_admin: "Super Admin",
            admin: "Admin",
            manager: "Manager",
            viewer: "Viewer",
            qa: "QA",
            agent: "Agent",
          }}
        />
      </div>

      <div className="space-y-6">
        {groupedUsers.map((group, groupIndex) => (
          <section key={group.key} className="space-y-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "flex h-8 w-8 items-center justify-center rounded-xl",
                      group.accent === "platform" ? "bg-emerald-400/10 text-emerald-400" : "bg-accent/10 text-accent",
                    )}
                  >
                    {group.accent === "platform" ? <Shield className="h-4 w-4" /> : <Building2 className="h-4 w-4" />}
                  </span>
                  <h2 className="text-base font-semibold text-foreground">{group.title}</h2>
                </div>
                <p className="mt-1 text-xs text-muted-foreground">{group.subtitle}</p>
              </div>
              <span className="w-fit rounded-full border border-border/60 bg-background/50 px-3 py-1 text-[11px] font-semibold text-muted-foreground">
                {group.users.length} member{group.users.length === 1 ? "" : "s"}
              </span>
            </div>

            <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
              {group.users.map((user: AdminTeamUser, i) => {
                const role = roleConfig[user.role];
                const status = statusIcons[user.status];
                const isCurrentUser = user.id === data.currentUserId;
                const tenantAssignableRole = tenantRoleOptions.includes(user.role as AssignableRole);
                const canManageThisUser =
                  canMutateUsers &&
                  !isCurrentUser &&
                  user.role !== "owner" &&
                  (platformScope || tenantAssignableRole) &&
                  (isOwner || user.role !== "super_admin");

                return (
                  <motion.div
                    key={user.id}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: (groupIndex + i) * 0.025, duration: 0.25 }}
                  >
                    <GlassCard className="h-full rounded-2xl p-5 hover:border-accent/20 transition-colors">
                      <div className="flex h-full flex-col gap-4">
                        <div className="flex items-start gap-3">
                          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-accent/10">
                            <span className="text-xs font-bold text-accent">
                              {user.name
                                .split(" ")
                                .filter(Boolean)
                                .slice(0, 2)
                                .map((n) => n[0])
                                .join("")}
                            </span>
                          </div>

                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <h3 className="truncate text-sm font-semibold text-foreground">{user.name}</h3>
                              {isCurrentUser && (
                                <span className="rounded bg-accent/10 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                                  You
                                </span>
                              )}
                            </div>
                            <p className="truncate text-xs text-muted-foreground">{user.email}</p>
                            <p className={cn("mt-1 truncate text-[11px]", user.clientId ? "text-muted-foreground/80" : "text-accent/80")}>
                              {getCompanyLabel(user)}
                            </p>
                          </div>
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <div className={cn("flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium", role.bg)}>
                            <Shield className={cn("h-3 w-3", role.color)} />
                            <span className={role.color}>{role.label}</span>
                          </div>
                          <div className="flex items-center gap-1.5 rounded-lg bg-muted/25 px-2.5 py-1">
                            <status.icon className={cn("h-3 w-3", status.color)} />
                            <span className={cn("text-xs", status.color)}>{status.label}</span>
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-3 rounded-2xl border border-border/40 bg-background/35 p-3">
                          <div>
                            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Scope</p>
                            <p className="mt-1 truncate text-xs font-medium text-foreground">
                              {user.clientId ? "Tenant" : "Platform"}
                            </p>
                          </div>
                          <div>
                            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Last Login</p>
                            <p className="mt-1 text-xs font-medium text-foreground">
                              {user.lastLogin ? new Date(user.lastLogin).toLocaleDateString() : "Never"}
                            </p>
                          </div>
                        </div>

                        {canMutateUsers && (
                          <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-border/40 pt-3">
                            {user.status === "invited" ? (
                              <button
                                onClick={() => handleCopyInviteLink(user.id)}
                                className="inline-flex items-center gap-1.5 rounded-lg border border-border/50 px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
                              >
                                <Copy className="h-3.5 w-3.5" />
                                Invite link
                              </button>
                            ) : canManageThisUser ? (
                              <select
                                value={user.role}
                                onChange={(event) => handleRoleChange(user.id, event.target.value as AssignableRole)}
                                disabled={updateRoleMutation.isPending}
                                className="h-8 rounded-lg border border-border/50 bg-background/70 px-2 text-xs outline-none transition-colors focus:border-primary"
                              >
                                {visibleRoleOptions.map((r) => (
                                  <option key={r} value={r}>
                                    {roleConfig[r].label}
                                  </option>
                                ))}
                              </select>
                            ) : (
                              <span className="text-[11px] text-muted-foreground">Protected account</span>
                            )}

                            <div className="flex items-center gap-1">
                              {canManageThisUser && user.status !== "invited" && (
                                <button
                                  onClick={() => handleToggleStatus(user)}
                                  className="grid h-8 w-8 place-items-center rounded-lg text-muted-foreground transition-colors hover:bg-foreground/[0.04] hover:text-foreground"
                                  title={user.status === "active" ? "Disable user" : "Enable user"}
                                >
                                  <Ban className="h-3.5 w-3.5" />
                                </button>
                              )}

                              {canManageThisUser && (
                                <button
                                  onClick={() => setDeleteTarget(user)}
                                  className="grid h-8 w-8 place-items-center rounded-lg text-destructive transition-colors hover:bg-destructive/10"
                                  title={user.status === "invited" ? "Delete invitation" : "Delete user"}
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </GlassCard>
                  </motion.div>
                );
              })}
            </div>
          </section>
        ))}

        {filteredUsers.length === 0 && (
          <div className="text-center py-12 text-muted-foreground text-sm">
            No members match your search.
          </div>
        )}
      </div>

      <AnimatePresence>
        {deleteTarget && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 backdrop-blur-sm p-4"
            onClick={() => {
              if (!deleteUserMutation.isPending) setDeleteTarget(null);
            }}
          >
            <motion.div
              initial={{ opacity: 0, y: 24, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 24, scale: 0.95 }}
              transition={{ duration: 0.2 }}
              className="glass-strong rounded-2xl p-6 w-full max-w-md border border-destructive/25 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-xl bg-destructive/10 text-destructive">
                  <Trash2 className="h-5 w-5" />
                </div>
                <div className="min-w-0">
                  <h2 className="text-lg font-semibold text-foreground">
                    {deleteTarget.status === "invited" ? "Delete invitation?" : "Delete user?"}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    This will permanently remove{" "}
                    <span className="font-semibold text-foreground">{deleteTarget.name}</span>{" "}
                    <span className="break-all">({deleteTarget.email})</span>. This action is server-side and cannot be undone.
                  </p>
                </div>
              </div>

              <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  disabled={deleteUserMutation.isPending}
                  onClick={() => setDeleteTarget(null)}
                  className="rounded-xl border border-border/60 px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted/40 disabled:opacity-50"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={deleteUserMutation.isPending}
                  onClick={confirmDeleteUser}
                  className="rounded-xl bg-destructive px-4 py-2 text-sm font-semibold text-destructive-foreground transition-colors hover:brightness-110 disabled:opacity-50"
                >
                  {deleteUserMutation.isPending ? "Deleting..." : "Delete permanently"}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}

        {showInviteModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-background/60 backdrop-blur-sm p-4"
            onClick={() => setShowInviteModal(false)}
          >
            <motion.div
              initial={{ opacity: 0, y: 24, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 24, scale: 0.95 }}
              transition={{ duration: 0.3 }}
              className="glass-strong rounded-2xl p-6 sm:p-8 w-full max-w-md glow-primary"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-6">
                <h2 className="text-lg font-semibold">Invite Team Member</h2>
                <button
                  onClick={() => setShowInviteModal(false)}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                    Name
                  </label>
                  <input
                    type="text"
                    value={inviteForm.name}
                    onChange={(e) =>
                      setInviteForm({ ...inviteForm, name: e.target.value })
                    }
                    placeholder="Full name"
                    className="w-full h-10 px-4 rounded-xl glass-input text-sm"
                  />
                </div>

                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                    Email
                  </label>
                  <input
                    type="email"
                    value={inviteForm.email}
                    onChange={(e) =>
                      setInviteForm({ ...inviteForm, email: e.target.value })
                    }
                    placeholder="person@company.com"
                    className="w-full h-10 px-4 rounded-xl glass-input text-sm"
                  />
                </div>

                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                    Role
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    {visibleRoleOptions.map((r) => (
                      <button
                        key={r}
                        onClick={() =>
                          setInviteForm({
                            ...inviteForm,
                            role: r,
                            clientId: r === "super_admin" ? null : inviteForm.clientId,
                          })
                        }
                        className={cn(
                          "px-3 py-2 rounded-xl text-xs font-medium transition-all border",
                          inviteForm.role === r
                            ? cn(roleConfig[r].bg, roleConfig[r].color, "border-current")
                            : "border-border/50 text-muted-foreground hover:text-foreground"
                        )}
                      >
                        {roleConfig[r].label}
                      </button>
                    ))}
                  </div>
                </div>

                {platformScope && inviteForm.role !== "super_admin" && (
                  <div>
                    <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                      Client / Company
                    </label>
                    <select
                      value={inviteForm.clientId ?? ""}
                      onChange={(e) =>
                        setInviteForm({
                          ...inviteForm,
                          clientId: e.target.value ? Number(e.target.value) : null,
                        })
                      }
                      className="w-full h-10 px-4 rounded-xl glass-input text-sm"
                    >
                      <option value="">Select company...</option>
                      {(clientsData?.clients ?? []).map((client) => (
                        <option key={client.id} value={client.id}>
                          {client.name}
                        </option>
                      ))}
                    </select>
                    <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
                      Tenant users are isolated to this company. They cannot see or manage other companies' calls, context, or users.
                    </p>
                  </div>
                )}

                <motion.button
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={handleInvite}
                  disabled={inviteMutation.isPending}
                  className="w-full h-10 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground font-semibold text-sm shadow-lg shadow-primary/20 hover:brightness-110 transition-all mt-2 disabled:opacity-60"
                >
                  {inviteMutation.isPending ? "Sending..." : "Send Invitation"}
                </motion.button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default AdminTeam;
