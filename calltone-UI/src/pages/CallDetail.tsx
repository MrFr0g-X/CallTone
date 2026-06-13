import { Link, useParams } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import apiClient from "@/services/api";
import {
  AlertTriangle,
  ArrowLeft,
  Download,
  FileText,
  Pause,
  Shield,
  PlayCircle,
} from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlassCard from "@/components/GlassCard";
import Navbar from "@/components/Navbar";
import PageTransition from "@/components/PageTransition";
import ScoreGauge from "@/components/ScoreGauge";
import { useAuth } from "@/contexts/AuthContext";
import { useQuery } from "@tanstack/react-query";
import { qaApi } from "@/services/api";
import { cn, cleanCallTitle } from "@/lib/utils";

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

const buildAudioSrc = (audioUrl?: string | null) => {
  if (!audioUrl) return null;
  if (/^https?:\/\//i.test(audioUrl)) return audioUrl;

  const base = String(apiClient.defaults.baseURL || "");
  if (audioUrl.startsWith("/api/")) {
    const origin = base ? new URL(base).origin : window.location.origin;
    return `${origin}${audioUrl}`;
  }

  return `${base.replace(/\/$/, "")}/${audioUrl.replace(/^\//, "")}`;
};

const formatAudioTime = (seconds: number) => {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0:00";
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  const remainder = String(total % 60).padStart(2, "0");
  return `${minutes}:${remainder}`;
};

type CallAudioPlayerProps = {
  audioSrc: string | null;
  drivePreviewUrl?: string | null;
  driveDownloadUrl?: string | null;
};

const CallAudioPlayer = ({
  audioSrc,
  drivePreviewUrl,
  driveDownloadUrl,
}: CallAudioPlayerProps) => {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const progressRef = useRef<HTMLDivElement | null>(null);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    setDuration(0);
    setCurrentTime(0);
    setIsPlaying(false);
    setHasError(false);
  }, [audioSrc]);

  const progress = duration > 0 ? Math.min(100, Math.max(0, (currentTime / duration) * 100)) : 0;

  const seekToPointer = (clientX: number) => {
    const audio = audioRef.current;
    const track = progressRef.current;
    if (!audio || !track || !duration) return;

    const bounds = track.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (clientX - bounds.left) / bounds.width));
    audio.currentTime = ratio * duration;
  };

  const togglePlayback = async () => {
    const audio = audioRef.current;
    if (!audio) return;

    if (audio.paused) {
      try {
        await audio.play();
      } catch {
        setHasError(true);
      }
    } else {
      audio.pause();
    }
  };

  if (!audioSrc && drivePreviewUrl) {
    return (
      <iframe
        src={drivePreviewUrl}
        width="100%"
        height="86"
        allow="autoplay"
        className="w-full rounded-2xl border border-border/70"
        title="Call audio preview"
      />
    );
  }

  if (!audioSrc) {
    return <p className="text-sm text-muted-foreground">No audio preview available for this call.</p>;
  }

  return (
    <div className="rounded-2xl border border-border/70 bg-card/80 px-4 py-3 shadow-sm">
      <audio
        ref={audioRef}
        preload="metadata"
        src={audioSrc}
        onLoadedMetadata={(event) => {
          setDuration(event.currentTarget.duration || 0);
        }}
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onEnded={() => setIsPlaying(false)}
        onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
        onError={() => {
          setHasError(true);
        }}
      />

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={togglePlayback}
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-accent text-accent-foreground shadow-sm transition-transform hover:scale-105 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background"
          aria-label={isPlaying ? "Pause call audio" : "Play call audio"}
        >
          {isPlaying ? <Pause className="h-4 w-4" /> : <PlayCircle className="h-4 w-4" />}
        </button>

        <span className="w-[76px] shrink-0 text-xs tabular-nums text-muted-foreground">
          {formatAudioTime(currentTime)} / {formatAudioTime(duration)}
        </span>

        <div
          ref={progressRef}
          className="relative h-2 flex-1 cursor-pointer rounded-full bg-muted"
          role="slider"
          aria-label="Call audio progress"
          aria-valuemin={0}
          aria-valuemax={Math.max(0, Math.floor(duration))}
          aria-valuenow={Math.floor(currentTime)}
          tabIndex={0}
          onClick={(event) => seekToPointer(event.clientX)}
          onKeyDown={(event) => {
            const audio = audioRef.current;
            if (!audio || !duration) return;
            if (event.key === "ArrowLeft") audio.currentTime = Math.max(0, audio.currentTime - 5);
            if (event.key === "ArrowRight") audio.currentTime = Math.min(duration, audio.currentTime + 5);
          }}
        >
          <div
            className="absolute left-0 top-0 h-full rounded-full bg-accent transition-[width]"
            style={{ width: `${progress}%` }}
          />
        </div>

        {(driveDownloadUrl || audioSrc) && (
          <a
            href={driveDownloadUrl || audioSrc}
            target="_blank"
            rel="noreferrer"
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-border bg-background/70 text-muted-foreground transition-colors hover:text-accent focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background"
            aria-label="Open call audio"
            title="Open audio"
          >
            <Download className="h-4 w-4" />
          </a>
        )}
      </div>

      {hasError && (
        <p className="mt-3 text-xs text-destructive">
          Audio stream could not be loaded. Refresh the page to renew the media link.
        </p>
      )}
    </div>
  );
};

