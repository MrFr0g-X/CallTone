import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import {
  Building2, Search, ChevronRight, CheckCircle2, Clock, XCircle,
  AlertTriangle, TrendingUp, TrendingDown, Users, Phone, DollarSign
} from "lucide-react";
import { clients } from "@/data/adminMockData";
import GlassCard from "@/components/GlassCard";
import AnimatedNumber from "@/components/AnimatedNumber";
import BubbleToggle from "@/components/BubbleToggle";
import { cn } from "@/lib/utils";

const statusConfig = {
  active: { label: "Active", icon: CheckCircle2, color: "text-success", bg: "bg-success/10" },
  trial: { label: "Trial", icon: Clock, color: "text-warning", bg: "bg-warning/10" },
  churned: { label: "Churned", icon: XCircle, color: "text-destructive", bg: "bg-destructive/10" },
  suspended: { label: "Suspended", icon: AlertTriangle, color: "text-muted-foreground", bg: "bg-muted/40" },
};

const planColors = {
  starter: "text-muted-foreground",
  professional: "text-accent",
  enterprise: "text-primary",
};

const AdminClients = () => {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");

  const activeClients = clients.filter(c => c.status === "active").length;
  const trialClients = clients.filter(c => c.status === "trial").length;
  const totalAgents = clients.reduce((a, c) => a + c.agents, 0);
  const totalCalls = clients.reduce((a, c) => a + c.callsThisMonth, 0);
  const totalMRR = clients.reduce((a, c) => a + c.mrr, 0);

  const filteredClients = useMemo(() => {
    return clients
      .filter(c => {
        if (statusFilter !== "All" && c.status !== statusFilter.toLowerCase()) return false;
        if (search && !c.name.toLowerCase().includes(search.toLowerCase()) && !c.industry.toLowerCase().includes(search.toLowerCase())) return false;
        return true;
      })
      .sort((a, b) => b.mrr - a.mrr);
  }, [search, statusFilter]);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl sm:text-4xl font-light text-foreground">
          Client <span className="font-bold gradient-text">Management</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-1">{clients.length} total clients · {activeClients} active</p>
      </header>

      {/* Summary */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { icon: Building2, label: "ACTIVE CLIENTS", value: activeClients, suffix: trialClients > 0 ? ` (+${trialClients} trial)` : "" },
          { icon: Users, label: "TOTAL AGENTS", value: totalAgents },
          { icon: Phone, label: "CALLS THIS MONTH", value: totalCalls },
          { icon: DollarSign, label: "TOTAL MRR", value: totalMRR, prefix: "$" },
        ].map(kpi => (
          <GlassCard key={kpi.label} className="rounded-2xl p-5">
            <div className="w-8 h-8 rounded-xl bg-accent/10 flex items-center justify-center mb-2">
              <kpi.icon className="w-4 h-4 text-accent" />
            </div>
            <p className="text-xl font-bold">{kpi.prefix || ""}<AnimatedNumber value={kpi.value} /></p>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider mt-1">{kpi.label}{kpi.suffix || ""}</p>
          </GlassCard>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            placeholder="Search clients..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-9 pl-9 pr-4 rounded-xl text-sm glass-input w-full"
          />
        </div>
        <BubbleToggle
          options={["All", "Active", "Trial", "Churned"]}
          value={statusFilter}
          onChange={setStatusFilter}
        />
      </div>

      {/* Client List */}
      <div className="space-y-3">
        {filteredClients.map((client, i) => {
          const status = statusConfig[client.status];
          return (
            <motion.div
              key={client.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03, duration: 0.3 }}
              whileHover={{ y: -2, scale: 1.005 }}
              whileTap={{ scale: 0.995 }}
              className="cursor-pointer"
            >
              <GlassCard className="rounded-2xl p-5 hover:border-accent/20 transition-colors">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-4 flex-1 min-w-0">
                    <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
                      <Building2 className="w-5 h-5 text-primary" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold truncate">{client.name}</h3>
                        <span className={cn("text-[11px] font-medium capitalize", planColors[client.plan])}>{client.plan}</span>
                      </div>
                      <p className="text-xs text-muted-foreground">{client.industry} · {client.agents} agents · {client.callsThisMonth.toLocaleString()} calls/mo</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-5 sm:gap-8">
                    {client.avgScore > 0 && (
                      <div className="text-right">
                        <p className={cn("text-lg font-bold", client.avgScore >= 85 ? "text-success" : client.avgScore >= 70 ? "text-warning" : "text-destructive")}>{client.avgScore}</p>
                        <p className="text-[10px] text-muted-foreground uppercase">Avg Score</p>
                      </div>
                    )}
                    <div className="text-right">
                      <p className="text-lg font-bold">${client.mrr.toLocaleString()}</p>
                      <p className="text-[10px] text-muted-foreground uppercase">MRR</p>
                    </div>
                    <div className={cn("flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium", status.bg)}>
                      <status.icon className={cn("w-3 h-3", status.color)} />
                      <span className={status.color}>{status.label}</span>
                    </div>
                    <ChevronRight className="w-4 h-4 text-muted-foreground hidden sm:block" />
                  </div>
                </div>
              </GlassCard>
            </motion.div>
          );
        })}
        {filteredClients.length === 0 && (
          <div className="text-center py-12 text-muted-foreground text-sm">No clients match your search.</div>
        )}
      </div>
    </div>
  );
};

export default AdminClients;
