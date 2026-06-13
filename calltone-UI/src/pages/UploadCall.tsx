import { useState, useCallback, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Upload, FileAudio, CheckCircle, AlertCircle, Loader2, X } from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlassCard from "@/components/GlassCard";
import Navbar from "@/components/Navbar";
import PageTransition from "@/components/PageTransition";
import { useAuth } from "@/contexts/AuthContext";
import { adminApi, agentsApi, callsApi, isAudioFile, MAX_UPLOAD_SIZE_BYTES } from "@/services/api";
import type { AdminClientItem, AsrEngine, UploadAgent } from "@/services/api";
import { cn } from "@/lib/utils";

type UploadStage = "idle" | "uploading" | "processing" | "completed" | "error";

const STEP_LABELS: Record<string, string> = {
  queued: "Queued for GPU processing...",
  uploaded: "File received",
  denoising: "Enhancing audio quality...",
  transcribing: "Transcribing & diarizing...",
  role_identification: "Identifying speaker roles...",
  emotion_detection: "Detecting emotions...",
  scoring: "Running QA analysis (7 criteria)...",
  report_generation: "Generating report...",
  completed: "Analysis complete",
  error: "Processing failed",
};

const ACCEPTED_TYPES = [
  "audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp3",
  "audio/flac", "audio/ogg", "audio/webm",
];