type CallTab = "overview" | "transcript" | "scores" | "report" | "evidence";

const CallDetailPage = () => {
  const { callId } = useParams();
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState<CallTab>("overview");
  const isAdminAreaRole = user?.role === "owner" || user?.role === "admin" || user?.role === "super_admin";
  const navRole = user?.role === "agent" ? "agent" : isAdminAreaRole ? "admin" : "qa";
  const backPath = user?.role === "agent" ? "/agent/dashboard" : isAdminAreaRole ? "/admin/dashboard" : "/qa/dashboard";
  const backLabel = user?.role === "agent" ? "Back to Agent Dashboard" : isAdminAreaRole ? "Back to Admin Dashboard" : "Back to Dashboard";

  const { data: call, isLoading, isError } = useQuery({
    queryKey: ["call-detail-real", callId],
    queryFn: () => qaApi.getCallDetailReal(callId!).then((r) => r.data),
    enabled: !!callId,
  });

  const audioSrc = buildAudioSrc(call?.audioUrl);

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

            <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl sm:text-3xl font-light text-foreground tracking-tight">
                  {cleanCallTitle(call.filename)}
                </h1>
                <p className="text-muted-foreground text-sm font-light mt-1">
                  {call.agentName} ·{" "}
                  {call.callTime ? new Date(call.callTime).toLocaleString() : "No date"} ·{" "}
                  {call.durationSeconds ? `${call.durationSeconds}s` : "Unknown duration"}
                </p>
                <p className="text-[11px] text-muted-foreground/70 mt-1 font-mono">
                  {call.filename}
                </p>
              </div>

              <ScoreGauge
                score={call.report.overallScore ?? 0}
                grade={call.report.grade}
                size={200}
              />
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

            {/* B4: section tabs so AI report / evidence are not buried at the bottom */}
            <div className="flex flex-wrap gap-1 border-b border-border/40">
              {([
                ["overview", "Overview"],
                ["transcript", "Transcript"],
                ["scores", "QA Scores"],
                ["report", "AI Report"],
                ["evidence", "Evidence"],
              ] as const).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setActiveTab(key)}
                  className={cn(
                    "px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors",
                    activeTab === key
                      ? "border-accent text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  )}
                >
                  {label}
                </button>
              ))}
            </div>

            {activeTab === "overview" && (
              <GlassCard className="p-5 sm:p-6">
                <h2 className="mb-4 text-sm font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-2">
                  <PlayCircle className="w-4 h-4" /> Call Audio
                </h2>

                <CallAudioPlayer
                  audioSrc={audioSrc}
                  drivePreviewUrl={call.drivePreviewUrl}
                  driveDownloadUrl={call.driveDownloadUrl}
                />

                <div className="mt-5 grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {Object.entries(call.report.dimensionScores || {}).map(([key, value]) => (
                    <div key={key} className="p-3 rounded-xl bg-foreground/[0.03] border border-foreground/[0.04]">
                      <p className="text-[10px] font-medium text-muted-foreground uppercase tracking-wider mb-1">
                        {key.replace(/_/g, " ")}
                      </p>
                      <span className={cn("text-lg font-semibold", scoreClass(value))}>{value}</span>
                    </div>
                  ))}
                </div>
              </GlassCard>
            )}

            {activeTab === "transcript" && (
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
            )}

            {activeTab === "scores" && (
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
            )}

            {activeTab === "report" && (
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
            )}

            {activeTab === "evidence" && (
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
            )}
          </main>
        )}
      </div>
    </PageTransition>
  );
};

export default CallDetailPage;
