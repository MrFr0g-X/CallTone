import { useState } from "react";
import { motion } from "framer-motion";
import { Shield, CheckCircle2, XCircle, Info, Lock, ChevronDown, ChevronRight } from "lucide-react";
import { allPermissions, rolePermissions, roleConfig, type AdminRole } from "@/data/adminMockData";
import { useAuth } from "@/contexts/AuthContext";
import GlassCard from "@/components/GlassCard";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

const categories = [
  { id: "clients", label: "Clients", description: "Client management and billing access" },
  { id: "analytics", label: "Analytics", description: "Platform analytics and reporting" },
  { id: "team", label: "Team", description: "Team member and role management" },
  { id: "billing", label: "Billing", description: "Platform billing and payments" },
  { id: "settings", label: "Settings", description: "Platform configuration and security" },
] as const;

const roles: AdminRole[] = ["super_admin", "admin", "manager", "viewer"];

const AdminPermissions = () => {
  const { toast } = useToast();
  const [selectedRole, setSelectedRole] = useState<AdminRole>("admin");
  const [expandedCategories, setExpandedCategories] = useState<string[]>(categories.map(c => c.id));
  const [localPermissions, setLocalPermissions] = useState(rolePermissions);

  const { user } = useAuth();
  const myRole = (user?.role ?? "viewer") as AdminRole;
  const canEditRoles = myRole === "super_admin" || myRole === "admin";
  const isSuperAdmin = selectedRole === "super_admin";

  const toggleCategory = (id: string) => {
    setExpandedCategories(prev =>
      prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]
    );
  };

  const togglePermission = (permId: string) => {
    if (!canEditRoles || isSuperAdmin) return;
    setLocalPermissions(prev => ({
      ...prev,
      [selectedRole]: prev[selectedRole].includes(permId)
        ? prev[selectedRole].filter(p => p !== permId)
        : [...prev[selectedRole], permId]
    }));
  };

  const handleSave = () => {
    toast({ title: "Permissions updated", description: `${roleConfig[selectedRole].label} permissions have been saved.` });
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <header>
        <h1 className="text-3xl sm:text-4xl font-light text-foreground">
          Roles & <span className="font-bold gradient-text">Access Control</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-1">Configure what each role can access across the platform</p>
      </header>

      {/* Role Hierarchy */}
      <GlassCard className="rounded-2xl p-6">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-4">Role Hierarchy</h2>
        <div className="flex flex-wrap items-center gap-3">
          {roles.map((role, i) => {
            const config = roleConfig[role];
            const isSelected = selectedRole === role;
            return (
              <div key={role} className="flex items-center gap-3">
                <motion.button
                  whileHover={{ scale: 1.03 }}
                  whileTap={{ scale: 0.97 }}
                  onClick={() => setSelectedRole(role)}
                  className={cn(
                    "flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all border",
                    isSelected
                      ? cn(config.bg, config.color, "border-current shadow-lg")
                      : "border-border/50 text-muted-foreground hover:text-foreground hover:border-border"
                  )}
                >
                  <Shield className="w-4 h-4" />
                  {config.label}
                  <span className={cn(
                    "text-[10px] px-1.5 py-0.5 rounded",
                    isSelected ? "bg-foreground/10" : "bg-muted"
                  )}>
                    {localPermissions[role].length}/{allPermissions.length}
                  </span>
                </motion.button>
                {i < roles.length - 1 && (
                  <ChevronRight className="w-4 h-4 text-muted-foreground/40 hidden sm:block" />
                )}
              </div>
            );
          })}
        </div>
        <p className="text-xs text-muted-foreground mt-3 flex items-center gap-1.5">
          <Info className="w-3 h-3" />
          Higher-ranked roles inherit all permissions. Super Admin has full access and cannot be modified.
        </p>
      </GlassCard>

      {/* Permissions Grid */}
      <div className="space-y-4">
        {categories.map((cat) => {
          const catPermissions = allPermissions.filter(p => p.category === cat.id);
          const isExpanded = expandedCategories.includes(cat.id);
          const grantedCount = catPermissions.filter(p => localPermissions[selectedRole].includes(p.id)).length;

          return (
            <GlassCard key={cat.id} className="rounded-2xl overflow-hidden">
              <button
                onClick={() => toggleCategory(cat.id)}
                className="w-full flex items-center justify-between p-5 text-left hover:bg-foreground/[0.02] transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    {isExpanded ? <ChevronDown className="w-4 h-4 text-muted-foreground" /> : <ChevronRight className="w-4 h-4 text-muted-foreground" />}
                    <h3 className="text-sm font-semibold">{cat.label}</h3>
                  </div>
                  <span className="text-[11px] text-muted-foreground">{cat.description}</span>
                </div>
                <span className={cn(
                  "text-xs font-medium px-2 py-0.5 rounded",
                  grantedCount === catPermissions.length ? "text-success bg-success/10" :
                  grantedCount > 0 ? "text-warning bg-warning/10" :
                  "text-muted-foreground bg-muted/40"
                )}>
                  {grantedCount}/{catPermissions.length}
                </span>
              </button>

              {isExpanded && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  className="border-t border-border/50"
                >
                  {catPermissions.map((perm) => {
                    const isGranted = localPermissions[selectedRole].includes(perm.id);
                    return (
                      <div
                        key={perm.id}
                        className={cn(
                          "flex items-center justify-between px-5 py-3.5 border-b border-border/30 last:border-0 transition-colors",
                          canEditRoles && !isSuperAdmin ? "cursor-pointer hover:bg-foreground/[0.02]" : ""
                        )}
                        onClick={() => togglePermission(perm.id)}
                      >
                        <div className="flex items-center gap-3">
                          {isSuperAdmin ? (
                            <Lock className="w-4 h-4 text-accent" />
                          ) : isGranted ? (
                            <CheckCircle2 className="w-4 h-4 text-success" />
                          ) : (
                            <XCircle className="w-4 h-4 text-muted-foreground/40" />
                          )}
                          <div>
                            <p className="text-sm font-medium">{perm.label}</p>
                            <p className="text-xs text-muted-foreground">{perm.description}</p>
                          </div>
                        </div>
                        {!isSuperAdmin && canEditRoles && (
                          <div className={cn(
                            "w-8 h-5 rounded-full transition-colors flex items-center px-0.5",
                            isGranted ? "bg-success justify-end" : "bg-muted-foreground/20 justify-start"
                          )}>
                            <div className="w-4 h-4 rounded-full bg-white shadow-sm" />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </motion.div>
              )}
            </GlassCard>
          );
        })}
      </div>

      {/* Save */}
      {canEditRoles && !isSuperAdmin && (
        <div className="flex justify-end">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleSave}
            className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground text-sm font-semibold shadow-lg shadow-primary/20 hover:brightness-110 transition-all"
          >
            Save Changes
          </motion.button>
        </div>
      )}
    </div>
  );
};

export default AdminPermissions;
