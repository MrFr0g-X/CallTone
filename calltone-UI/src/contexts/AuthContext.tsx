import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

export type UserRole = "agent" | "qa" | "admin";

interface AuthUser {
  email: string;
  name: string;
  role: UserRole;
}

interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  login: (email: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
};

// Derive role & name from email for mock auth
const resolveUser = (email: string): AuthUser => {
  const name = email.split("@")[0];
  const displayName = name.charAt(0).toUpperCase() + name.slice(1);

  let role: UserRole = "agent";
  if (email.includes("admin")) role = "admin";
  else if (email.includes("qa")) role = "qa";

  return { email, name: displayName, role };
};

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const stored = sessionStorage.getItem("calltone_user");
    return stored ? JSON.parse(stored) : null;
  });

  const login = useCallback((email: string) => {
    const u = resolveUser(email);
    setUser(u);
    sessionStorage.setItem("calltone_user", JSON.stringify(u));
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    sessionStorage.removeItem("calltone_user");
  }, []);

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};
