import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Phone, BarChart3, Shield, Users, Zap, Brain,
  ArrowRight, CheckCircle2, Star, ChevronRight,
  Headphones, TrendingUp, MessageSquare
} from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import PageTransition from "@/components/PageTransition";
import ThemeToggle from "@/components/ThemeToggle";
import calltoneLogo from "@/assets/calltone-logo.png";
import calltoneIcon from "@/assets/calltone-icon.png";
import TrueFocus from "@/components/TrueFocus";
import BlurText from "@/components/BlurText";
import CountUp from "@/components/CountUp";
import calltoneHeroIcon from "@/assets/calltone-hero-icon.png";

const fadeUp = {
  hidden: { opacity: 0, y: 32 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, delay: i * 0.1, ease: [0.25, 0.46, 0.45, 0.94] as const },
  }),
};

const features = [
  {
    icon: Brain,
    title: "AI-Powered Analysis",
    description: "Automatically score calls on politeness, empathy, conflict detection, and resolution rate using advanced NLP.",
  },
  {
    icon: BarChart3,
    title: "Real-Time Dashboards",
    description: "Live performance metrics for agents and QA teams with interactive charts and trend analysis.",
  },
  {
    icon: Shield,
    title: "Quality Assurance",
    description: "Comprehensive QA workflows with flagging, review statuses, and multi-dimensional scoring.",
  },
  {
    icon: MessageSquare,
    title: "Smart Transcripts",
    description: "Emotion-tagged transcripts with speaker identification and sentiment highlighting.",
  },
  {
    icon: TrendingUp,
    title: "Performance Trends",
    description: "Track agent improvement over time with weekly, monthly, and quarterly trend reports.",
  },
  {
    icon: Headphones,
    title: "Audio Playback",
    description: "Custom audio player with waveform visualization and timestamp-linked transcript navigation.",
  },
];

const pricing = [
  {
    name: "Starter",
    price: "$49",
    period: "/agent/mo",
    description: "For small teams getting started with call QA",
    features: ["Up to 10 agents", "500 calls/month", "Basic AI scoring", "Email support", "Weekly reports"],
    highlighted: false,
  },
  {
    name: "Professional",
    price: "$99",
    period: "/agent/mo",
    description: "For growing call centers that need deeper insights",
    features: ["Up to 50 agents", "5,000 calls/month", "Advanced AI analysis", "Priority support", "Custom reports", "API access", "Emotion detection"],
    highlighted: true,
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    description: "For large organizations with custom requirements",
    features: ["Unlimited agents", "Unlimited calls", "Custom AI models", "Dedicated support", "SSO & SAML", "On-premise option", "SLA guarantee", "Custom integrations"],
    highlighted: false,
  },
];

const stats = [
  { value: 98, suffix: "%", label: "Accuracy Rate" },
  { value: 2, suffix: "M+", label: "Calls Analyzed" },
  { value: 500, suffix: "+", label: "Teams Using CallTone" },
  { value: 40, suffix: "%", label: "Faster QA Reviews" },
];