const UploadCall = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [stage, setStage] = useState<UploadStage>("idle");
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [callId, setCallId] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [queuePosition, setQueuePosition] = useState<number | null>(null);
  const [etaSeconds, setEtaSeconds] = useState<number | null>(null);
  const [asrEngine, setAsrEngine] = useState<AsrEngine>("fasterwhisper");
  const [clients, setClients] = useState<AdminClientItem[]>([]);
  const [selectedClientId, setSelectedClientId] = useState<number | null>(null);
  const [companyName, setCompanyName] = useState("");
  const [agents, setAgents] = useState<UploadAgent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [companyLoadError, setCompanyLoadError] = useState("");
  const [agentLoadError, setAgentLoadError] = useState("");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const platformScope = user?.roleScope === "platform";
  const canUseTestingControls = platformScope;

  const reset = () => {
    setStage("idle");
    setFile(null);
    setCallId(null);
    setCurrentStep("");
    setErrorMsg("");
    setQueuePosition(null);
    setEtaSeconds(null);
    if (pollRef.current) clearInterval(pollRef.current);
  };

  const handleFile = useCallback((f: File) => {
    if (!isAudioFile(f)) {
      setErrorMsg("Unsupported file type. Upload WAV, MP3, FLAC, OGG, or WebM audio.");
      setStage("error");
      return;
    }
    if (f.size > MAX_UPLOAD_SIZE_BYTES) {
      setErrorMsg("File too large (max 200 MB)");
      setStage("error");
      return;
    }
    setFile(f);
    setStage("idle");
    setErrorMsg("");
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const f = e.dataTransfer.files[0];
      if (f) handleFile(f);
    },
    [handleFile]
  );

  const onFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0];
      if (f) handleFile(f);
    },
    [handleFile]
  );

  const pollStatus = useCallback(
    (id: string) => {
      pollRef.current = setInterval(async () => {
        try {
          const res = await callsApi.getStatus(id);
          const d = res.data;
          setCurrentStep(d.currentStep);
          setQueuePosition(d.queuePosition ?? null);
          setEtaSeconds(d.etaSeconds ?? null);

          if (d.status === "COMPLETED") {
            setStage("completed");
            if (pollRef.current) clearInterval(pollRef.current);
          } else if (d.status === "FAILED") {
            setStage("error");
            setErrorMsg(d.error || "Pipeline processing failed");
            if (pollRef.current) clearInterval(pollRef.current);
          }
        } catch {
          // ignore transient errors during polling
        }
      }, 5000);
    },
    []
  );

  const handleUpload = async () => {
    if (!file) return;
    setStage("uploading");
    setErrorMsg("");

    try {
      const res = await callsApi.upload(
        file,
        selectedAgentId,
        canUseTestingControls ? asrEngine : "fasterwhisper",
        canUseTestingControls ? companyName : undefined,
      );
      const { callId: id, queuePosition: pos, etaSeconds: eta } = res.data;
      setCallId(id);
      setCurrentStep("queued");
      setQueuePosition(pos ?? null);
      setEtaSeconds(eta ?? null);
      setStage("processing");
      pollStatus(id);
    } catch (err: unknown) {
      setStage("error");
      const msg =
        err && typeof err === "object" && "response" in err
          ? (err as { response: { data: { detail?: string } } }).response?.data?.detail
          : undefined;
      setErrorMsg(msg || "Upload failed. Please try again.");
    }
  };

  useEffect(() => {
    let cancelled = false;
    const loadCompanyContext = async () => {
      try {
        if (!platformScope) {
          setCompanyName(user?.clientName || "");
          setCompanyLoadError(user?.clientName ? "" : "Your account is not assigned to a company.");
          return;
        }
        const clientsRes = await adminApi.getClients();
        if (cancelled) return;
        const list = clientsRes.data.clients || [];
        setClients(list);
        const first = list[0];
        setSelectedClientId(first?.id ?? null);
        setCompanyName(first?.name ?? "");
        setCompanyLoadError(list.length ? "" : "No clients found. Create a client before uploading calls.");
      } catch {
        if (!cancelled) setCompanyLoadError("Could not load company list.");
      }
    };
    loadCompanyContext();
    return () => {
      cancelled = true;
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [platformScope, user?.clientName]);

  useEffect(() => {
    let cancelled = false;
    const loadAgents = async () => {
      if (platformScope && !selectedClientId) {
        setAgents([]);
        setSelectedAgentId("");
        return;
      }
      try {
        const response = await agentsApi.list(platformScope ? selectedClientId : undefined);
        if (cancelled) return;
        const list = response.data.agents || [];
        setAgents(list);
        setSelectedAgentId((current) => (list.some((agent) => agent.id === current) ? current : ""));
        setAgentLoadError(list.length ? "" : "No agents found for this company. Invite an agent first.");
      } catch {
        if (!cancelled) setAgentLoadError("Could not load agents.");
      }
    };
    loadAgents();
    return () => {
      cancelled = true;
    };
  }, [platformScope, selectedClientId]);

  const userRole = user?.role === "qa" ? "qa" : "admin";

  return (
    <PageTransition>
      <div className="min-h-screen relative">
        <AnimatedBackground />
        <Navbar userName={user?.name ?? ""} userRole={userRole} />

        <main className="max-w-3xl mx-auto px-5 sm:px-8 py-8 sm:py-12 space-y-8">
          <header>
            <h1 className="text-3xl sm:text-4xl font-light text-foreground tracking-tight">
              Upload <span className="font-semibold gradient-text">Call</span>
            </h1>
            <p className="text-muted-foreground mt-2 text-sm font-light">
              Upload an audio file for automated QA analysis
            </p>
          </header>

          {/* Drop Zone */}
          {(stage === "idle" || stage === "error") && (
            <GlassCard className="p-0 overflow-hidden">
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={onDrop}
                onClick={() => fileInputRef.current?.click()}
                className={cn(
                  "p-12 sm:p-16 flex flex-col items-center justify-center cursor-pointer transition-all duration-300",
                  dragOver
                    ? "bg-primary/[0.08] border-primary/30"
                    : "hover:bg-foreground/[0.02]"
                )}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ACCEPTED_TYPES.join(",")}
                  onChange={onFileInput}
                  className="hidden"
                />

                <motion.div
                  animate={dragOver ? { scale: 1.1, y: -4 } : { scale: 1, y: 0 }}
                  transition={{ type: "spring", stiffness: 300, damping: 20 }}
                >
                  <Upload className="w-10 h-10 text-muted-foreground/40 mb-4" />
                </motion.div>

                <p className="text-sm text-foreground font-medium">
                  {dragOver
                    ? "Drop your audio file here"
                    : "Drag & drop an audio file, or click to browse"}
                </p>
                <p className="text-xs text-muted-foreground mt-2">
                  MP3, WAV, FLAC, OGG, WebM — up to 200 MB
                </p>
              </div>
            </GlassCard>
          )}

          {/* Selected File */}
          {file && stage !== "completed" && (
            <GlassCard className="p-5">
              <div className="flex items-center gap-4">
                <div className="p-2.5 rounded-xl bg-primary/10">
                  <FileAudio className="w-5 h-5 text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">
                    {file.name}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {(file.size / (1024 * 1024)).toFixed(1)} MB
                  </p>
                </div>
                {stage === "idle" && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      reset();
                    }}
                    className="p-1.5 rounded-lg hover:bg-foreground/[0.06] transition-colors"
                  >
                    <X className="w-4 h-4 text-muted-foreground" />
                  </button>
                )}
              </div>
            </GlassCard>
          )}

          {file && (stage === "idle" || stage === "error") && (
            <GlassCard className="p-5">
              <div className="space-y-5">
                <div className="space-y-3">
                  <div>
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                      {platformScope ? "Client / Company" : "Company"}
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      QA scores are evaluated against the selected agent's assigned company context.
                    </p>
                  </div>
                  {platformScope ? (
                    <select
                      value={selectedClientId ?? ""}
                      onChange={(e) => {
                        const nextClientId = e.target.value ? Number(e.target.value) : null;
                        const nextClient = clients.find((client) => client.id === nextClientId);
                        setSelectedClientId(nextClientId);
                        setCompanyName(nextClient?.name ?? "");
                      }}
                      disabled={!clients.length}
                      className="w-full rounded-2xl border border-border/50 bg-background/60 px-4 py-3 text-sm text-foreground outline-none transition-colors focus:border-primary"
                    >
                      {clients.map((client) => (
                        <option key={client.id} value={client.id}>
                          {client.name}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <div className="rounded-2xl border border-border/50 bg-muted/30 px-4 py-3 text-sm text-foreground">
                      {companyName || "No company assigned"}
                    </div>
                  )}
                  {companyLoadError && (
                    <p className="text-xs text-destructive">{companyLoadError}</p>
                  )}
                </div>

                <div className="space-y-3">
                  <div>
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                      Call Agent
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Select the agent who handled this call. This controls attribution and tenant isolation.
                    </p>
                  </div>
                  <select
                    value={selectedAgentId}
                    onChange={(e) => setSelectedAgentId(e.target.value)}
                    disabled={!agents.length}
                    className="w-full rounded-2xl border border-border/50 bg-background/60 px-4 py-3 text-sm text-foreground outline-none transition-colors focus:border-primary"
                  >
                    <option value="">Select agent...</option>
                    {agents.map((agent) => (
                      <option key={agent.id} value={agent.id}>
                        {agent.name}{agent.email ? ` (${agent.email})` : ""}
                      </option>
                    ))}
                  </select>
                  {agentLoadError && (
                    <p className="text-xs text-destructive">{agentLoadError}</p>
                  )}
                </div>

                {canUseTestingControls && (
                  <>
                    <div>
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                        ASR Engine
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Platform testing control. Tenant QA/admin uploads use the production default.
                      </p>
                    </div>
                    <div className="grid gap-3">
                      <button
                        type="button"
                        onClick={() => setAsrEngine("fasterwhisper")}
                        className={cn(
                          "text-left rounded-2xl border p-4 transition-all",
                          asrEngine === "fasterwhisper"
                            ? "border-primary bg-primary/10"
                            : "border-border/50 hover:border-primary/40"
                        )}
                      >
                        <p className="text-sm font-medium text-foreground">Faster-Whisper</p>
                        <p className="text-xs text-muted-foreground mt-1">
                          Production transcription engine (CTranslate2). Faster, lower latency.
                        </p>
                      </button>
                    </div>
                  </>
                )}
              </div>
            </GlassCard>
          )}

          {/* Error Message */}
          {stage === "error" && errorMsg && (
            <GlassCard className="p-5 border-destructive/20 bg-destructive/[0.03]">
              <div className="flex items-center gap-3">
                <AlertCircle className="w-5 h-5 text-destructive flex-shrink-0" />
                <p className="text-sm text-destructive">{errorMsg}</p>
              </div>
            </GlassCard>
          )}

          {/* Upload Button */}
          {file && (stage === "idle" || stage === "error") && (
            <motion.button
              onClick={handleUpload}
              disabled={!companyName || !selectedAgentId}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              className="w-full py-3.5 rounded-2xl bg-primary text-primary-foreground font-medium text-sm
                         hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Upload & Analyze
            </motion.button>
          )}

          {/* Processing Status */}
          {(stage === "uploading" || stage === "processing") && (
            <GlassCard className="p-8 text-center">
              <Loader2 className="w-8 h-8 text-primary animate-spin mx-auto mb-4" />
              <p className="text-sm font-medium text-foreground">
                {stage === "uploading"
                  ? "Uploading file..."
                  : STEP_LABELS[currentStep] || "Processing..."}
              </p>
              <p className="text-xs text-muted-foreground mt-2">
                {currentStep === "queued" && queuePosition != null
                  ? `Queue position ${queuePosition}${etaSeconds ? ` · ETA ~${Math.ceil(etaSeconds / 60)} min` : ""}`
                  : "This may take a moment"}
              </p>
            </GlassCard>
          )}

          {/* Success */}
          {stage === "completed" && callId && (
            <GlassCard className="p-8 text-center" glow="success">
              <CheckCircle className="w-10 h-10 text-success mx-auto mb-4" />
              <p className="text-lg font-medium text-foreground mb-2">
                Analysis Complete
              </p>
              <p className="text-sm text-muted-foreground mb-6">
                The call has been processed and a QA report has been generated.
              </p>
              <div className="flex flex-col sm:flex-row gap-3 justify-center">
                <motion.button
                  onClick={() => navigate(`/call/${callId}`)}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className="px-6 py-2.5 rounded-xl bg-primary text-primary-foreground font-medium text-sm"
                >
                  View Report
                </motion.button>
                <motion.button
                  onClick={reset}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className="px-6 py-2.5 rounded-xl glass text-foreground font-medium text-sm
                             hover:bg-foreground/[0.04] transition-colors"
                >
                  Upload Another
                </motion.button>
              </div>
            </GlassCard>
          )}
        </main>
      </div>
    </PageTransition>
  );
};

export default UploadCall;
