import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";
import { ApiError, get, post } from "./api";
import type { Me } from "./types";

interface AuthValue {
  me: Me | null;
  loading: boolean;
  login: (mobile: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  can: (module: string, mode?: "view" | "edit") => boolean;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        return await get<Me>("/auth/me/");
      } catch (e) {
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return null;
        throw e;
      }
    },
    staleTime: 5 * 60_000,
    retry: false,
  });

  const value: AuthValue = {
    me: data ?? null,
    loading: isLoading,
    login: async (mobile, password) => {
      const me = await post<Me>("/auth/login/", { mobile, password });
      qc.clear();
      qc.setQueryData(["me"], me);
    },
    logout: async () => {
      await post("/auth/logout/");
      qc.clear();
      qc.setQueryData(["me"], null);
    },
    can: (module, mode = "view") => {
      if (!data) return false;
      return (mode === "edit" ? data.modules_edit : data.modules_view).includes(module);
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
