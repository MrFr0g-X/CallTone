import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import PageTransition from "@/components/PageTransition";

const NotFound = () => {
  return (
    <PageTransition>
      <div className="min-h-screen relative flex items-center justify-center">
        <AnimatedBackground />
        <div className="text-center space-y-6 px-4">
          <h1 className="text-8xl sm:text-9xl font-extralight text-foreground/20 tracking-tight">404</h1>
          <p className="text-lg text-muted-foreground font-light">This page doesn't exist.</p>
          <Link
            to="/"
            className="inline-flex items-center gap-2 text-sm text-accent hover:text-accent/80 transition-colors font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            Go back home
          </Link>
        </div>
      </div>
    </PageTransition>
  );
};

export default NotFound;
