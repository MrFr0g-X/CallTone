import { Link, Navigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, CheckCircle2, ChevronRight, FileAudio, ShieldCheck, Sparkles, Workflow, Zap } from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import PageTransition from "@/components/PageTransition";
import ThemeToggle from "@/components/ThemeToggle";
import TrueFocus from "@/components/TrueFocus";
import calltoneIcon from "@/assets/calltone-icon.png";
import calltoneHeroIcon from "@/assets/calltone-hero-icon.png";
import calltoneLogo from "@/assets/calltone-logo.png";
import { useAuth } from "@/contexts/AuthContext";
import { roleHome } from "@/lib/roles";

const fadeUp = {
  hidden: { opacity: 0, y: 32 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, delay: i * 0.1, ease: [0.25, 0.46, 0.45, 0.94] as const },
  }),
};

const workflowSteps = [
  {
    title: "Audio intake",
    body: "Upload WAV, MP3, FLAC, M4A, WebM, or OGG calls. The API validates format, size, company, and ASR engine before queueing.",
    icon: FileAudio,
  },
  {
    title: "Layer 1 signal extraction",
    body: "The GPU pipeline creates speaker turns, transcript text, role labels, and emotion-aware call structure for downstream scoring.",
    icon: Workflow,
  },
  {
    title: "Layer 2 QA scoring",
    body: "Seven QA dimensions are scored against the selected company context, with evidence quotes and confidence per dimension.",
    icon: ShieldCheck,
  },
  {
    title: "Review workspace",
    body: "QA, admin, and agent views expose only the routes each role is allowed to use, with reports and audio linked to the call record.",
    icon: CheckCircle2,
  },
];

const Home = () => {
  const { isAuthenticated, isLoading, user } = useAuth();

  if (!isLoading && isAuthenticated && user) {
    return <Navigate to={roleHome(user.role)} replace />;
  }

  return (
    <PageTransition>
      <div className="relative min-h-screen overflow-x-hidden">
        <AnimatedBackground />

        <nav className="sticky top-0 z-50 border-b border-border/50 bg-background/60 backdrop-blur-2xl">
          <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-5 sm:px-8">
            <Link to="/" className="flex items-center gap-2">
              <img src={calltoneIcon} alt="CallTone" className="-my-8 h-28 w-28 md:hidden" />
              <img src={calltoneLogo} alt="CallTone" className="-my-12 hidden h-36 md:block" />
            </Link>

            <div className="flex items-center gap-3">
              <ThemeToggle />
              <Link
                to="/login"
                className="rounded-xl bg-gradient-to-r from-primary to-accent px-5 py-2 text-[13px] font-semibold text-primary-foreground shadow-lg shadow-primary/20 transition-all hover:brightness-110"
              >
                Sign In
              </Link>
            </div>
          </div>
        </nav>

        <main>
          <section className="relative pb-20 pt-16 sm:pb-28 sm:pt-28">
            <div className="mx-auto max-w-7xl px-5 sm:px-8">
              <div className="mx-auto max-w-3xl text-center">
                <motion.img
                  src={calltoneHeroIcon}
                  alt="CallTone AI"
                  initial={{ opacity: 0, y: 32 }}
                  animate={{ opacity: 1, y: [0, -8, 0] }}
                  transition={{
                    opacity: { duration: 0.6, ease: [0.25, 0.46, 0.45, 0.94] },
                    y: { delay: 0.6, duration: 4, repeat: Infinity, ease: "easeInOut" },
                  }}
                  className="mx-auto mb-6 h-36 w-36 object-contain sm:h-48 sm:w-48"
                />

                <motion.div
                  variants={fadeUp}
                  initial="hidden"
                  animate="visible"
                  custom={0.5}
                  className="mb-8 inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-4 py-1.5 text-xs font-medium text-accent"
                >
                  <Zap className="h-3.5 w-3.5" />
                  AI-Powered Call Quality Assurance
                </motion.div>

                <motion.div variants={fadeUp} initial="hidden" animate="visible" custom={1} className="mb-6">
                  <TrueFocus
                    sentence="Turn Every Call Into a Quality Insight"
                    manualMode={false}
                    blurAmount={4}
                    animationDuration={0.5}
                    pauseBetweenAnimations={1.2}
                    className="text-4xl font-bold leading-[1.1] tracking-tight sm:text-5xl lg:text-6xl"
                  />
                </motion.div>

                <motion.p
                  variants={fadeUp}
                  initial="hidden"
                  animate="visible"
                  custom={2}
                  className="mx-auto mb-10 max-w-2xl text-lg font-light leading-relaxed text-muted-foreground sm:text-xl"
                >
                  CallTone analyzes customer service calls end-to-end: transcript, speaker turns, company-context scoring,
                  evidence, and review-ready QA output from one production workflow.
                </motion.p>

                <motion.div
                  variants={fadeUp}
                  initial="hidden"
                  animate="visible"
                  custom={3}
                  className="flex flex-col items-center justify-center gap-4 sm:flex-row"
                >
                  <Link
                    to="/login"
                    className="group flex items-center gap-2 rounded-2xl bg-gradient-to-r from-primary to-accent px-8 py-3.5 text-sm font-semibold text-primary-foreground shadow-xl shadow-primary/25 transition-all duration-300 hover:brightness-110 hover:shadow-2xl hover:shadow-primary/30"
                  >
                    Open Workspace
                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                  </Link>
                  <a
                    href="#workflow"
                    className="glass flex items-center gap-2 rounded-2xl px-8 py-3.5 text-sm font-semibold transition-all duration-300 hover:bg-foreground/[0.06]"
                  >
                    View Production Workflow
                    <ChevronRight className="h-4 w-4" />
                  </a>
                </motion.div>
              </div>
            </div>
          </section>

          <section id="workflow" className="relative border-t border-border/40 py-16 sm:py-20">
            <div className="mx-auto max-w-7xl px-5 sm:px-8">
              <motion.div
                variants={fadeUp}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true, margin: "-80px" }}
                custom={0}
                className="mx-auto mb-10 max-w-3xl text-center"
              >
                <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-4 py-1.5 text-xs font-semibold text-primary">
                  <Sparkles className="h-3.5 w-3.5" />
                  Deployed production flow
                </div>
                <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
                  From upload to evidence-backed QA report
                </h2>
                <p className="mt-4 text-sm leading-6 text-muted-foreground sm:text-base">
                  This section describes the actual CallTone path used after sign-in. It is not demo pricing, marketing filler,
                  or a fake dashboard surface.
                </p>
              </motion.div>

              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                {workflowSteps.map((step, index) => (
                  <motion.div
                    key={step.title}
                    variants={fadeUp}
                    initial="hidden"
                    whileInView="visible"
                    viewport={{ once: true, margin: "-80px" }}
                    custom={index + 1}
                    className="glass-strong rounded-3xl p-6"
                  >
                    <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-2xl bg-accent/10 text-accent">
                      <step.icon className="h-5 w-5" />
                    </div>
                    <p className="text-xs font-semibold uppercase tracking-[0.24em] text-muted-foreground">
                      Step {index + 1}
                    </p>
                    <h3 className="mt-3 text-lg font-semibold text-foreground">{step.title}</h3>
                    <p className="mt-3 text-sm leading-6 text-muted-foreground">{step.body}</p>
                  </motion.div>
                ))}
              </div>
            </div>
          </section>
        </main>
      </div>
    </PageTransition>
  );
};

export default Home;
