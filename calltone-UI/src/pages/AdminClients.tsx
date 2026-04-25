import { useMemo, useState } from "react";
import { Building2, Phone, Search, Users } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import AnimatedNumber from "@/components/AnimatedNumber";
import GlassCard from "@/components/GlassCard";
import { adminApi } from "@/services/api";
import { cn } from "@/lib/utils";

const AdminClients = () => {
  const [search, setSearch] = useState("");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-clients"],
    queryFn: () => adminApi.getClients().then((response) => response.data),
  });

  const filteredClients = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!data || !query) return data?.clients ?? [];
    return data.clients.filter((client) =>
      [client.name, client.industry, client.status, client.plan]
        .join(" ")
        .toLowerCase()
        .includes(query),
    );
  }, [data, search]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <span className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
      </div>
    );
  }

  if (isError || !data) {
    return <div className="text-destructive text-sm">Failed to load clients.</div>;
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl sm:text-4xl font-light text-foreground">
            Client <span className="font-bold gradient-text">Directory</span>
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Read-only tenant and staffing overview from the backend database.
          </p>
        </div>
        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search clients..."
            className="h-10 w-full rounded-xl glass-input pl-9 pr-4 text-sm"
          />
        </div>
      </header>

      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Total Clients", value: data.summary.totalClients, icon: Building2 },
          { label: "Active Clients", value: data.summary.activeClients, icon: Building2 },
          { label: "Total Agents", value: data.summary.totalAgents, icon: Users },
          { label: "Total Calls", value: data.summary.totalCalls, icon: Phone },
        ].map((item) => (
          <GlassCard key={item.label} className="rounded-2xl p-5">
            <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-xl bg-accent/10">
              <item.icon className="h-4 w-4 text-accent" />
            </div>
            <p className="text-2xl font-bold">
              <AnimatedNumber value={item.value} />
            </p>
            <p className="mt-1 text-[11px] uppercase tracking-wider text-muted-foreground">{item.label}</p>
          </GlassCard>
        ))}
      </section>

      <section className="space-y-3">
        {filteredClients.length === 0 ? (
          <GlassCard className="p-10 text-center text-sm text-muted-foreground">
            No clients match your search.
          </GlassCard>
        ) : (
          filteredClients.map((client) => (
            <GlassCard key={client.id} className="rounded-2xl p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-sm font-semibold text-foreground">{client.name}</h2>
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize",
                        client.status === "active" && "bg-success/10 text-success",
                        client.status === "trial" && "bg-warning/10 text-warning",
                        client.status === "suspended" && "bg-destructive/10 text-destructive",
                        client.status === "churned" && "bg-muted/40 text-muted-foreground",
                      )}
                    >
                      {client.status}
                    </span>
                    <span className="rounded-full bg-muted/40 px-2 py-0.5 text-[10px] font-semibold capitalize text-muted-foreground">
                      {client.plan}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">{client.industry}</p>
                </div>

                <div className="grid grid-cols-3 gap-3 text-right sm:min-w-[320px]">
                  <div>
                    <p className="text-sm font-semibold">{client.agents}</p>
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Agents</p>
                  </div>
                  <div>
                    <p className="text-sm font-semibold">{client.qaCount}</p>
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">QA</p>
                  </div>
                  <div>
                    <p className="text-sm font-semibold">{client.callsThisMonth}</p>
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Calls</p>
                  </div>
                </div>
              </div>
            </GlassCard>
          ))
        )}
      </section>
    </div>
  );
};

export default AdminClients;
