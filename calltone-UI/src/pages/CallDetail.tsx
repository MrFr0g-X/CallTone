import { Link, useParams } from "react-router-dom";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import apiClient from "@/services/api";
import {
  AlertTriangle,
  ArrowLeft,
  Clock,
  FileText,
  Shield,
  ExternalLink,
  PlayCircle,
} from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlassCard from "@/components/GlassCard";
import Navbar from "@/components/Navbar";
import PageTransition from "@/components/PageTransition";
import { useAuth } from "@/contexts/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { qaApi } from "@/services/api";
import { cn } from "@/lib/utils";

const severityClass = (severity?: string | null) => {
  const s = (severity || "").toLowerCase();
  if (s === "minor") return "bg-success/10 text-success";
  if (s === "moderate") return "bg-warning/10 text-warning";
  if (s === "major") return "bg-orange-500/10 text-orange-500";
  if (s === "critical") return "bg-destructive/10 text-destructive";
  return "bg-muted/30 text-muted-foreground";
};

const scoreClass = (score: number) => {
  if (score >= 80) return "text-success";
  if (score >= 60) return "text-warning";
  return "text-destructive";
};

const CallDetailPage = () => {
  const { callId } = useParams();
  const { user } = useAuth();
  const isAdminAreaRole = user?.role === "owner" || user?.role === "admin" || user?.role === "super_admin";
  const navRole = user?.role === "agent" ? "agent" : isAdminAreaRole ? "admin" : "qa";
  const backPath = user?.role === "agent" ? "/agent/dashboard" : isAdminAreaRole ? "/admin/dashboard" : "/qa/dashboard";
  const backLabel = user?.role === "agent" ? "Back to Agent Dashboard" : isAdminAreaRole ? "Back to Admin Dashboard" : "Back to Dashboard";

  const { data: call, isLoading, isError } = useQuery({
    queryKey: ["call-detail-real", callId],
    queryFn: () => qaApi.getCallDetailReal(callId!).then((r) => r.data),
    enabled: !!callId,
  });

  const [audioBlobUrl, setAudioBlobUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!call?.audioUrl) {
      setAudioBlobUrl(null);
      return;
    }
    let objectUrl: string | null = null;
    let cancelled = false;
    const path = call.audioUrl.startsWith("/api/")
      ? call.audioUrl.slice(4)
      : call.audioUrl;
    apiClient
      .get(path, { responseType: "blob", timeout: 60000 })
      .then((resp) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(resp.data);
        setAudioBlobUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setAudioBlobUrl(null);
      });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [call?.audioUrl]);

  return (
    <PageTransition>
      <div className="min-h-screen relative">
        <AnimatedBackground />
        <Navbar userName={user?.name ?? ""} userRole={navRole} />

        {isLoading || !call ? (
          <div className="flex items-center justify-center min-h-[60vh]">
            <div className="text-center">
              <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin mx-auto mb-4" />
              <p className="text-sm text-muted-foreground">Loading call details...</p>
            </div>
          </div>
        ) : isError ? (
          <div className="flex items-center justify-center min-h-[60vh] text-destructive">
            Failed to load call details.
          </div>
        ) : (
          <main className="max-w-7xl mx-auto px-5 sm:px-8 py-8 sm:py-12 space-y-6 sm:space-y-8">
            <nav aria-label="Breadcrumb">
              <Link
                to={backPath}
                className="inline-flex items-center gap-2 text-[13px] text-muted-foreground hover:text-foreground transition-colors duration-300"
              >
                <ArrowLeft className="w-4 h-4" /> {backLabel}
              </Link>
            </nav>

            <header className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
              <div>
                <h1 className="text-2xl sm:text-3xl font-light text-foreground tracking-tight">
                  {call.filename}
                </h1>
                <p className="text-muted-foreground text-sm font-light mt-1">
                  {call.agentName} ·{" "}
                  {call.callTime ? new Date(call.callTime).toLocaleString() : "No date"} ·{" "}
                  {call.durationSeconds ? `${call.durationSeconds}s` : "Unknown duration"}
                </p>
              </div>

              <span
                className={cn(
                  "text-5xl sm:text-6xl font-extralight tracking-tight",
                  scoreClass(call.report.overallScore ?? 0)
                )}
              >
                {call.report.overallScore ?? "-"}
              </span>
            </header>

            {(call.report.severity || "").toLowerCase() === "major" ||
            (call.report.severity || "").toLowerCase() === "critical" ? (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                className="glass rounded-2xl p-4 sm:p-5 border-warning/20 bg-warning/[0.03] flex items-center gap-4"
              >
                <div className="p-2 rounded-xl bg-warning/10">
                  <AlertTriangle className="w-5 h-5 text-warning" />
                </div>
                <div>
                  <p className="text-sm font-medium text-warning">Flagged for Review</p>
                  <p className="text-xs text-muted-foreground mt-0.5 hidden sm:block">
                    This call requires extra QA attention due to severity.
                  </p>
                </div>
              </motion.div>
            ) : null}

            <GlassCard className="p-5 sm:p-6">
              <div className="flex items-center justify-between gap-3 mb-4">
                <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                  <PlayCircle className="w-4 h-4" /> Call Audio
                </h2>

                {call.driveDownloadUrl && (
                  <a
                    href={call.driveDownloadUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-2 text-xs text-accent hover:text-accent/80 transition-colors"
                  >
                    Open in Drive <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                )}
              </div>

              {audioBlobUrl ? (
                <div className="rounded-2xl overflow-hidden border border-white/[0.06] bg-black/20 p-3">
                  <audio
                    controls
                    preload="metadata"
                    className="w-full"
                    src={audioBlobUrl}
                  >
                    Your browser does not support the audio element.
                  </audio>
                </div>
              ) : call.drivePreviewUrl ? (
                <div className="rounded-2xl overflow-hidden border border-white/[0.06] bg-black/20">
                  <iframe
                    src={call.drivePreviewUrl}
                    width="100%"
                    height="120"
                    allow="autoplay"
                    className="w-full"
                    title="Call audio preview"
                  />
                </div>
              ) : call.audioUrl ? (
                <p className="text-sm text-muted-foreground">Loading audio…</p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No audio preview available for this call.
                </p>
              )}
            </GlassCard>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 sm:gap-6">
              <GlassCard className="p-5 sm:p-6 max-h-[700px] overflow-y-auto">
                <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-5 flex items-center gap-2">
                  <FileText className="w-4 h-4" /> Transcript
                </h2>

                <div className="space-y-2.5">
                  {call.transcript.speakerTurns?.map((line, i) => {
                    const isAgent =
                      String(line.speaker ?? line.role ?? "")
                        .toLowerCase()
                        .includes("agent");
                    const displayName =
                      line.role || line.speaker || `Speaker ${i}`;
                    const signals: string[] = line.signals ?? [];
                    const emotion =
                      line.emotion && line.emotion !== "EMO_UNKNOWN"
                        ? line.emotion
                        : line.audio_emotion && line.audio_emotion !== "EMO_UNKNOWN"
                        ? line.audio_emotion
                        : null;

                    return (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.02, duration: 0.2 }}
                        className={cn(
                          "p-3 rounded-2xl border",
                          isAgent
                            ? "bg-accent/[0.06] border-accent/15"
                            : "bg-primary/[0.04] border-primary/10"
                        )}
                      >
                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                          <span
                            className={cn(
                              "text-[10px] font-semibold px-2 py-0.5 rounded-full",
                              isAgent
                                ? "bg-accent/15 text-accent"
                                : "bg-primary/15 text-primary"
                            )}
                          >
                            {displayName}
                          </span>
                          <span className="text-[10px] text-muted-foreground">
                            {line.start.toFixed(1)}s – {line.end.toFixed(1)}s
                          </span>
                          {emotion && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full font-medium bg-warning/10 text-warning">
                              {emotion}
                            </span>
                          )}
                          {signals.map((sig: string, si: number) => (
                            <span
                              key={si}
                              className={cn(
                                "text-[9px] px-1.5 py-0.5 rounded-full font-medium",
                                sig === "FRUSTRATED" || sig === "ESCALATION"
                                  ? "bg-destructive/10 text-destructive"
                                  : sig === "APOLOGETIC" || sig === "SATISFIED"
                                  ? "bg-success/10 text-success"
                                  : "bg-muted/30 text-muted-foreground"
                              )}
                            >
                              {sig}
                            </span>
                          ))}
                          {line.profile && !emotion && signals.length === 0 && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded-full font-medium bg-accent/10 text-accent">
                              {line.profile}
                            </span>
                          )}
                        </div>
                        <p className="text-[13px] text-foreground/75 leading-relaxed">
                          {line.text}
                        </p>
                      </motion.div>
                    );
                  })}
                </div>
              </GlassCard>

              <div className="space-y-5 sm:space-y-6">
                <GlassCard className="p-5 sm:p-6">
                  <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-5 flex items-center gap-2">
                    <Shield className="w-4 h-4" /> QA Scores
                  </h2>

                  <div className="flex items-center justify-between mb-4">
                    <span className="text-sm text-muted-foreground">Grade</span>
                    <span className="text-lg font-semibold text-foreground">
                      {call.report.grade ?? "-"}
                    </span>
                  </div>

                  <div className="flex items-center justify-between mb-6">
                    <span className="text-sm text-muted-foreground">Severity</span>
                    <span
                      className={cn(
                        "text-[11px] px-3 py-1.5 rounded-full font-semibold capitalize",
                        severityClass(call.report.severity)
                      )}
                    >
                      {call.report.severity ?? "N/A"}
                    </span>
                  </div>

                  <div className="space-y-3">
                    {Object.entries(call.report.dimensionScores || {}).map(([key, value]) => (
                      <div
                        key={key}
                        className="p-3.5 rounded-xl bg-foreground/[0.03] border border-foreground/[0.04]"
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                            {key.replace(/_/g, " ")}
                          </p>
                          <span className={cn("text-sm font-semibold", scoreClass(value))}>
                            {value}
                          </span>
                        </div>

                        <p className="text-xs text-foreground/70 leading-relaxed">
                          {call.report.dimensionReports?.[key] || "No report available."}
                        </p>

                        <p className="text-[10px] text-muted-foreground mt-2">
                          Confidence:{" "}
                          {call.report.confidenceScores?.[key] != null
                            ? `${Math.round(call.report.confidenceScores[key] * 100)}%`
                            : "N/A"}
                        </p>
                      </div>
                    ))}
                  </div>
                </GlassCard>

                <GlassCard className="p-5 sm:p-6">
                  <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-5">
                    AI Quality Report
                  </h2>

                  <div className="space-y-4 text-sm text-foreground/75">
                    <div>
                      <p className="font-semibold text-foreground mb-1">Summary</p>
                      <p>{call.report.reportJson?.summary || "No summary available."}</p>
                    </div>

                    <div>
                      <p className="font-semibold text-foreground mb-1">Strengths</p>
                      <ul className="list-disc pl-5 space-y-1">
                        {(call.report.reportJson?.strengths || []).map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>

                    <div>
                      <p className="font-semibold text-foreground mb-1">Weaknesses</p>
                      <ul className="list-disc pl-5 space-y-1">
                        {(call.report.reportJson?.weaknesses || []).map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>

                    <div>
                      <p className="font-semibold text-foreground mb-1">Recommended Actions</p>
                      <ul className="list-disc pl-5 space-y-1">
                        {(call.report.reportJson?.recommended_actions || []).map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </GlassCard>

                <GlassCard className="p-5 sm:p-6">
                  <h2 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-5">
                    Evidence
                  </h2>

                  <div className="space-y-3">
                    {(call.report.evidence || []).map((item, i) => (
                      <div
                        key={i}
                        className="p-3.5 rounded-xl bg-foreground/[0.03] border border-foreground/[0.04]"
                      >
                        <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider mb-1">
                          {item.dimension}
                        </p>
                        <p className="text-xs italic text-foreground/75 mb-1">"{item.quote}"</p>
                        <p className="text-[11px] text-muted-foreground">
                          Speaker {item.speaker} · {item.reason}
                        </p>
                      </div>
                    ))}
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
