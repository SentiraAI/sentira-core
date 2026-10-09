import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { RotateCcw } from "lucide-react";
import { AnimatedNumber } from "../motion";
import { Button } from "./button";
import { Card, CardContent, CardHeader, CardTitle } from "./card";
import { Skeleton } from "./skeleton";
import { cn } from "./utils";

/* Gli stati di una sezione (vuota, in errore, in caricamento) e la card di un
   indicatore: uguali in ogni prodotto, così una sezione vuota non sembra rotta. */

export function EmptyState({ icon: Icon, title, body, action, className }: {
  icon?: LucideIcon;
  title: string;
  body?: ReactNode;
  /** un bottone o un link sotto il testo */
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex min-h-40 flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-border p-8 text-center", className)}>
      {Icon && <Icon size={32} className="mb-2 text-muted-foreground/40" aria-hidden="true" />}
      <p className="text-sm font-medium text-muted-foreground">{title}</p>
      {body && <p className="text-xs text-muted-foreground/70">{body}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

/** Una sezione che non si è caricata, detto dove sta: il resto della pagina continua a funzionare. */
export function ErrorState({ title = "Impossibile caricare i dati", body, onRetry, className }: {
  title?: string;
  body?: ReactNode;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div role="alert" className={cn("rounded-lg border border-destructive/30 bg-destructive/5 p-6 text-center", className)}>
      <p className="text-sm text-destructive">{title}</p>
      {body && <p className="mt-1 text-xs text-muted-foreground">{body}</p>}
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-3 gap-1.5" onClick={onRetry}>
          <RotateCcw size={14} /> Riprova
        </Button>
      )}
    </div>
  );
}

/** La forma del contenuto prima del contenuto: `height` uguale a quello vero, o la pagina salta. */
export function LoadingState({ rows = 3, height = "h-24", grid = false, className }: {
  rows?: number;
  height?: string;
  /** card affiancate invece di righe impilate */
  grid?: boolean;
  className?: string;
}) {
  return (
    <div role="status" aria-busy="true" aria-label="Caricamento"
      className={cn(grid ? "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3" : "space-y-4", className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className={cn("w-full rounded-lg", height)} />
      ))}
    </div>
  );
}

/** Un indicatore: titolo, numero che conta fino al valore, riga sotto. Con `onClick` è un bottone. */
export function KpiCard({ title, value, suffix, icon: Icon, sub, onClick, colore = "text-primary" }: {
  title: string;
  /** un numero conta fino al valore; una stringa ("—") resta com'è */
  value: number | string;
  suffix?: string;
  icon: LucideIcon;
  sub?: ReactNode;
  onClick?: () => void;
  /** classe del colore dell'icona, es. "text-destructive" quando il numero è un allarme */
  colore?: string;
}) {
  return (
    <Card
      onClick={onClick}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      } : undefined}
      className={cn(
        "border-t-2 border-t-primary transition-transform duration-200 ease-out hover:-translate-y-0.5",
        onClick && "cursor-pointer",
      )}
    >
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon size={18} className={colore} />
      </CardHeader>
      <CardContent>
        <div className="metric font-instrument text-3xl font-bold">
          {typeof value === "number" ? <AnimatedNumber value={value} /> : value}{suffix}
        </div>
        {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
      </CardContent>
    </Card>
  );
}
