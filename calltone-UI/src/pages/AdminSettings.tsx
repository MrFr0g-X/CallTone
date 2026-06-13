import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ArchiveX, CheckCircle2, Cpu, Loader2, Mail, RefreshCw, RotateCcw, Save, Send, XCircle } from "lucide-react";
import GlassCard from "@/components/GlassCard";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { adminApi, apiErrorMessage, contextApi, mailApi, pipelineApi } from "@/services/api";
import type { AdminClientItem, ClientPolicy, CompanyContextSummary, MailSettingsResponse, PipelineJobResponse, PipelineQueueResponse, PipelineSettingsResponse } from "@/services/api";
import { useAuth } from "@/contexts/AuthContext";
import { isPlatformScope } from "@/lib/roles";

const AdminSettings = () => {
  const { toast } = useToast();
  const { user } = useAuth();
  const platformScope = isPlatformScope(user);
  const tenantScope = !platformScope;
  const [pipeline, setPipeline] = useState<PipelineSettingsResponse>({
    audioMode: "denoise",
    injectionScan: "static",
    numSpeakers: null,
    reportMode: "narrative",
    useConsensus: false,
    companyName: "",
  });
  const [companies, setCompanies] = useState<CompanyContextSummary[]>([]);
  const [queue, setQueue] = useState<PipelineQueueResponse | null>(null);
  const [jobs, setJobs] = useState<PipelineJobResponse[]>([]);
  const [mail, setMail] = useState<MailSettingsResponse | null>(null);
  const [clientDirectory, setClientDirectory] = useState<AdminClientItem[]>([]);
  const [policyClientId, setPolicyClientId] = useState<number | null>(null);
  const [clientPolicy, setClientPolicy] = useState<ClientPolicy | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [queueLoading, setQueueLoading] = useState(false);
  const [mailTestLoading, setMailTestLoading] = useState(false);
  const [policyLoading, setPolicyLoading] = useState(false);
  const [policySaving, setPolicySaving] = useState(false);
  const [jobActionCallId, setJobActionCallId] = useState<string | null>(null);
  const canManagePolicy = user?.capabilities?.canManageUsers ?? false;
  const settingsTitle = platformScope ? "Platform" : "Company";
  const settingsSubtitle = platformScope
    ? "Owner and Super Admin controls for all tenants, mail, GPU queue, and platform defaults."
    : `Company-scoped controls for ${user?.clientName ?? "your company"}. Platform-only settings are hidden.`;

  const loadQueueState = async () => {
    setQueueLoading(true);
    try {
      const [queueRes, jobsRes] = await Promise.all([
        pipelineApi.getQueue(),
        pipelineApi.getJobs(undefined, 20),
      ]);
      setQueue(queueRes.data);
      setJobs(jobsRes.data.jobs);
    } catch (error: unknown) {
      toast({
        title: "Queue unavailable",
        description: apiErrorMessage(error, "Could not load pipeline queue."),
        variant: "destructive",
      });
    } finally {
      setQueueLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      pipelineApi.getSettings(),
      contextApi.listCompanies(),
      pipelineApi.getQueue(),
      pipelineApi.getJobs(undefined, 20),
      platformScope ? mailApi.getSettings() : Promise.resolve({ data: null as MailSettingsResponse | null }),
    ])
      .then(([settingsRes, companiesRes, queueRes, jobsRes, mailRes]) => {
        if (cancelled) return;
        setPipeline(settingsRes.data);
        setCompanies(companiesRes.data.companies || []);
        setQueue(queueRes.data);
        setJobs(jobsRes.data.jobs);
        setMail(mailRes.data);
      })
      .catch(() => {
        toast({
          title: "Settings unavailable",
          description: "Could not load live pipeline configuration.",
          variant: "destructive",
        });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [toast, platformScope]);

  useEffect(() => {
    if (!platformScope) return;
    let cancelled = false;
    adminApi
      .getClients()
      .then((response) => {
        if (cancelled) return;
        const clients = response.data.clients || [];
        setClientDirectory(clients);
        if (!policyClientId && clients.length > 0) {
          setPolicyClientId(clients[0].id);
        }
      })
      .catch((error: unknown) => {
        toast({
          title: "Clients unavailable",
          description: apiErrorMessage(error, "Could not load client policy targets."),
          variant: "destructive",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [platformScope, policyClientId, toast]);

  useEffect(() => {
    const targetClientId = platformScope ? policyClientId : null;
    if (platformScope && !targetClientId) return;

    let cancelled = false;
    setPolicyLoading(true);
    adminApi
      .getClientPolicy(targetClientId)
      .then((response) => {
        if (cancelled) return;
        setClientPolicy(response.data.policy);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setClientPolicy(null);
        toast({
          title: "Access policy unavailable",
          description: apiErrorMessage(error, "Could not load client access policy."),
          variant: "destructive",
        });
      })
      .finally(() => {
        if (!cancelled) setPolicyLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [platformScope, policyClientId, user?.id, toast]);

  const handlePipelineSave = async () => {
    setSaving(true);
    try {
      const response = await pipelineApi.updateSettings(pipeline);
      setPipeline(response.data);
      toast({ title: "Pipeline settings saved", description: "Future uploads will use this configuration." });
    } catch (error: unknown) {
      toast({
        title: "Save failed",
        description: apiErrorMessage(error, "Could not save pipeline settings."),
        variant: "destructive",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleMailTest = async () => {
    setMailTestLoading(true);
    try {
      const response = await mailApi.sendTest();
      const statusResponse = await mailApi.getSettings();
      setMail(statusResponse.data);
      toast({
        title: response.data.ok ? "Test email sent" : "Test email recorded",
        description: response.data.ok
          ? `Mailtrap accepted the test email to ${response.data.event.recipientEmail}.`
          : response.data.event.error || `Email status: ${response.data.event.status}`,
        variant: response.data.ok ? "default" : "destructive",
      });
    } catch (error: unknown) {
      toast({
        title: "Mail test failed",
        description: apiErrorMessage(error, "Could not send the test email."),
        variant: "destructive",
      });
    } finally {
      setMailTestLoading(false);
    }
  };

  const updatePolicyField = <K extends keyof ClientPolicy>(key: K, value: ClientPolicy[K]) => {
    setClientPolicy((policy) => (policy ? { ...policy, [key]: value } : policy));
  };

  const handlePolicySave = async () => {
    if (!clientPolicy) return;
    setPolicySaving(true);
    try {
      const response = await adminApi.updateClientPolicy({
        ...clientPolicy,
        clientId: platformScope ? policyClientId : clientPolicy.clientId,
      });
      setClientPolicy(response.data.policy);
      toast({
        title: "Access policy saved",
        description: "Company permissions are enforced immediately by the backend.",
      });
    } catch (error: unknown) {
      toast({
        title: "Policy save failed",
        description: apiErrorMessage(error, "Could not update client access policy."),
        variant: "destructive",
      });
    } finally {
      setPolicySaving(false);
    }
  };

  const handleRetryJob = async (callId: string) => {
    setJobActionCallId(callId);
    try {
      await pipelineApi.retryJob(callId);
      await loadQueueState();
      toast({ title: "Job requeued", description: `Call ${callId} is back in the GPU queue.` });
    } catch (error: unknown) {
      toast({
        title: "Retry failed",
        description: apiErrorMessage(error, "Could not retry this pipeline job."),
        variant: "destructive",
      });
    } finally {
      setJobActionCallId(null);
    }
  };

  const handleDeadLetterJob = async (callId: string) => {
    setJobActionCallId(callId);
    try {
      await pipelineApi.deadLetterJob(callId);
      await loadQueueState();
      toast({ title: "Job dead-lettered", description: `Call ${callId} will not be retried automatically.` });
    } catch (error: unknown) {
      toast({
        title: "Dead-letter failed",
        description: apiErrorMessage(error, "Could not dead-letter this pipeline job."),
        variant: "destructive",
      });
    } finally {
      setJobActionCallId(null);
    }
  };

  const agentPolicyFlags = [
    ["agentPortalEnabled", "Enable agent portal", "If disabled, agents cannot use their dashboard at all."],
    ["agentCanViewCallList", "Agent call list", "Allow agents to see their own calls list."],
    ["agentCanOpenCallDetail", "Call detail page", "Allow agents to open individual call reports."],
    ["agentCanPlayAudio", "Audio playback", "Allow agents to stream their own call audio."],
    ["agentCanViewTranscript", "Transcript", "Allow agents to read transcript text and speaker turns."],
    ["agentCanViewScores", "Scores", "Allow agents to see scores, severity, and trends."],
    ["agentCanViewEvidence", "Evidence", "Allow agents to see QA evidence quotes."],
    ["agentCanViewAiReport", "AI report", "Allow agents to see the generated narrative report."],
    ["agentCanViewTrends", "Trends", "Allow agents to see historical performance trends."],
  ] as const;

  const qaPolicyFlags = [
    ["qaCanUploadCalls", "QA uploads", "Allow QA/admin users in this company to submit calls."],
    ["qaCanManageContextTickets", "Context tickets", "Allow QA/admin users to submit and review context change tickets."],
    ...(platformScope
      ? ([["tenantAdminCanInviteAdmins", "Tenant admin invitations", "Allow this company admin to invite additional company admins."]] as const)
      : []),
  ] as const;

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl sm:text-4xl font-light text-foreground">
          {settingsTitle} <span className="font-bold gradient-text">Settings</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          {settingsSubtitle}
        </p>
      </header>

      <GlassCard className="rounded-2xl p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-accent" />
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                Company Access Policy
              </h2>
            </div>
            <p className="max-w-3xl text-xs leading-5 text-muted-foreground">
              {platformScope
                ? "Select a client and control what that company's agents, QA users, and tenant admins can see or operate."
                : "These controls apply only to your company. Owner-only options, such as allowing tenant admins to invite other admins, are not exposed here."}
            </p>
          </div>

          {platformScope && (
            <select
              value={policyClientId ?? ""}
              onChange={(event) => setPolicyClientId(event.target.value ? Number(event.target.value) : null)}
              className="h-10 min-w-[240px] rounded-xl glass-input px-4 text-sm"
            >
              {clientDirectory.length === 0 ? (
                <option value="">No clients found</option>
              ) : (
                clientDirectory.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.name}
                  </option>
                ))
              )}
            </select>
          )}
          {tenantScope && (
            <div className="rounded-xl border border-border/50 bg-muted/20 px-4 py-2 text-sm text-foreground">
              {user?.clientName ?? "Assigned company"}
            </div>
          )}
        </div>

        {policyLoading ? (
          <div className="mt-5 flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading access policy...
          </div>
        ) : clientPolicy ? (
          <div className="mt-6 space-y-6">
            <section>
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Agent visibility
              </p>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {agentPolicyFlags.map(([key, label, description]) => (
                  <label
                    key={key}
                    className={cn(
                      "rounded-xl border border-border/50 bg-muted/10 p-4 transition-colors",
                      !canManagePolicy && "opacity-70",
                    )}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-medium text-foreground">{label}</span>
                      <button
                        type="button"
                        disabled={!canManagePolicy}
                        onClick={() => updatePolicyField(key, !clientPolicy[key])}
                        className={cn(
                          "flex h-6 w-10 items-center rounded-full px-0.5 transition-colors disabled:cursor-not-allowed",
                          clientPolicy[key] ? "justify-end bg-success" : "justify-start bg-muted-foreground/25",
                        )}
                        aria-label={`Toggle ${label}`}
                      >
                        <span className="h-5 w-5 rounded-full bg-white shadow-sm" />
                      </button>
                    </div>
                    <p className="mt-2 text-[11px] leading-5 text-muted-foreground">{description}</p>
                  </label>
                ))}
              </div>
            </section>

            <section>
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                QA and tenant admin operations
              </p>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {qaPolicyFlags.map(([key, label, description]) => (
                  <label key={key} className="rounded-xl border border-border/50 bg-muted/10 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-medium text-foreground">{label}</span>
                      <button
                        type="button"
                        disabled={!canManagePolicy}
                        onClick={() => updatePolicyField(key, !clientPolicy[key])}
                        className={cn(
                          "flex h-6 w-10 items-center rounded-full px-0.5 transition-colors disabled:cursor-not-allowed",
                          clientPolicy[key] ? "justify-end bg-success" : "justify-start bg-muted-foreground/25",
                        )}
                        aria-label={`Toggle ${label}`}
                      >
                        <span className="h-5 w-5 rounded-full bg-white shadow-sm" />
                      </button>
                    </div>
                    <p className="mt-2 text-[11px] leading-5 text-muted-foreground">{description}</p>
                  </label>
                ))}
              </div>

              <div className="mt-4 max-w-sm">
                <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                  QA data scope
                </label>
                <div className="h-10 w-full rounded-xl border border-border/50 bg-muted/20 px-4 py-2.5 text-sm text-foreground">
                  Whole company
                </div>
                <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
                  This is the only active QA scope in the current release. The backend enforces same-company isolation.
                </p>
              </div>
            </section>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-[11px] text-muted-foreground">
                Last updated: {clientPolicy.updatedAt ? new Date(clientPolicy.updatedAt).toLocaleString() : "Not recorded"}
              </p>
              <button
                onClick={handlePolicySave}
                disabled={!canManagePolicy || policySaving}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-primary to-accent px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-lg shadow-primary/20 transition-all hover:brightness-110 disabled:opacity-60"
              >
                {policySaving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                Save Access Policy
              </button>
            </div>
          </div>
        ) : (
          <p className="mt-5 text-sm text-muted-foreground">Select a client to load policy controls.</p>
        )}
      </GlassCard>

      {platformScope && (
      <GlassCard className="relative overflow-hidden rounded-2xl p-6">
        <div className="pointer-events-none absolute -right-16 -top-20 h-48 w-48 rounded-full bg-cyan-400/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 left-8 h-52 w-52 rounded-full bg-teal-400/10 blur-3xl" />
        <div className="relative flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="mb-5 flex items-center gap-2">
              <Mail className="h-4 w-4 text-accent" />
              <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                Mail & Notifications
              </h2>
            </div>

            {mail ? (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold",
                      mail.enabled && mail.configured
                        ? "bg-success/15 text-success"
                        : "bg-warning/15 text-warning",
                    )}
                  >
                    {mail.enabled && mail.configured ? (
                      <CheckCircle2 className="h-3.5 w-3.5" />
                    ) : (
                      <XCircle className="h-3.5 w-3.5" />
                    )}
                    {mail.enabled && mail.configured ? "Live" : "Needs config"}
                  </span>
                  <span className="rounded-full bg-accent/10 px-3 py-1 text-xs font-semibold text-accent">
                    {mail.provider}
                  </span>
                </div>

                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <div className="rounded-xl border border-border/50 bg-muted/10 p-3">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Sender</p>
                    <p className="mt-1 truncate text-sm font-medium text-foreground">{mail.fromEmail}</p>
                  </div>
                  <div className="rounded-xl border border-border/50 bg-muted/10 p-3">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Reply To</p>
                    <p className="mt-1 truncate text-sm font-medium text-foreground">{mail.replyTo}</p>
                  </div>
                  <div className="rounded-xl border border-border/50 bg-muted/10 p-3">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Last Event</p>
                    <p className="mt-1 text-sm font-medium text-foreground">
                      {mail.lastEvent ? `${mail.lastEvent.status} · ${mail.lastEvent.eventType}` : "None yet"}
                    </p>
                  </div>
                  <div className="rounded-xl border border-border/50 bg-muted/10 p-3">
                    <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Test Recipient</p>
                    <p className="mt-1 truncate text-sm font-medium text-foreground">{user?.email || "current admin"}</p>
                  </div>
                </div>

                {mail.lastEvent?.providerMessageId && (
                  <p className="font-mono text-[11px] text-muted-foreground">
                    Latest provider message ID: {mail.lastEvent.providerMessageId}
                  </p>
                )}
                {mail.lastEvent?.error && (
                  <p className="rounded-xl border border-destructive/25 bg-destructive/10 p-3 text-xs text-destructive">
                    {mail.lastEvent.error}
                  </p>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading mail configuration...
              </div>
            )}
          </div>

          <button
            onClick={handleMailTest}
            disabled={!mail || mailTestLoading}
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-primary to-accent px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-lg shadow-primary/20 transition-all hover:brightness-110 disabled:opacity-60"
          >
            {mailTestLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Send Test Email
          </button>
        </div>
      </GlassCard>
      )}

      <GlassCard className="rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-5">
            <Cpu className="w-4 h-4 text-accent" />
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            {platformScope ? "AI Pipeline Defaults" : "Company Context"}
          </h2>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-muted-foreground text-sm py-4">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading pipeline settings...
          </div>
        ) : (
          <div className="space-y-5">
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                Default Company Context
              </label>
              <select
                value={pipeline.companyName}
                onChange={(event) => setPipeline((p) => ({ ...p, companyName: event.target.value }))}
                className="w-full max-w-sm h-10 px-4 rounded-xl glass-input text-sm"
              >
                {companies.length === 0 ? (
                  <option value={pipeline.companyName}>{pipeline.companyName || "No company contexts found"}</option>
                ) : (
                  companies.map((company) => (
                    <option key={company.file || company.name} value={company.name}>
                      {company.name}
                    </option>
                  ))
                )}
              </select>
              <p className="text-[11px] text-muted-foreground mt-1">
                {platformScope
                  ? "The selected context is synced to the GPU model server before scoring."
                  : "This context is used for this company's future uploads and is enforced server-side."}
              </p>
            </div>

            {/* Audio/injection/speaker/report/consensus are CallTone-platform controls,
                not tenant-admin controls. Company admins only choose their context. */}
            {platformScope && (<>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                Audio Processing
              </label>
              <div className="flex flex-wrap gap-2">
                {(["none", "denoise", "enhance"] as const).map((option) => (
                  <button
                    key={option}
                    onClick={() => setPipeline((p) => ({ ...p, audioMode: option }))}
                    className={cn(
                      "px-4 py-2 rounded-xl text-xs font-medium border transition-all capitalize",
                      pipeline.audioMode === option
                        ? "bg-accent/20 border-accent text-accent"
                        : "border-border/50 text-muted-foreground hover:border-accent/50",
                    )}
                  >
                    {option === "none" ? "Skip" : option === "denoise" ? "Denoise" : "Enhance"}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                Prompt Injection Scan
              </label>
              <div className="flex gap-2">
                {(["static", "llm"] as const).map((option) => (
                  <button
                    key={option}
                    onClick={() => setPipeline((p) => ({ ...p, injectionScan: option }))}
                    className={cn(
                      "px-4 py-2 rounded-xl text-xs font-medium border transition-all uppercase",
                      pipeline.injectionScan === option
                        ? "bg-accent/20 border-accent text-accent"
                        : "border-border/50 text-muted-foreground hover:border-accent/50",
                    )}
                  >
                    {option === "static" ? "Static" : "LLM"}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                Speaker Count
              </label>
              <div className="flex gap-2 flex-wrap">
                {[null, 2, 3, 4].map((count) => (
                  <button
                    key={String(count)}
                    onClick={() => setPipeline((p) => ({ ...p, numSpeakers: count }))}
                    className={cn(
                      "px-4 py-2 rounded-xl text-xs font-medium border transition-all",
                      pipeline.numSpeakers === count
                        ? "bg-accent/20 border-accent text-accent"
                        : "border-border/50 text-muted-foreground hover:border-accent/50",
                    )}
                  >
                    {count === null ? "Auto-detect" : `${count} Speakers`}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                Report Generation
              </label>
              <div className="flex gap-2 flex-wrap">
                {(["none", "simple", "narrative", "both"] as const).map((option) => (
                  <button
                    key={option}
                    onClick={() => setPipeline((p) => ({ ...p, reportMode: option }))}
                    className={cn(
                      "px-4 py-2 rounded-xl text-xs font-medium border transition-all capitalize",
                      pipeline.reportMode === option
                        ? "bg-accent/20 border-accent text-accent"
                        : "border-border/50 text-muted-foreground hover:border-accent/50",
                    )}
                  >
                    {option === "none" ? "Skip" : option === "both" ? "Both" : option}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex items-center justify-between gap-4 py-2">
              <div>
                <p className="text-sm font-medium">Consensus Scoring</p>
                <p className="text-xs text-muted-foreground">
                  Runs each QA criterion multiple times and stores median confidence; slower but more stable.
                </p>
              </div>
              <button
                onClick={() => setPipeline((p) => ({ ...p, useConsensus: !p.useConsensus }))}
                className={cn(
                  "w-10 h-6 rounded-full transition-colors flex items-center px-0.5 shrink-0",
                  pipeline.useConsensus ? "bg-success justify-end" : "bg-muted-foreground/20 justify-start",
                )}
                aria-label="Toggle consensus scoring"
              >
                <div className="w-5 h-5 rounded-full bg-white shadow-sm" />
              </button>
            </div>
            </>)}

            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handlePipelineSave}
              disabled={saving}
              className="flex items-center gap-2 px-5 py-2 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground text-sm font-semibold shadow-lg shadow-primary/20 hover:brightness-110 transition-all disabled:opacity-60"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              {platformScope ? "Save Pipeline Settings" : "Save Company Context"}
            </motion.button>
          </div>
        )}
      </GlassCard>

      {/* Queue operations are a CallTone-ops concern, not a tenant-admin surface. */}
      {platformScope && (
      <GlassCard className="rounded-2xl p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-5">
          <div className="flex items-center gap-2">
            <RefreshCw className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              GPU Queue Operations
            </h2>
          </div>
          <button
            onClick={loadQueueState}
            disabled={queueLoading}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-border/50 text-xs text-muted-foreground hover:text-foreground hover:border-accent/50 disabled:opacity-60"
          >
            {queueLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Refresh
          </button>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-5">
          {[
            ["Active", queue?.activeCallId ? "1" : "0"],
            ["Queued", String(queue?.queuedCount ?? 0)],
            ["Running", String(queue?.runningCallIds?.length ?? 0)],
            ["Failed", String(queue?.failedCount ?? 0)],
            ["Drain ETA", `${Math.ceil((queue?.estimatedDrainSeconds ?? 0) / 60)}m`],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl border border-border/50 bg-muted/10 p-3">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</p>
              <p className="mt-1 text-lg font-semibold text-foreground">{value}</p>
            </div>
          ))}
        </div>

        <div className="overflow-x-auto rounded-xl border border-border/50">
          <table className="min-w-full text-sm">
            <thead className="bg-muted/20 text-[11px] uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Call</th>
                <th className="px-3 py-2 text-left">Status</th>
                <th className="px-3 py-2 text-left">Attempts</th>
                <th className="px-3 py-2 text-left">Engine</th>
                <th className="px-3 py-2 text-left">Company</th>
                <th className="px-3 py-2 text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-3 py-5 text-center text-muted-foreground">
                    No pipeline jobs found.
                  </td>
                </tr>
              ) : (
                jobs.map((job) => (
                  <tr key={job.id} className="border-t border-border/40">
                    <td className="px-3 py-2 font-mono text-xs">{job.callId.slice(0, 8)}...</td>
                    <td className="px-3 py-2">
                      <span className={cn(
                        "rounded-full px-2 py-1 text-[11px] font-semibold uppercase",
                        job.status === "completed" && "bg-success/15 text-success",
                        job.status === "failed" && "bg-destructive/15 text-destructive",
                        job.status === "running" && "bg-accent/15 text-accent",
                        job.status === "queued" && "bg-muted/30 text-muted-foreground",
                      )}>
                        {job.status}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">{job.attempts}/{job.maxAttempts}</td>
                    <td className="px-3 py-2 text-muted-foreground">{job.asrEngine}</td>
                    <td className="px-3 py-2 text-muted-foreground">{job.companyName || "-"}</td>
                    <td className="px-3 py-2">
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleRetryJob(job.callId)}
                          disabled={job.status === "running" || job.status === "completed" || jobActionCallId === job.callId}
                          className="inline-flex items-center gap-1 rounded-lg border border-border/50 px-2 py-1 text-[11px] hover:border-accent/60 disabled:opacity-40"
                        >
                          <RotateCcw className="w-3 h-3" />
                          Retry
                        </button>
                        <button
                          onClick={() => handleDeadLetterJob(job.callId)}
                          disabled={job.status === "running" || job.status === "completed" || jobActionCallId === job.callId}
                          className="inline-flex items-center gap-1 rounded-lg border border-border/50 px-2 py-1 text-[11px] hover:border-destructive/60 disabled:opacity-40"
                        >
                          <ArchiveX className="w-3 h-3" />
                          Dead-letter
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </GlassCard>
      )}
    </div>
  );
};

export default AdminSettings;
