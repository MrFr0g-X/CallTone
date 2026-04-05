import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { Settings, Globe, Lock, Bell, Database, Save, Cpu, Loader2 } from "lucide-react";
import GlassCard from "@/components/GlassCard";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";
import { pipelineApi } from "@/services/api";
import type { PipelineSettingsResponse } from "@/services/api";

const AdminSettings = () => {
  const { toast } = useToast();
  const [settings, setSettings] = useState({
    platformName: "CallTone",
    supportEmail: "support@calltone.ai",
    enforceSSO: false,
    require2FA: true,
    sessionTimeout: 30,
    emailNotifications: true,
    slackIntegration: false,
    dataRetention: 90,
    autoBackup: true,
  });

  const [pipeline, setPipeline] = useState<PipelineSettingsResponse>({
    audioMode: "denoise",
    injectionScan: "static",
    numSpeakers: null,
    reportMode: "simple",
    useConsensus: false,
    companyName: "BankServ Global",
  });
  const [pipelineLoading, setPipelineLoading] = useState(true);
  const [pipelineSaving, setPipelineSaving] = useState(false);

  useEffect(() => {
    pipelineApi.getSettings()
      .then(r => setPipeline(r.data))
      .catch(() => {})
      .finally(() => setPipelineLoading(false));
  }, []);

  const handleSave = () => {
    toast({ title: "Settings saved", description: "Platform settings have been updated." });
  };

  const handlePipelineSave = async () => {
    setPipelineSaving(true);
    try {
      const r = await pipelineApi.updateSettings(pipeline);
      setPipeline(r.data);
      toast({ title: "Pipeline settings saved", description: "AI pipeline configuration updated." });
    } catch {
      toast({ title: "Save failed", description: "Could not save pipeline settings.", variant: "destructive" });
    } finally {
      setPipelineSaving(false);
    }
  };

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-3xl sm:text-4xl font-light text-foreground">
          Platform <span className="font-bold gradient-text">Settings</span>
        </h1>
        <p className="text-sm text-muted-foreground mt-1">Configure global platform preferences</p>
      </header>

      <div className="grid gap-6">
        {/* General */}
        <GlassCard className="rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-5">
            <Globe className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">General</h2>
          </div>
          <div className="grid sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">Platform Name</label>
              <input
                type="text"
                value={settings.platformName}
                onChange={(e) => setSettings({ ...settings, platformName: e.target.value })}
                className="w-full h-10 px-4 rounded-xl glass-input text-sm"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">Support Email</label>
              <input
                type="email"
                value={settings.supportEmail}
                onChange={(e) => setSettings({ ...settings, supportEmail: e.target.value })}
                className="w-full h-10 px-4 rounded-xl glass-input text-sm"
              />
            </div>
          </div>
        </GlassCard>

        {/* Security */}
        <GlassCard className="rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-5">
            <Lock className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Security</h2>
          </div>
          <div className="space-y-4">
            {[
              { key: "enforceSSO", label: "Enforce SSO", description: "Require all admins to sign in via SSO provider" },
              { key: "require2FA", label: "Require 2FA", description: "Enforce two-factor authentication for all admin accounts" },
            ].map(item => (
              <div key={item.key} className="flex items-center justify-between py-2">
                <div>
                  <p className="text-sm font-medium">{item.label}</p>
                  <p className="text-xs text-muted-foreground">{item.description}</p>
                </div>
                <button
                  onClick={() => setSettings(s => ({ ...s, [item.key]: !s[item.key as keyof typeof s] }))}
                  className={cn(
                    "w-10 h-6 rounded-full transition-colors flex items-center px-0.5",
                    settings[item.key as keyof typeof settings] ? "bg-success justify-end" : "bg-muted-foreground/20 justify-start"
                  )}
                >
                  <div className="w-5 h-5 rounded-full bg-white shadow-sm" />
                </button>
              </div>
            ))}
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">Session Timeout (minutes)</label>
              <input
                type="number"
                value={settings.sessionTimeout}
                onChange={(e) => setSettings({ ...settings, sessionTimeout: parseInt(e.target.value) || 30 })}
                className="w-full max-w-[200px] h-10 px-4 rounded-xl glass-input text-sm"
              />
            </div>
          </div>
        </GlassCard>

        {/* Notifications */}
        <GlassCard className="rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-5">
            <Bell className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Notifications</h2>
          </div>
          <div className="space-y-4">
            {[
              { key: "emailNotifications", label: "Email Notifications", description: "Send email alerts for critical platform events" },
              { key: "slackIntegration", label: "Slack Integration", description: "Post notifications to a Slack channel" },
            ].map(item => (
              <div key={item.key} className="flex items-center justify-between py-2">
                <div>
                  <p className="text-sm font-medium">{item.label}</p>
                  <p className="text-xs text-muted-foreground">{item.description}</p>
                </div>
                <button
                  onClick={() => setSettings(s => ({ ...s, [item.key]: !s[item.key as keyof typeof s] }))}
                  className={cn(
                    "w-10 h-6 rounded-full transition-colors flex items-center px-0.5",
                    settings[item.key as keyof typeof settings] ? "bg-success justify-end" : "bg-muted-foreground/20 justify-start"
                  )}
                >
                  <div className="w-5 h-5 rounded-full bg-white shadow-sm" />
                </button>
              </div>
            ))}
          </div>
        </GlassCard>

        {/* Data */}
        <GlassCard className="rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-5">
            <Database className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Data Management</h2>
          </div>
          <div className="space-y-4">
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">Data Retention (days)</label>
              <input
                type="number"
                value={settings.dataRetention}
                onChange={(e) => setSettings({ ...settings, dataRetention: parseInt(e.target.value) || 90 })}
                className="w-full max-w-[200px] h-10 px-4 rounded-xl glass-input text-sm"
              />
            </div>
            <div className="flex items-center justify-between py-2">
              <div>
                <p className="text-sm font-medium">Automatic Backups</p>
                <p className="text-xs text-muted-foreground">Daily automated database backups</p>
              </div>
              <button
                onClick={() => setSettings(s => ({ ...s, autoBackup: !s.autoBackup }))}
                className={cn(
                  "w-10 h-6 rounded-full transition-colors flex items-center px-0.5",
                  settings.autoBackup ? "bg-success justify-end" : "bg-muted-foreground/20 justify-start"
                )}
              >
                <div className="w-5 h-5 rounded-full bg-white shadow-sm" />
              </button>
            </div>
          </div>
        </GlassCard>

        {/* AI Pipeline */}
        <GlassCard className="rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-5">
            <Cpu className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">AI Pipeline</h2>
          </div>
          {pipelineLoading ? (
            <div className="flex items-center gap-2 text-muted-foreground text-sm py-4">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading pipeline settings...
            </div>
          ) : (
            <div className="space-y-5">
              {/* Company Name */}
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">Default Company Context</label>
                <input
                  type="text"
                  value={pipeline.companyName}
                  onChange={e => setPipeline(p => ({ ...p, companyName: e.target.value }))}
                  className="w-full max-w-xs h-10 px-4 rounded-xl glass-input text-sm"
                  placeholder="e.g. BankServ Global"
                />
                <p className="text-[11px] text-muted-foreground mt-1">Company policy used when scoring calls.</p>
              </div>

              {/* Audio Mode */}
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">Audio Processing</label>
                <div className="flex flex-wrap gap-2">
                  {(["none", "denoise", "enhance"] as const).map(opt => (
                    <button
                      key={opt}
                      onClick={() => setPipeline(p => ({ ...p, audioMode: opt }))}
                      className={cn(
                        "px-4 py-2 rounded-xl text-xs font-medium border transition-all capitalize",
                        pipeline.audioMode === opt
                          ? "bg-accent/20 border-accent text-accent"
                          : "border-border/50 text-muted-foreground hover:border-accent/50"
                      )}
                    >{opt === "none" ? "Skip (Fastest)" : opt === "denoise" ? "Denoise Only" : "Full Enhance"}</button>
                  ))}
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  None = skip, Denoise = noise removal only, Enhance = denoise + super-resolution.
                </p>
              </div>

              {/* Injection Scan */}
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">Prompt Injection Scan</label>
                <div className="flex gap-2">
                  {(["static", "llm"] as const).map(opt => (
                    <button
                      key={opt}
                      onClick={() => setPipeline(p => ({ ...p, injectionScan: opt }))}
                      className={cn(
                        "px-4 py-2 rounded-xl text-xs font-medium border transition-all uppercase",
                        pipeline.injectionScan === opt
                          ? "bg-accent/20 border-accent text-accent"
                          : "border-border/50 text-muted-foreground hover:border-accent/50"
                      )}
                    >{opt === "static" ? "Static (Fast)" : "LLM (Thorough)"}</button>
                  ))}
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  Static = regex patterns only. LLM = uses Llama to verify, slower but catches novel attacks.
                </p>
              </div>

              {/* Num Speakers */}
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">Speaker Count</label>
                <div className="flex gap-2 flex-wrap">
                  {[null, 2, 3, 4].map(n => (
                    <button
                      key={String(n)}
                      onClick={() => setPipeline(p => ({ ...p, numSpeakers: n }))}
                      className={cn(
                        "px-4 py-2 rounded-xl text-xs font-medium border transition-all",
                        pipeline.numSpeakers === n
                          ? "bg-accent/20 border-accent text-accent"
                          : "border-border/50 text-muted-foreground hover:border-accent/50"
                      )}
                    >{n === null ? "Auto-detect" : `${n} Speakers`}</button>
                  ))}
                </div>
              </div>

              {/* Report Mode */}
              <div>
                <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">Report Generation</label>
                <div className="flex gap-2 flex-wrap">
                  {(["none", "simple", "narrative"] as const).map(opt => (
                    <button
                      key={opt}
                      onClick={() => setPipeline(p => ({ ...p, reportMode: opt }))}
                      className={cn(
                        "px-4 py-2 rounded-xl text-xs font-medium border transition-all capitalize",
                        pipeline.reportMode === opt
                          ? "bg-accent/20 border-accent text-accent"
                          : "border-border/50 text-muted-foreground hover:border-accent/50"
                      )}
                    >{opt === "none" ? "Skip" : opt === "simple" ? "Simple (Table)" : "Narrative (LLM)"}</button>
                  ))}
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">LaTeX report format. Narrative uses Llama and is slower.</p>
              </div>

              {/* Use Consensus */}
              <div className="flex items-center justify-between py-2">
                <div>
                  <p className="text-sm font-medium">Consensus Scoring</p>
                  <p className="text-xs text-muted-foreground">Run each criterion 3 times and take the median — more accurate but 3× slower.</p>
                </div>
                <button
                  onClick={() => setPipeline(p => ({ ...p, useConsensus: !p.useConsensus }))}
                  className={cn(
                    "w-10 h-6 rounded-full transition-colors flex items-center px-0.5",
                    pipeline.useConsensus ? "bg-success justify-end" : "bg-muted-foreground/20 justify-start"
                  )}
                >
                  <div className="w-5 h-5 rounded-full bg-white shadow-sm" />
                </button>
              </div>

              {/* Save pipeline */}
              <div className="pt-2">
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={handlePipelineSave}
                  disabled={pipelineSaving}
                  className="flex items-center gap-2 px-5 py-2 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground text-sm font-semibold shadow-lg shadow-primary/20 hover:brightness-110 transition-all disabled:opacity-60"
                >
                  {pipelineSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  Save Pipeline Settings
                </motion.button>
              </div>
            </div>
          )}
        </GlassCard>
      </div>

      {/* Save */}
      <div className="flex justify-end">
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={handleSave}
          className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground text-sm font-semibold shadow-lg shadow-primary/20 hover:brightness-110 transition-all"
        >
          <Save className="w-4 h-4" />
          Save Settings
        </motion.button>
      </div>
    </div>
  );
};

export default AdminSettings;
