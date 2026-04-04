import { motion } from "framer-motion";
import { Clock, User, Phone, UserPlus, Shield, Info } from "lucide-react";
import GlassCard from "@/components/GlassCard";
import { useQuery } from "@tanstack/react-query";
import { adminApi } from "@/services/api";
import { cn } from "@/lib/utils";

const AdminActivity = () => {
  const { data } = useQuery({
    queryKey: ["admin-users-activity"],
    queryFn: () => adminApi.getUsers().then((r) => r.data),
  });

  const users = data?.users ?? [];

  // Build activity entries from real user data (logins, invites, status)
  const activities = users
    .filter((u) => u.lastLogin || u.status === "invited")
    .map((u) => ({
      id: `user-${u.id}`,
      name: u.name,
      action:
        u.status === "invited"
          ? `was invited as ${u.role.replace("_", " ")}`
          : `logged in (${u.role.replace("_", " ")})`,
      timestamp: u.lastLogin || "",
      icon: u.status === "invited" ? UserPlus : Shield,
    }))
    .sort((a, b) => {
      if (!a.timestamp) return 1;
      if (!b.timestamp) return -1;
      return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
    });

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl sm:text-4xl font-light text-foreground">
          Activity <span className="font-bold gradient-text">Log</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-1">Recent platform activity</p>
      </header>

      <div className="space-y-3">
        {activities.length === 0 ? (
          <GlassCard className="p-10 text-center text-muted-foreground text-sm">
            No activity recorded yet.
          </GlassCard>
        ) : (
          activities.map((log, i) => (
            <motion.div
              key={log.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04, duration: 0.3 }}
            >
              <GlassCard className="rounded-2xl p-5">
                <div className="flex items-start gap-4">
                  <div className="w-9 h-9 rounded-xl bg-accent/10 flex items-center justify-center shrink-0 mt-0.5">
                    <log.icon className="w-4 h-4 text-accent" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm">
                      <span className="font-semibold">{log.name}</span>
                      {" "}
                      <span className="text-muted-foreground">{log.action}</span>
                    </p>
                    {log.timestamp && (
                      <div className="flex items-center gap-1.5 mt-1">
                        <Clock className="w-3 h-3 text-muted-foreground" />
                        <span className="text-xs text-muted-foreground">
                          {new Date(log.timestamp).toLocaleString()}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </GlassCard>
            </motion.div>
          ))
        )}
      </div>
    </div>
  );
};

export default AdminActivity;
