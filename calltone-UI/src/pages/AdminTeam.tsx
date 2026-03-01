import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Users, Search, Plus, MoreHorizontal, Mail, Shield, Clock,
  CheckCircle2, XCircle, AlertTriangle, ChevronDown, X
} from "lucide-react";
import { adminUsers, roleConfig, currentAdmin, type AdminRole, type AdminUser } from "@/data/adminMockData";
import GlassCard from "@/components/GlassCard";
import BubbleToggle from "@/components/BubbleToggle";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

const statusIcons = {
  active: { icon: CheckCircle2, color: "text-success", label: "Active" },
  invited: { icon: Mail, color: "text-warning", label: "Invited" },
  disabled: { icon: XCircle, color: "text-destructive", label: "Disabled" },
};

const AdminTeam = () => {
  const { toast } = useToast();
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("All");
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [editingUser, setEditingUser] = useState<AdminUser | null>(null);
  const [inviteForm, setInviteForm] = useState({ name: "", email: "", role: "viewer" as AdminRole });

  const filteredUsers = useMemo(() => {
    return adminUsers.filter(u => {
      if (roleFilter !== "All" && u.role !== roleFilter) return false;
      if (search && !u.name.toLowerCase().includes(search.toLowerCase()) && !u.email.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [search, roleFilter]);

  const canManageUser = (targetUser: AdminUser) => {
    const currentRank = roleConfig[currentAdmin.role].rank;
    const targetRank = roleConfig[targetUser.role].rank;
    return currentRank < targetRank && currentAdmin.id !== targetUser.id;
  };

  const handleInvite = () => {
    if (!inviteForm.name || !inviteForm.email) {
      toast({ title: "Missing fields", description: "Please fill in name and email.", variant: "destructive" });
      return;
    }
    toast({ title: "Invitation sent", description: `${inviteForm.name} has been invited as ${roleConfig[inviteForm.role].label}.` });
    setShowInviteModal(false);
    setInviteForm({ name: "", email: "", role: "viewer" });
  };

  const handleRoleChange = (user: AdminUser, newRole: AdminRole) => {
    toast({ title: "Role updated", description: `${user.name}'s role changed to ${roleConfig[newRole].label}.` });
    setEditingUser(null);
  };

  const handleToggleStatus = (user: AdminUser) => {
    const action = user.status === "disabled" ? "enabled" : "disabled";
    toast({ title: `Account ${action}`, description: `${user.name}'s account has been ${action}.` });
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl sm:text-4xl font-light text-foreground">
            Team <span className="font-bold gradient-text">Management</span>
          </h1>
          <p className="text-sm text-muted-foreground mt-1">{adminUsers.length} team members · {adminUsers.filter(u => u.status === "active").length} active</p>
        </div>
        {currentAdmin.permissions.includes("team.manage") && (
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowInviteModal(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground text-sm font-semibold shadow-lg shadow-primary/20 hover:brightness-110 transition-all"
          >
            <Plus className="w-4 h-4" />
            Invite Member
          </motion.button>
        )}
      </header>

      {/* Filters */}
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
          options={["All", "super_admin", "admin", "manager", "viewer"]}
          value={roleFilter}
          onChange={setRoleFilter}
          labels={{ All: "All", super_admin: "Super Admin", admin: "Admin", manager: "Manager", viewer: "Viewer" }}
        />
      </div>

      {/* Team List */}
      <div className="space-y-3">
        {filteredUsers.map((user, i) => {
          const role = roleConfig[user.role];
          const status = statusIcons[user.status];
          const canManage = canManageUser(user);
          const isCurrentUser = user.id === currentAdmin.id;

          return (
            <motion.div
              key={user.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03, duration: 0.3 }}
            >
              <GlassCard className="rounded-2xl p-5 hover:border-accent/20 transition-colors">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-4 flex-1 min-w-0">
                    <div className="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center shrink-0">
                      <span className="text-xs font-bold text-accent">
                        {user.name.split(" ").map(n => n[0]).join("")}
                      </span>
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold truncate">{user.name}</h3>
                        {isCurrentUser && (
                          <span className="text-[10px] font-medium text-accent bg-accent/10 px-1.5 py-0.5 rounded">You</span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">{user.email}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 sm:gap-6">
                    {/* Role badge */}
                    <div className="relative">
                      {editingUser?.id === user.id ? (
                        <div className="flex items-center gap-2">
                          {(["admin", "manager", "viewer"] as AdminRole[]).map(r => (
                            <button
                              key={r}
                              onClick={() => handleRoleChange(user, r)}
                              className={cn(
                                "px-2.5 py-1 rounded-lg text-xs font-medium transition-all",
                                roleConfig[r].bg, roleConfig[r].color,
                                "hover:brightness-110"
                              )}
                            >
                              {roleConfig[r].label}
                            </button>
                          ))}
                          <button onClick={() => setEditingUser(null)} className="p-1 text-muted-foreground hover:text-foreground">
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      ) : (
                        <div className={cn("flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium", role.bg)}>
                          <Shield className={cn("w-3 h-3", role.color)} />
                          <span className={role.color}>{role.label}</span>
                        </div>
                      )}
                    </div>

                    {/* Status */}
                    <div className="flex items-center gap-1.5">
                      <status.icon className={cn("w-3 h-3", status.color)} />
                      <span className={cn("text-xs", status.color)}>{status.label}</span>
                    </div>

                    {/* Last login */}
                    <div className="hidden lg:block text-right min-w-[100px]">
                      <p className="text-[10px] text-muted-foreground uppercase">Last Login</p>
                      <p className="text-xs text-foreground">
                        {user.lastLogin ? new Date(user.lastLogin).toLocaleDateString() : "Never"}
                      </p>
                    </div>

                    {/* Actions */}
                    {canManage && currentAdmin.permissions.includes("team.manage") && (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => setEditingUser(editingUser?.id === user.id ? null : user)}
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-foreground/[0.04] transition-colors"
                          title="Change role"
                        >
                          <Shield className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => handleToggleStatus(user)}
                          className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-foreground/[0.04] transition-colors"
                          title={user.status === "disabled" ? "Enable account" : "Disable account"}
                        >
                          {user.status === "disabled" ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </GlassCard>
            </motion.div>
          );
        })}

        {filteredUsers.length === 0 && (
          <div className="text-center py-12 text-muted-foreground text-sm">No members match your search.</div>
        )}
      </div>

      {/* Invite Modal */}
      <AnimatePresence>
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
                <button onClick={() => setShowInviteModal(false)} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground">
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">Name</label>
                  <input
                    type="text"
                    value={inviteForm.name}
                    onChange={(e) => setInviteForm({ ...inviteForm, name: e.target.value })}
                    placeholder="Full name"
                    className="w-full h-10 px-4 rounded-xl glass-input text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">Email</label>
                  <input
                    type="email"
                    value={inviteForm.email}
                    onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
                    placeholder="email@calltone.ai"
                    className="w-full h-10 px-4 rounded-xl glass-input text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">Role</label>
                  <div className="grid grid-cols-3 gap-2">
                    {(["admin", "manager", "viewer"] as AdminRole[]).map(r => (
                      <button
                        key={r}
                        onClick={() => setInviteForm({ ...inviteForm, role: r })}
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

                <motion.button
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={handleInvite}
                  className="w-full h-10 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground font-semibold text-sm shadow-lg shadow-primary/20 hover:brightness-110 transition-all mt-2"
                >
                  Send Invitation
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
