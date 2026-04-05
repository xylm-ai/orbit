"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { saveToken } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [needsTotp, setNeedsTotp] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const res = await apiFetch<{ access_token: string }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password, totp_code: totpCode || undefined }),
      });
      saveToken(res.access_token);
      document.cookie = `orbit_token=${res.access_token};path=/`;
      router.push("/dashboard");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Login failed";
      if (msg === "2FA code required") {
        setNeedsTotp(true);
      } else {
        setError(msg);
      }
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 w-full max-w-sm">
        <h1 className="text-2xl font-bold text-white mb-1">ORBIT</h1>
        <p className="text-slate-400 text-sm mb-6">Wealth Intelligence Platform</p>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <input
            type="email" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-white text-sm outline-none focus:border-indigo-500"
            required
          />
          <input
            type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-white text-sm outline-none focus:border-indigo-500"
            required
          />
          {needsTotp && (
            <input
              type="text" placeholder="2FA Code" value={totpCode} onChange={e => setTotpCode(e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2.5 text-white text-sm outline-none focus:border-indigo-500"
              maxLength={6}
            />
          )}
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <button type="submit" className="bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg py-2.5 text-sm font-semibold transition-colors">
            {needsTotp ? "Verify & Sign in" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
