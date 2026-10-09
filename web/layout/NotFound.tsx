import Link from "next/link";
import { Home } from "lucide-react";
import { buttonVariants } from "../ui/button";
import { cn } from "../ui/utils";

/** La pagina 404 (app/not-found.tsx). */
export function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center p-4 text-center">
      <div>
        <h1 className="text-6xl font-bold text-muted-foreground/30">404</h1>
        <h2 className="mt-4 text-xl font-semibold">Pagina non trovata</h2>
        <p className="mt-2 text-muted-foreground">La pagina che cerchi non esiste o è stata spostata.</p>
        <Link href="/" className={cn(buttonVariants({ variant: "default" }), "mt-6 inline-flex items-center gap-2")}>
          <Home size={16} />
          Torna alla dashboard
        </Link>
      </div>
    </div>
  );
}
