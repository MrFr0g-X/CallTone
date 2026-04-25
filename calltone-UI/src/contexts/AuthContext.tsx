import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import { authApi } from "@/services/api";

export type UserRole = "agent" | "qa" | "admin" | "super_admin" | "manager" | "viewer";

interface AuthUser {
  id?: number;
  email: string;
  name: string;
  role: UserRole;
  clientId?: number | null;
}

interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<AuthUser>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const stored = localStorage.getItem("calltone_user");
    return stored ? JSON.parse(stored) : null;
  });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem("calltone_token");

      if (!token) {
        setIsLoading(false);
        return;
      }

      try {
        const response = await authApi.me();
        const me = response.data;

        const authUser: AuthUser = {
          id: me.id,
          email: me.email,
          name: me.name,
          role: me.role,
          clientId: me.clientId,
        };

        setUser(authUser);
        localStorage.setItem("calltone_user", JSON.stringify(authUser));
      } catch {
        localStorage.removeItem("calltone_token");
        localStorage.removeItem("calltone_user");
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };

    initAuth();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const response = await authApi.login(email, password);
    const { access_token, user } = response.data;

    localStorage.setItem("calltone_token", access_token);

    const authUser: AuthUser = {
      id: user.id,
      email: user.email,
      name: user.name,
      role: user.role,
      clientId: user.clientId,
    };

    setUser(authUser);
    localStorage.setItem("calltone_user", JSON.stringify(authUser));

    return authUser;
  }, []);

  const logout = useCallback(async () => {
    localStorage.removeItem("calltone_token");
    localStorage.removeItem("calltone_user");
    setUser(null);

    try {
      await authApi.logout();
    } catch {
      // Local logout is already complete; the API call is best-effort only.
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isLoading,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
