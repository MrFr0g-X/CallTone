import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Phone,
  BarChart3,
  AlertTriangle,
  Search,
  ChevronRight,
  Clock,
} from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlassCard from "@/components/GlassCard";
import Navbar from "@/components/Navbar";
import PageTransition from "@/components/PageTransition";
import BubbleToggle from "@/components/BubbleToggle";
import { useAuth } from "@/contexts/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { qaApi } from "@/services/api";
import type { QaCallItem } from "@/services/api";
import { cn } from "@/lib/utils";
import AnimatedNumber from "@/components/AnimatedNumber";

const timeRanges = ["Weekly", "Monthly", "Quarterly", "Yearly"];

const QADashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [selectedRange, setSelectedRange] = useState("Monthly");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<"time" | "rating">("time");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["qa-calls-list"],
    queryFn: async () => {
      const response = await qaApi.getCallsList();
      return response.data;
    },
  });

  const calls = data?.calls ?? [];

  const filteredCalls = useMemo(() => {
    let filtered = calls.filter((call) => {
      const q = search.toLowerCase();
      return (
        call.filename.toLowerCase().includes(q) ||
        call.agentName.toLowerCase().includes(q) ||
        (call.severity || "").toLowerCase().includes(q)
      );
    });

    if (sortBy === "rating") {
      filtered = [...filtered].sort(
        (a, b) => (b.overallScore ?? 0) - (a.overallScore ?? 0)
      );
    } else {
      filtered = [...filtered].sort((a, b) => {
        const da = a.callTime ? new Date(a.callTime).getTime() : 0;
        const db = b.callTime ? new Date(b.callTime).getTime() : 0;
        return db - da;
      });
    }

    return filtered;
  }, [calls, search, sortBy]);

  const totalCalls = calls.length;
  const avgScore =
    calls.length > 0
      ? Math.round(
          calls.reduce((sum, c) => sum + (c.overallScore ?? 0), 0) / calls.length
        )
      : 0;
  const flaggedCalls = calls.filter(
    (c) =>
      (c.overallScore ?? 100) < 70 ||
      (c.severity ?? "").toLowerCase() === "major" ||
      (c.severity ?? "").toLowerCase() === "critical"
  ).length;

  if (isLoading) {
    return (
      <PageTransition>
        <div className="min-h-screen relative">
          <AnimatedBackground />
          <Navbar userName={user?.name ?? ""} userRole="qa" />
          <div className="flex items-center justify-center min-h-[70vh]">
            <span className="w-8 h-8 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
          </div>
        </div>
      </PageTransition>
    );
  }

  if (isError) {
    return (
      <PageTransition>
        <div className="min-h-screen relative">
          <AnimatedBackground />
          <Navbar userName={user?.name ?? ""} userRole="qa" />
          <div className="flex items-center justify-center min-h-[70vh] text-destructive">
            Failed to load QA calls.
          </div>
        </div>
      </PageTransition>
    );
  }

  return (
    <PageTransition>
      <div className="min-h-screen relative">
        <AnimatedBackground />
        <Navbar userName={user?.name ?? ""} userRole="qa" />

        <main className="max-w-7xl mx-auto px-5 sm:px-8 py-8 sm:py-12 space-y-8">
          <header>
            <h1 className="text-3xl sm:text-4xl font-light text-foreground tracking-tight">
              QA <span className="font-bold gradient-text">Dashboard</span>
            </h1>
            <p className="text-muted-foreground mt-2 text-sm font-light">
              Review calls, transcripts, and quality reports
            </p>
          </header>

          <section className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
            {[
              {
                icon: Phone,
                value: totalCalls,
                label: "Total Calls",
                iconColor: "text-accent",
              },
              {
                icon: BarChart3,
                value: avgScore,
                label: "Average Score",
                iconColor: "text-success",
              },
              {
                icon: AlertTriangle,
                value: flaggedCalls,
                label: "Flagged Calls",
                iconColor: "text-warning",
              },
            ].map((item) => (
              <GlassCard key={item.label} className="p-5 sm:p-6">
                <div className="flex items-center gap-4">
                  <div className="p-2.5 rounded-xl bg-white/[0.04]">
                    <item.icon className={cn("w-5 h-5", item.iconColor)} />
                  </div>
                  <div>
                    <p className="text-3xl font-extralight text-foreground tracking-tight">
                      <AnimatedNumber value={item.value} duration={1200} />
                    </p>
                    <p className="text-[11px] text-muted-foreground mt-1 font-medium uppercase tracking-wider">
                      {item.label}
                    </p>
                  </div>
                </div>
              </GlassCard>
            ))}
          </section>

          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 justify-between">
            <BubbleToggle
              options={timeRanges}
              value={selectedRange}
              onChange={setSelectedRange}
            />

            <div className="flex flex-col sm:flex-row gap-2">
              <div className="relative">
                <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/60" />
                <input
                  type="text"
                  placeholder="Search calls..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="h-9 pl-9 pr-3 rounded-xl glass-input text-xs sm:text-[13px] w-full sm:w-56"
                />
              </div>

              <BubbleToggle
                options={["By Time", "By Rating"]}
                value={sortBy === "time" ? "By Time" : "By Rating"}
                onChange={(v) => setSortBy(v === "By Time" ? "time" : "rating")}
              />
            </div>
          </div>

          <section className="space-y-3">
            {filteredCalls.length === 0 ? (
              <GlassCard className="p-10 text-center text-muted-foreground text-sm">
                No calls found.
              </GlassCard>
            ) : (
              filteredCalls.map((call: QaCallItem, i) => (
                <motion.div
                  key={call.callId}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.04, duration: 0.25 }}
                  onClick={() => navigate(`/qa/call/${call.callId}`)}
                  className="cursor-pointer"
                >
                  <GlassCard className="rounded-2xl p-5 hover:border-accent/20 transition-colors">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 flex-wrap">
                          <h3 className="text-sm font-semibold text-foreground truncate">
                            {call.filename}
                          </h3>

                          <span
                            className={cn(
                              "text-[10px] px-2 py-0.5 rounded-full font-medium",
                              (call.severity || "").toLowerCase() === "moderate" &&
                                "bg-warning/10 text-warning",
                              (call.severity || "").toLowerCase() === "major" &&
                                "bg-orange-500/10 text-orange-500",
                              (call.severity || "").toLowerCase() === "critical" &&
                                "bg-destructive/10 text-destructive",
                              (call.severity || "").toLowerCase() === "minor" &&
                                "bg-success/10 text-success"
                            )}
                          >
                            {call.severity || "N/A"}
                          </span>
                        </div>

                        <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground flex-wrap">
                          <span>{call.agentName}</span>
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {call.callTime
                              ? new Date(call.callTime).toLocaleString()
                              : "No date"}
                          </span>
                          <span>{call.status}</span>
                        </div>
                      </div>

                      <div className="flex items-center gap-4">
                        <span
                          className={cn(
                            "text-2xl font-extralight",
                            (call.overallScore ?? 0) >= 80
                              ? "text-success"
                              : (call.overallScore ?? 0) >= 60
                              ? "text-warning"
                              : "text-destructive"
                          )}
                        >
                          {call.overallScore ?? "-"}
                        </span>
                        <ChevronRight className="w-4 h-4 text-muted-foreground/40" />
                      </div>
                    </div>
                  </GlassCard>
                </motion.div>
              ))
            )}
          </section>
        </main>
      </div>
    </PageTransition>
  );
};

export default QADashboard;