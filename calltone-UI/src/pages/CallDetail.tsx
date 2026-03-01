import { useState, useRef } from "react";
import { useTheme } from "@/components/ThemeProvider";
import { useParams, Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Play, Pause, SkipBack, SkipForward, AlertTriangle, ArrowLeft, Shield } from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlassCard from "@/components/GlassCard";
import Navbar from "@/components/Navbar";
import PageTransition from "@/components/PageTransition";
import { useAuth } from "@/contexts/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { qaApi } from "@/services/api";
import type { CallDetail } from "@/data/mockData";
import { cn } from "@/lib/utils";

const emotionColors: Record<string, string> = {
  neutral: "bg-muted/50 text-muted-foreground",
  anger: "bg-destructive/10 text-destructive",
  joy: "bg-success/10 text-success",
  frustration: "bg-warning/10 text-warning",
  satisfaction: "bg-accent/10 text-accent",
};

const CallDetailPage = () => {
  const { callId } = useParams();
  const { user } = useAuth();
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const progressRef = useRef<HTMLDivElement>(null);

  const { data: call, isLoading } = useQuery({
    queryKey: ["call-detail", callId],
    queryFn: () => qaApi.getCallDetail(callId!).then(r => r.data),
    enabled: !!callId,
  });

  const handleProgressClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!progressRef.current) return;
    const rect = progressRef.current.getBoundingClientRect();
    const pct = ((e.clientX - rect.left) / rect.width) * 100;
    setProgress(Math.max(0, Math.min(100, pct)));
  };

  const renderScoreRadial = (score: number, max: number, label: string, confidence: number) => {
    const pct = (score / max) * 100;
    const circumference = 2 * Math.PI * 40;
    const offset = circumference - (pct / 100) * circumference;
    const color = score >= 4 ? "hsl(160 84% 39%)" : score >= 3 ? "hsl(38 92% 50%)" : "hsl(0 72% 56%)";

    return (
      <div className="flex flex-col items-center">
        <div className="relative w-24 h-24 sm:w-28 sm:h-28">
          <svg className="w-full h-full -rotate-90" viewBox="0 0 88 88">
            <circle cx="44" cy="44" r="40" fill="none" stroke="hsl(var(--border))" strokeWidth="4" />
            <motion.circle
              cx="44" cy="44" r="40" fill="none" stroke={color} strokeWidth="4"
              strokeLinecap="round"
              strokeDasharray={circumference}
              initial={{ strokeDashoffset: circumference }}
              animate={{ strokeDashoffset: offset }}
              transition={{ duration: 1.2, ease: [0.25, 0.46, 0.45, 0.94] }}
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-2xl sm:text-3xl font-extralight text-foreground">{score}</span>
          </div>
        </div>
        <p className="text-xs font-medium text-foreground mt-3">{label}</p>
        <p className="text-[10px] text-muted-foreground mt-0.5">{confidence}% confidence</p>
      </div>
    );
  };

  return (
    <PageTransition>
      <div className="min-h-screen relative">
        <AnimatedBackground />
        <Navbar userName={user?.name ?? ""} userRole="qa" />

        {isLoading || !call ? (
          <div className="flex items-center justify-center min-h-[60vh]">
            <div className="text-center">
              <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
              <p className="text-sm text-muted-foreground">Loading call details...</p>
            </div>
          </div>
        ) : (
        <main className="max-w-7xl mx-auto px-5 sm:px-8 py-8 sm:py-12 space-y-6 sm:space-y-8">
          {/* Breadcrumb */}
          <nav aria-label="Breadcrumb">
            <Link to="/qa/dashboard" className="inline-flex items-center gap-2 text-[13px] text-muted-foreground hover:text-foreground transition-colors duration-300">
              <ArrowLeft className="w-4 h-4" /> Back to Dashboard
            </Link>
          </nav>

          {/* Header */}
          <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
            <div>
              <h1 className="text-2xl sm:text-3xl font-light text-foreground tracking-tight">Call {callId}</h1>
              <p className="text-muted-foreground text-sm font-light mt-1">{call.agentName} → {call.customerName} · {call.date} · {call.duration}</p>
            </div>
            <span className={cn(
              "text-5xl sm:text-6xl font-extralight tracking-tight",
              call.overallScore >= 80 ? "text-success" : call.overallScore >= 60 ? "text-warning" : "text-destructive"
            )}>
              {call.overallScore}
            </span>
          </header>

          {/* Flagged Banner */}
          {call.flagForReview && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ ease: [0.25, 0.46, 0.45, 0.94] }}
              className="glass rounded-2xl p-4 sm:p-5 border-warning/20 bg-warning/[0.03] flex items-center gap-4"
              role="alert"
            >
              <div className="p-2 rounded-xl bg-warning/10">
                <AlertTriangle className="w-5 h-5 text-warning" />
              </div>
              <div>
                <p className="text-sm font-medium text-warning">Flagged for Review</p>
                <p className="text-xs text-muted-foreground mt-0.5 hidden sm:block">This call requires supervisor attention due to low quality scores.</p>
              </div>
            </motion.div>
          )}

          {/* Audio Player */}
          <GlassCard glow="primary" className="p-5 sm:p-6">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5">
                <button className="p-2 rounded-xl hover:bg-foreground/[0.06] transition-all duration-300 text-muted-foreground hover:text-foreground" aria-label="Skip back">
                  <SkipBack className="w-4 h-4" />
                </button>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  transition={{ type: "spring", stiffness: 400, damping: 25 }}
                  onClick={() => setIsPlaying(!isPlaying)}
                  className="p-3 rounded-2xl bg-accent text-accent-foreground shadow-lg shadow-accent/20"
                  aria-label={isPlaying ? "Pause" : "Play"}
                >
                  {isPlaying ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5 ml-0.5" />}
                </motion.button>
                <button className="p-2 rounded-xl hover:bg-foreground/[0.06] transition-all duration-300 text-muted-foreground hover:text-foreground" aria-label="Skip forward">
                  <SkipForward className="w-4 h-4" />
                </button>
              </div>
              <div className="flex-1">
                <div
                  ref={progressRef}
                  onClick={handleProgressClick}
                  className="h-1.5 rounded-full bg-foreground/[0.08] cursor-pointer relative group"
                >
                  <div
                    className="h-full rounded-full bg-accent transition-all duration-100"
                    style={{ width: `${progress}%` }}
                  />
                  <div
                    className="absolute top-1/2 -translate-y-1/2 w-3.5 h-3.5 rounded-full bg-foreground shadow-lg opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                    style={{ left: `${progress}%`, transform: `translate(-50%, -50%)` }}
                  />
                </div>
              </div>
              <span className="text-[11px] text-muted-foreground font-mono min-w-[50px] tabular-nums">
                {Math.floor((progress / 100) * 8)}:{String(Math.floor(((progress / 100) * 47) % 60)).padStart(2, "0")} / {call.duration}
              </span>
            </div>
          </GlassCard>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 sm:gap-6">
            {/* Transcript */}
            <GlassCard className="p-5 sm:p-6 max-h-[500px] sm:max-h-[600px] overflow-y-auto">
              <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-5">Transcript</h2>
              <div className="space-y-2.5">
                {call.transcript.map((line, i) => (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, x: line.speaker === "agent" ? -8 : 8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.025, duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
                    className={cn(
                      "flex gap-2.5",
                      line.speaker === "customer" && "flex-row-reverse text-right"
                    )}
                  >
                    <div className={cn(
                      "flex-1 p-3 rounded-2xl",
                      line.speaker === "agent" ? "bg-primary/[0.06] border border-primary/10" : "bg-secondary/[0.06] border border-secondary/10"
                    )}>
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className="text-[10px] font-semibold text-foreground/80 capitalize">{line.speaker}</span>
                        <span className="text-[10px] text-muted-foreground">{line.timestamp}</span>
                        <span className={cn("text-[9px] px-1.5 py-0.5 rounded-full font-medium", emotionColors[line.emotion])}>
                          {line.emotion}
                        </span>
                      </div>
                      <p className="text-[13px] text-foreground/75 leading-relaxed">{line.text}</p>
                    </div>
                  </motion.div>
                ))}
              </div>
            </GlassCard>

            <div className="space-y-5 sm:space-y-6">
              {/* Scoring Panel */}
              <GlassCard glow="accent" className="p-5 sm:p-6">
                <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-6 flex items-center gap-2">
                  <Shield className="w-4 h-4" /> QA Scoring — 7 Dimensions
                </h2>
                {/* Radial scores: Politeness, Empathy, Factual Accuracy */}
                <div className="grid grid-cols-3 gap-3 sm:gap-5 mb-6">
                  {renderScoreRadial(call.scores.politeness.score, 5, "Politeness", call.scores.politeness.confidence)}
                  {renderScoreRadial(call.scores.empathy.score, 5, "Empathy", call.scores.empathy.confidence)}
                  {renderScoreRadial(call.scores.factualAccuracy.score, 5, "Factual Accuracy", call.scores.factualAccuracy.confidence)}
                </div>
                {/* Binary badges: Script Compliance, Conflict, Resolution */}
                <div className="grid grid-cols-3 gap-3 mb-6">
                   <div className="text-center p-3.5 rounded-2xl bg-foreground/[0.03] border border-foreground/[0.04]">
                     <span className={cn(
                       "text-[11px] px-2.5 py-1 rounded-full font-medium",
                       call.scores.scriptCompliance.compliant ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive"
                     )}>
                       {call.scores.scriptCompliance.compliant ? "Compliant" : "Non-Compliant"}
                     </span>
                     <p className="text-[10px] text-muted-foreground mt-2">Script · {call.scores.scriptCompliance.confidence}%</p>
                   </div>
                   <div className="text-center p-3.5 rounded-2xl bg-foreground/[0.03] border border-foreground/[0.04]">
                     <span className={cn(
                       "text-[11px] px-2.5 py-1 rounded-full font-medium",
                       call.scores.conflict.detected ? "bg-destructive/10 text-destructive" : "bg-success/10 text-success"
                     )}>
                       {call.scores.conflict.detected ? "Conflict" : "No Conflict"}
                     </span>
                     <p className="text-[10px] text-muted-foreground mt-2">Detection · {call.scores.conflict.confidence}%</p>
                   </div>
                   <div className="text-center p-3.5 rounded-2xl bg-foreground/[0.03] border border-foreground/[0.04]">
                    <span className={cn(
                      "text-[11px] px-2.5 py-1 rounded-full font-medium",
                      call.scores.resolution.resolved ? "bg-success/10 text-success" : "bg-destructive/10 text-destructive"
                    )}>
                      {call.scores.resolution.resolved ? "Resolved" : "Unresolved"}
                    </span>
                    <p className="text-[10px] text-muted-foreground mt-2">Resolution · {call.scores.resolution.confidence}%</p>
                  </div>
                </div>
                {/* Severity badge */}
                <div className="mb-6 p-3.5 rounded-2xl bg-foreground/[0.03] border border-foreground/[0.04] flex items-center justify-between">
                  <div>
                    <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1">Overall Severity</p>
                    <p className="text-[10px] text-muted-foreground">{call.scores.severity.confidence}% confidence</p>
                  </div>
                  <span className={cn(
                    "text-[11px] px-3 py-1.5 rounded-full font-semibold capitalize",
                    call.scores.severity.level === "minor" && "bg-success/10 text-success",
                    call.scores.severity.level === "moderate" && "bg-warning/10 text-warning",
                    call.scores.severity.level === "major" && "bg-orange-500/10 text-orange-500",
                    call.scores.severity.level === "critical" && "bg-destructive/10 text-destructive",
                  )}>
                    {call.scores.severity.level}
                  </span>
                </div>
                {/* Evidence Quotes */}
                <div className="space-y-2">
                  {Object.entries(call.scores).map(([key, val]) => (
                    <div key={key} className="p-3.5 rounded-xl bg-foreground/[0.02] border border-foreground/[0.04]">
                      <p className="text-[10px] font-medium text-muted-foreground capitalize mb-1.5 uppercase tracking-wider">{key.replace(/([A-Z])/g, " $1").trim()}</p>
                      <p className="text-xs italic text-foreground/60 leading-relaxed">"{val.evidence}"</p>
                    </div>
                  ))}
                </div>
              </GlassCard>

              {/* AI Report */}
              <GlassCard className="p-5 sm:p-6">
                <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-5">AI Quality Report</h2>
                <div className="prose prose-invert prose-sm max-w-none text-foreground/70 text-[13px] leading-relaxed [&_h2]:text-foreground [&_h2]:text-sm [&_h2]:font-semibold [&_h2]:mt-5 [&_h2]:mb-2 [&_h3]:text-foreground [&_h3]:text-[13px] [&_h3]:font-semibold [&_h3]:mt-4 [&_h3]:mb-1.5 [&_strong]:text-foreground/90 [&_ol]:list-decimal [&_ol]:pl-4 [&_li]:mb-1">
                  {call.aiReport.split("\n").map((line, i) => {
                    if (line.startsWith("## ")) return <h2 key={i}>{line.replace("## ", "")}</h2>;
                    if (line.startsWith("### ")) return <h3 key={i}>{line.replace("### ", "")}</h3>;
                    if (line.startsWith("**") && line.endsWith("**")) return <p key={i}><strong>{line.replace(/\*\*/g, "")}</strong></p>;
                    if (line.match(/^\d+\. /)) return <p key={i} className="ml-4">{line}</p>;
                    if (line.trim() === "") return <br key={i} />;
                    return <p key={i}>{line}</p>;
                  })}
                </div>
              </GlassCard>
            </div>
          </div>
        </main>
        )}
      </div>
    </PageTransition>
  );
};

export default CallDetailPage;
