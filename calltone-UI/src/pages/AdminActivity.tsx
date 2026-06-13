import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { Clock, UserPlus, Shield, ChevronLeft, ChevronRight, Search } from "lucide-react";
import GlassCard from "@/components/GlassCard";
import BubbleToggle from "@/components/BubbleToggle";
import { useQuery } from "@tanstack/react-query";
import { adminApi } from "@/services/api";

type Category = "All" | "Logins" | "Invitations";
const PAGE_SIZE = 12;
const WINDOWS: Record<string, number | null> = { "7d": 7, "30d": 30, All: null };

const AdminActivity = () => {
  const { data } = useQuery({
    queryKey: ["admin-users-activity"],
    queryFn: () => adminApi.getUsers().then((r) => r.data),
  });

  const [category, setCategory] = useState<Category>("All");
  const [windowKey, setWindowKey] = useState<string>("7d");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);

  const users = data?.users ?? [];

  const activities = useMemo(() => {
    const windowDays = WINDOWS[windowKey];
    const cutoff = windowDays != null ? Date.now() - windowDays * 86_400_000 : null;
    const q = search.trim().toLowerCase();

    return users
      .filter((u) => u.lastLogin || u.status === "invited")
      .map((u) => {
        const isInvite = u.status === "invited";
        return {
          id: `user-${u.id}`,
          name: u.name,
          kind: isInvite ? ("Invitations" as const) : ("Logins" as const),
          action: isInvite
            ? `was invited as ${u.role.replace("_", " ")}`
            : `logged in (${u.role.replace("_", " ")})`,
          timestamp: u.lastLogin || "",
          icon: isInvite ? UserPlus : Shield,
        };
      })
      .filter((a) => category === "All" || a.kind === category)
      .filter((a) => {
        if (!cutoff || !a.timestamp) return windowKey === "All" ? true : !a.timestamp ? false : true;
        return new Date(a.timestamp).getTime() >= cutoff;
      })
      .filter((a) => !q || a.name.toLowerCase().includes(q))
      .sort((a, b) => {
        if (!a.timestamp) return 1;
        if (!b.timestamp) return -1;
        return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
      });
  }, [users, category, windowKey, search]);

  const pageCount = Math.max(1, Math.ceil(activities.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const visible = activities.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);

  // Reset to first page whenever a filter changes.
  const onFilter = <T,>(setter: (v: T) => void) => (v: T) => {
    setter(v);
    setPage(0);
  };

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl sm:text-4xl font-light text-foreground">
          Activity <span className="font-bold gradient-text">Log</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Sign-ins and invitations across your company · {activities.length} event{activities.length === 1 ? "" : "s"}
        </p>
      </header>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap gap-3">
          <BubbleToggle
            options={["All", "Logins", "Invitations"]}
            value={category}
            onChange={onFilter<string>((v) => setCategory(v as Category))}
          />
          <BubbleToggle
            options={["7d", "30d", "All"]}
            value={windowKey}
            onChange={onFilter<string>(setWindowKey)}
            labels={{ "7d": "Last 7 days", "30d": "Last 30 days", All: "All time" }}
          />
        </div>
        <div className="relative w-full lg:w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            placeholder="Search by name..."
            value={search}
            onChange={(e) => onFilter<string>(setSearch)(e.target.value)}
            className="h-9 pl-9 pr-4 rounded-xl text-sm glass-input w-full"
          />
        </div>
      </div>

      <div className="space-y-3">
        {visible.length === 0 ? (
          <GlassCard className="p-10 text-center text-muted-foreground text-sm">
            No activity matches these filters.
          </GlassCard>
        ) : (
          visible.map((log, i) => (
            <motion.div
              key={log.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03, duration: 0.25 }}
            >
              <GlassCard className="rounded-2xl p-5">
                <div className="flex items-start gap-4">
                  <div className="w-9 h-9 rounded-xl bg-accent/10 flex items-center justify-center shrink-0 mt-0.5">
                    <log.icon className="w-4 h-4 text-accent" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm">
                      <span className="font-semibold">{log.name}</span>{" "}
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

      {pageCount > 1 && (
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={safePage === 0}
            className="inline-flex items-center gap-1 px-3 py-2 rounded-xl border border-border/50 text-xs text-muted-foreground hover:text-foreground hover:border-accent/50 disabled:opacity-40"
          >
            <ChevronLeft className="w-3.5 h-3.5" /> Prev
          </button>
          <span className="text-xs text-muted-foreground">
            Page {safePage + 1} of {pageCount}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={safePage >= pageCount - 1}
            className="inline-flex items-center gap-1 px-3 py-2 rounded-xl border border-border/50 text-xs text-muted-foreground hover:text-foreground hover:border-accent/50 disabled:opacity-40"
          >
            Next <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </div>
  );
};

export default AdminActivity;