const Landing = () => {
  return (
    <PageTransition>
      <div className="min-h-screen relative overflow-x-hidden">
        <AnimatedBackground />

        {/* ─── Navbar ─── */}
        <nav className="sticky top-0 z-50 bg-background/60 backdrop-blur-2xl border-b border-border/50">
          <div className="max-w-7xl mx-auto px-5 sm:px-8 h-14 flex items-center justify-between">
            <Link to="/" className="flex items-center gap-2">
              <img src={calltoneIcon} alt="CallTone" className="w-28 h-28 -my-8 md:hidden" />
              <img src={calltoneLogo} alt="CallTone" className="hidden md:block h-36 -my-12" />
            </Link>

            <div className="hidden md:flex items-center gap-8">
              <a href="#features" className="text-[13px] font-medium text-muted-foreground hover:text-foreground transition-colors">Features</a>
              <a href="#pricing" className="text-[13px] font-medium text-muted-foreground hover:text-foreground transition-colors">Pricing</a>
              <a href="#testimonials" className="text-[13px] font-medium text-muted-foreground hover:text-foreground transition-colors">Testimonials</a>
            </div>

            <div className="flex items-center gap-3">
              <ThemeToggle />
              <Link
                to="/login"
                className="px-5 py-2 rounded-xl text-[13px] font-semibold bg-gradient-to-r from-primary to-accent text-primary-foreground shadow-lg shadow-primary/20 hover:brightness-110 transition-all"
              >
                Sign In
              </Link>
            </div>
          </div>
        </nav>

        {/* ─── Hero ─── */}
        <section className="relative pt-20 sm:pt-32 pb-20 sm:pb-28">
          <div className="max-w-7xl mx-auto px-5 sm:px-8">
            <div className="max-w-3xl mx-auto text-center">
              <motion.img
                src={calltoneHeroIcon}
                alt="CallTone AI"
                initial={{ opacity: 0, y: 32 }}
                animate={{
                  opacity: 1,
                  y: [0, -8, 0],
                }}
                transition={{
                  opacity: { duration: 0.6, ease: [0.25, 0.46, 0.45, 0.94] },
                  y: {
                    delay: 0.6,
                    duration: 4,
                    repeat: Infinity,
                    ease: "easeInOut",
                  },
                }}
                className="w-36 h-36 sm:w-48 sm:h-48 mb-6 mx-auto object-contain"
              />

              <motion.div
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                custom={0.5}
                className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-accent/30 bg-accent/10 text-accent text-xs font-medium mb-8"
              >
                <Zap className="w-3.5 h-3.5" />
                AI-Powered Call Quality Assurance
              </motion.div>

              <motion.div
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                custom={1}
                className="mb-6"
              >
                <TrueFocus
                  sentence="Turn Every Call Into a Quality Insight"
                  manualMode={false}
                  blurAmount={4}
                  animationDuration={0.5}
                  pauseBetweenAnimations={1.2}
                  className="text-4xl sm:text-5xl lg:text-6xl font-bold leading-[1.1] tracking-tight"
                />
              </motion.div>

              <motion.p
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                custom={2}
                className="text-lg sm:text-xl text-muted-foreground font-light max-w-2xl mx-auto mb-10 leading-relaxed"
              >
                CallTone uses advanced AI to analyze customer service calls in real-time.
                Score agent performance, detect conflicts, and elevate your customer experience — automatically.
              </motion.p>

              <motion.div
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                custom={3}
                className="flex flex-col sm:flex-row items-center justify-center gap-4"
              >
                <Link
                  to="/login"
                  className="group flex items-center gap-2 px-8 py-3.5 rounded-2xl text-sm font-semibold bg-gradient-to-r from-primary to-accent text-primary-foreground shadow-xl shadow-primary/25 hover:brightness-110 hover:shadow-2xl hover:shadow-primary/30 transition-all duration-300"
                >
                  Start Free Trial
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                </Link>
                <a
                  href="#features"
                  className="flex items-center gap-2 px-8 py-3.5 rounded-2xl text-sm font-semibold glass hover:bg-foreground/[0.06] transition-all duration-300"
                >
                  See How It Works
                  <ChevronRight className="w-4 h-4" />
                </a>
              </motion.div>
            </div>

            {/* Stats bar */}
            <motion.div
              variants={fadeUp}
              initial="hidden"
              animate="visible"
              custom={5}
              className="mt-20 sm:mt-28 grid grid-cols-2 md:grid-cols-4 gap-4"
            >
              {stats.map((stat, i) => (
                <div key={stat.label} className="glass rounded-2xl px-6 py-5 text-center">
                  <p className="text-2xl sm:text-3xl font-bold gradient-text">
                    <CountUp to={stat.value} duration={2.5} delay={i * 0.15} />
                    {stat.suffix}
                  </p>
                  <p className="text-xs sm:text-[13px] text-muted-foreground mt-1 font-medium">{stat.label}</p>
                </div>
              ))}
            </motion.div>
          </div>
        </section>

        {/* ─── Features ─── */}
        <section id="features" className="py-20 sm:py-28">
          <div className="max-w-7xl mx-auto px-5 sm:px-8">
            <div className="text-center mb-16">
              <BlurText
                text="Everything You Need for Call Excellence"
                delay={100}
                animateBy="words"
                direction="top"
                className="text-3xl sm:text-4xl font-bold mb-4 justify-center"
              />
              <BlurText
                text="A complete suite of tools designed for call center teams who demand the best quality assurance."
                delay={50}
                animateBy="words"
                direction="bottom"
                className="text-muted-foreground text-lg max-w-2xl mx-auto font-light justify-center"
              />
            </div>

            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {features.map((feature, i) => (
                <motion.div
                  key={feature.title}
                  variants={fadeUp}
                  initial="hidden"
                  whileInView="visible"
                  viewport={{ once: true, margin: "-50px" }}
                  custom={i}
                  whileHover={{ y: -4, scale: 1.01 }}
                  className="glass rounded-2xl p-7 group cursor-default"
                >
                  <div className="w-11 h-11 rounded-xl bg-accent/10 flex items-center justify-center mb-5 group-hover:bg-accent/20 transition-colors">
                    <feature.icon className="w-5 h-5 text-accent" />
                  </div>
                  <h3 className="text-base font-semibold mb-2">{feature.title}</h3>
                  <p className="text-sm text-muted-foreground leading-relaxed font-light">{feature.description}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── How It Works ─── */}
        <section className="py-20 sm:py-28">
          <div className="max-w-7xl mx-auto px-5 sm:px-8">
            <div className="text-center mb-16">
              <BlurText
                text="Simple Setup, Powerful Results"
                delay={100}
                animateBy="words"
                direction="top"
                className="text-3xl sm:text-4xl font-bold mb-4 justify-center"
              />
              <BlurText
                text="Get your team up and running in minutes, not weeks."
                delay={50}
                animateBy="words"
                direction="bottom"
                className="text-muted-foreground text-lg max-w-2xl mx-auto font-light justify-center"
              />
            </div>

            <div className="grid md:grid-cols-3 gap-8">
              {[
                { step: "01", title: "Connect Your Calls", description: "Integrate with your existing phone system or upload call recordings. We support all major providers." },
                { step: "02", title: "AI Analyzes Everything", description: "Our AI processes each call — scoring politeness, empathy, conflict detection, and resolution quality." },
                { step: "03", title: "Act on Insights", description: "QA teams review flagged calls, agents track their performance, and managers see the full picture." },
              ].map((item, i) => (
                <motion.div
                  key={item.step}
                  variants={fadeUp}
                  initial="hidden"
                  whileInView="visible"
                  viewport={{ once: true, margin: "-50px" }}
                  custom={i}
                  className="relative"
                >
                  <span className="text-6xl sm:text-7xl font-black text-accent/10 absolute -top-4 -left-2">{item.step}</span>
                  <div className="pt-10 pl-2">
                    <h3 className="text-lg font-semibold mb-2">{item.title}</h3>
                    <p className="text-sm text-muted-foreground leading-relaxed font-light">{item.description}</p>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── Pricing ─── */}
        <section id="pricing" className="py-20 sm:py-28">
          <div className="max-w-7xl mx-auto px-5 sm:px-8">
            <div className="text-center mb-16">
              <BlurText
                text="Plans That Scale With You"
                delay={100}
                animateBy="words"
                direction="top"
                className="text-3xl sm:text-4xl font-bold mb-4 justify-center"
              />
              <BlurText
                text="Start small and grow. No hidden fees, no long-term contracts."
                delay={50}
                animateBy="words"
                direction="bottom"
                className="text-muted-foreground text-lg max-w-2xl mx-auto font-light justify-center"
              />
            </div>

            <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
              {pricing.map((plan, i) => (
                <motion.div
                  key={plan.name}
                  variants={fadeUp}
                  initial="hidden"
                  whileInView="visible"
                  viewport={{ once: true, margin: "-50px" }}
                  custom={i}
                  whileHover={{ y: -4 }}
                  className={`rounded-2xl p-7 flex flex-col ${
                    plan.highlighted
                      ? "glass-strong glow-accent border-accent/30 relative"
                      : "glass"
                  }`}
                >
                  {plan.highlighted && (
                    <span className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full bg-gradient-to-r from-primary to-accent text-primary-foreground text-xs font-semibold shadow-lg">
                      Most Popular
                    </span>
                  )}
                  <h3 className="text-lg font-semibold mb-1">{plan.name}</h3>
                  <p className="text-sm text-muted-foreground font-light mb-5">{plan.description}</p>
                  <div className="mb-6">
                    <span className="text-4xl font-bold">{plan.price}</span>
                    <span className="text-sm text-muted-foreground">{plan.period}</span>
                  </div>
                  <ul className="space-y-3 mb-8 flex-1">
                    {plan.features.map((f) => (
                      <li key={f} className="flex items-start gap-2.5 text-sm">
                        <CheckCircle2 className="w-4 h-4 text-success mt-0.5 shrink-0" />
                        <span className="text-muted-foreground">{f}</span>
                      </li>
                    ))}
                  </ul>
                  <Link
                    to="/login"
                    className={`w-full py-3 rounded-xl text-sm font-semibold text-center transition-all duration-300 block ${
                      plan.highlighted
                        ? "bg-gradient-to-r from-primary to-accent text-primary-foreground shadow-lg shadow-primary/25 hover:brightness-110"
                        : "glass hover:bg-foreground/[0.06]"
                    }`}
                  >
                    {plan.price === "Custom" ? "Contact Sales" : "Start Free Trial"}
                  </Link>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── Testimonials ─── */}
        <section id="testimonials" className="py-20 sm:py-28">
          <div className="max-w-7xl mx-auto px-5 sm:px-8">
            <div className="text-center mb-16">
              <BlurText
                text="Trusted by Leading Teams"
                delay={100}
                animateBy="words"
                direction="top"
                className="text-3xl sm:text-4xl font-bold mb-4 justify-center"
              />
            </div>

            <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
              {[
                { name: "Sarah Chen", role: "Head of QA, TeleCorp", text: "CallTone reduced our QA review time by 60%. The AI scoring is incredibly accurate and our agents love the performance dashboards." },
                { name: "Marcus Rivera", role: "Operations Director, ConnectPlus", text: "We went from reviewing 5% of calls to 100%. The conflict detection alone has saved us from dozens of escalations." },
                { name: "Aisha Patel", role: "VP Customer Success, CloudTalk", text: "The emotion-tagged transcripts are a game changer. We can pinpoint exactly where calls go well or need improvement." },
              ].map((testimonial, i) => (
                <motion.div
                  key={testimonial.name}
                  variants={fadeUp}
                  initial="hidden"
                  whileInView="visible"
                  viewport={{ once: true, margin: "-50px" }}
                  custom={i}
                  className="glass rounded-2xl p-7"
                >
                  <div className="flex gap-1 mb-4">
                    {[...Array(5)].map((_, j) => (
                      <Star key={j} className="w-4 h-4 fill-warning text-warning" />
                    ))}
                  </div>
                  <p className="text-sm text-muted-foreground leading-relaxed font-light mb-6">"{testimonial.text}"</p>
                  <div>
                    <p className="text-sm font-semibold">{testimonial.name}</p>
                    <p className="text-xs text-muted-foreground">{testimonial.role}</p>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        {/* ─── CTA ─── */}
        <section className="py-20 sm:py-28">
          <div className="max-w-4xl mx-auto px-5 sm:px-8 text-center">
            <motion.div
              variants={fadeUp}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: "-100px" }}
              custom={0}
              className="glass-strong rounded-3xl p-10 sm:p-16 glow-primary"
            >
              <h2 className="text-3xl sm:text-4xl font-bold mb-4">
                Ready to Transform Your{" "}
                <span className="gradient-text">Call Quality?</span>
              </h2>
              <p className="text-muted-foreground text-lg max-w-xl mx-auto font-light mb-8">
                Join 500+ teams already using CallTone to deliver exceptional customer experiences.
              </p>
              <Link
                to="/login"
                className="group inline-flex items-center gap-2 px-8 py-3.5 rounded-2xl text-sm font-semibold bg-gradient-to-r from-primary to-accent text-primary-foreground shadow-xl shadow-primary/25 hover:brightness-110 hover:shadow-2xl transition-all duration-300"
              >
                Get Started for Free
                <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
              </Link>
            </motion.div>
          </div>
        </section>

        {/* ─── Footer ─── */}
        <footer className="border-t border-border/50 py-10">
          <div className="max-w-7xl mx-auto px-5 sm:px-8">
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <img src={calltoneIcon} alt="CallTone" className="w-16 h-16 -my-4" />
                <span className="text-sm text-muted-foreground font-light">© 2026 CallTone. All rights reserved.</span>
              </div>
              <div className="flex items-center gap-6">
                <a href="#" className="text-xs text-muted-foreground hover:text-foreground transition-colors">Privacy</a>
                <a href="#" className="text-xs text-muted-foreground hover:text-foreground transition-colors">Terms</a>
                <a href="#" className="text-xs text-muted-foreground hover:text-foreground transition-colors">Contact</a>
              </div>
            </div>
          </div>
        </footer>
      </div>
    </PageTransition>
  );
};

export default Landing;
