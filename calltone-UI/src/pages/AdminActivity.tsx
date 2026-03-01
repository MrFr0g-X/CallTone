import { motion } from "framer-motion";
import { Clock, User } from "lucide-react";
import { activityLog, adminUsers } from "@/data/adminMockData";
import GlassCard from "@/components/GlassCard";
import { cn } from "@/lib/utils";

const AdminActivity = () => {
  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl sm:text-4xl font-light text-foreground">
          Activity <span className="font-bold gradient-text">Log</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-1">Recent admin actions across the platform</p>
      </header>

      <div className="space-y-3">
        {activityLog.map((log, i) => {
          const user = adminUsers.find(u => u.id === log.userId);
          return (
            <motion.div
              key={log.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04, duration: 0.3 }}
            >
              <GlassCard className="rounded-2xl p-5">
                <div className="flex items-start gap-4">
                  <div className="w-9 h-9 rounded-xl bg-accent/10 flex items-center justify-center shrink-0 mt-0.5">
                    <User className="w-4 h-4 text-accent" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm">
                      <span className="font-semibold">{user?.name || "Unknown"}</span>
                      {" "}
                      <span className="text-muted-foreground">{log.action}</span>
                    </p>
                    <div className="flex items-center gap-1.5 mt-1">
                      <Clock className="w-3 h-3 text-muted-foreground" />
                      <span className="text-xs text-muted-foreground">
                        {new Date(log.timestamp).toLocaleString()}
                      </span>
                    </div>
                  </div>
                </div>
              </GlassCard>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
};

export default AdminActivity;
