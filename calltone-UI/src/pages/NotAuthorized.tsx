import { Link } from "react-router-dom";
import { ShieldX, ArrowLeft } from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import PageTransition from "@/components/PageTransition";
import { useAuth } from "@/contexts/AuthContext";
import { roleHome } from "@/lib/roles";

const NotAuthorized = () => {
  const { user } = useAuth();

  const homeRoute = roleHome(user?.role);

  return (
    <PageTransition>
      <div className="min-h-screen relative flex items-center justify-center">
        <AnimatedBackground />
        <div className="text-center space-y-6 px-4">
          <ShieldX className="w-16 h-16 text-destructive/60 mx-auto" />
          <h1 className="text-5xl sm:text-6xl font-extralight text-foreground/20 tracking-tight">403</h1>
          <p className="text-lg text-muted-foreground font-light">
            You don't have permission to access this page.
          </p>
          <Link
            to={homeRoute}
            className="inline-flex items-center gap-2 text-sm text-accent hover:text-accent/80 transition-colors font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            Go to your dashboard
          </Link>
        </div>
      </div>
    </PageTransition>
  );
};

export default NotAuthorized;
