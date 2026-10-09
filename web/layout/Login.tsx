"use client";

import { useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "motion/react";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";

/** Il titolo che entra una lettera alla volta. */
function LetterSplit({ text, delay = 0 }: { text: string; delay?: number }) {
  const shouldReduce = useReducedMotion();
  if (shouldReduce) return <span>{text}</span>;
  return (
    <span className="inline-flex" aria-label={text}>
      {text.split("").map((l, i) => (
        <motion.span
          key={i}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1], delay: delay + i * 0.04 }}
          style={{ display: "inline-block", whiteSpace: "pre" }}
        >
          {l}
        </motion.span>
      ))}
    </span>
  );
}

/** La pagina di login: una password, un bottone. Il cookie, la firma e la durata li
 *  decide il backend (sentira_core.auth); qui solo la chiamata e i messaggi, compreso
 *  il limite di 5 tentativi al minuto. */
export function Login({ logo, titolo, sottotitolo, sfondo }: {
  /** il logo del prodotto, già dimensionato */
  logo: ReactNode;
  titolo: string;
  sottotitolo: string;
  /** decorazioni dietro la card (particelle, grana…) */
  sfondo?: ReactNode;
}) {
  const router = useRouter();
  const shouldReduce = useReducedMotion();
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [shake, setShake] = useState(0);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ password }),
      });
      if (res.ok) {
        router.replace("/");
        return;
      }
      setError(res.status === 429 ? "Troppi tentativi. Riprova tra un minuto." : "Password errata. Riprova.");
      setShake((s) => s + 1);
    } catch {
      setError("Errore di connessione. Riprova.");
      setShake((s) => s + 1);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background p-4">
      {sfondo}

      <motion.div
        key={shake}
        animate={shake > 0 && !shouldReduce ? { x: [0, -10, 10, -8, 8, -4, 4, 0] } : undefined}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="relative z-10 w-full max-w-sm"
      >
        <div className="rounded-2xl border border-t-2 border-white/10 border-t-primary bg-card/60 shadow-2xl backdrop-blur-[24px]">
          <div className="px-6 pt-8 pb-4 text-center">
            {logo}
            <h1 className="font-display text-xl">
              <LetterSplit text={titolo} delay={0.4} />
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">{sottotitolo}</p>
          </div>

          <div className="px-6 pb-8">
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={show ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoFocus
                    autoComplete="current-password"
                    aria-invalid={!!error}
                    aria-describedby={error ? "login-errore" : undefined}
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShow((s) => !s)}
                    className="absolute top-1/2 right-2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    aria-label={show ? "Nascondi password" : "Mostra password"}
                  >
                    {show ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              {error && (
                <p id="login-errore" className="text-sm text-destructive" role="alert">
                  {error}
                </p>
              )}

              <Button type="submit" className="w-full hover:[box-shadow:0_0_16px_var(--primary)_/_0.3] active:scale-[0.98]" disabled={loading}>
                {loading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Accesso in corso...
                  </>
                ) : (
                  "Accedi"
                )}
              </Button>
            </form>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
