import { useMemo, useState } from "react";
import { useSearchParams, Navigate, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Eye, EyeOff } from "lucide-react";
import { apiErrorMessage, authApi } from "@/services/api";
import { useToast } from "@/hooks/use-toast";
import PageTransition from "@/components/PageTransition";
import AnimatedBackground from "@/components/AnimatedBackground";

const AcceptInvite = () => {
  const [searchParams] = useSearchParams();
  const token = useMemo(() => searchParams.get("token") || "", [searchParams]);
  const navigate = useNavigate();
  const { toast } = useToast();

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["invite-details", token],
    queryFn: async () => {
      const response = await authApi.getInviteDetails(token);
      return response.data;
    },
    enabled: !!token,
    retry: false,
  });

  const acceptMutation = useMutation({
    mutationFn: async () => {
      const response = await authApi.acceptInvite({
        token,
        password,
        confirmPassword,
      });
      return response.data;
    },
    onSuccess: () => {
      toast({
        title: "Account activated",
        description: "Your account is now active. Please sign in.",
      });
      navigate("/login");
    },
    onError: (err: unknown) => {
      toast({
        title: "Activation failed",
        description: apiErrorMessage(err, "Failed to activate account."),
        variant: "destructive",
      });
    },
  });

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (!password || !confirmPassword) {
      toast({
        title: "Missing fields",
        description: "Please enter and confirm your password.",
        variant: "destructive",
      });
      return;
    }

    if (password !== confirmPassword) {
      toast({
        title: "Password mismatch",
        description: "Passwords do not match.",
        variant: "destructive",
      });
      return;
    }

    acceptMutation.mutate();
  };

  return (
    <PageTransition>
      <div className="min-h-screen flex items-center justify-center relative px-4">
        <AnimatedBackground />

        <div className="glass-strong rounded-3xl p-8 sm:p-10 w-full max-w-[440px] glow-primary">
          <h1 className="text-2xl font-semibold mb-2">Accept Invitation</h1>

          {isLoading && (
            <div className="py-10 flex justify-center">
              <span className="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
            </div>
          )}

          {isError && (
            <div className="text-destructive text-sm">
              {apiErrorMessage(error, "Invalid or expired invitation.")}
            </div>
          )}

          {data && (
            <>
              <div className="space-y-1 mb-6 text-sm text-muted-foreground">
                <p><span className="text-foreground font-medium">Name:</span> {data.name}</p>
                <p><span className="text-foreground font-medium">Email:</span> {data.email}</p>
                <p><span className="text-foreground font-medium">Role:</span> {data.role}</p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                    Password
                  </label>
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Enter password"
                      className="w-full h-12 px-4 pr-11 rounded-xl glass-input text-sm"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">
                    Confirm Password
                  </label>
                  <input
                    type={showPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Confirm password"
                    className="w-full h-12 px-4 rounded-xl glass-input text-sm"
                  />
                </div>

                <button
                  type="submit"
                  disabled={acceptMutation.isPending}
                  className="w-full h-12 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground font-semibold text-sm shadow-lg shadow-primary/20 hover:brightness-110 transition-all disabled:opacity-60"
                >
                  {acceptMutation.isPending ? "Activating..." : "Activate Account"}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </PageTransition>
  );
};

export default AcceptInvite;
