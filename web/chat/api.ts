/* Chiamate al backend della chat, stesse regole del client delle app:
   cookie di sessione, 401 = di nuovo al login, errori come testo leggibile. */

export const BOTTONE =
  "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg border border-transparent text-sm font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0";

function messaggioErrore(status: number, corpo: string): string {
  try {
    const detail = JSON.parse(corpo)?.detail;
    if (typeof detail === "string" && detail) return detail;
  } catch {
    // non è JSON: si guarda il testo qui sotto
  }
  const testo = corpo.trim();
  return testo && !testo.startsWith("<") && testo.length < 300 ? testo : `Errore ${status}`;
}

export async function richiesta(metodo: string, path: string, corpo?: unknown, signal?: AbortSignal) {
  const res = await fetch(path, {
    method: metodo,
    credentials: "include",
    signal,
    headers: corpo === undefined ? undefined : { "Content-Type": "application/json" },
    body: corpo === undefined ? undefined : JSON.stringify(corpo),
  });
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Sessione scaduta");
  }
  if (!res.ok) throw new Error(messaggioErrore(res.status, await res.text().catch(() => "")));
  return res;
}

/** Il backend manda UTC senza offset: senza la Z "Ora" diventava "2h fa". */
export function dataRelativa(iso: string): string {
  const allora = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
  const sec = Math.floor((Date.now() - allora.getTime()) / 1000);
  const min = Math.floor(sec / 60);
  const ore = Math.floor(min / 60);
  const giorni = Math.floor(ore / 24);
  if (sec < 60) return "Ora";
  if (min < 60) return `${min}m fa`;
  if (ore < 24) return `${ore}h fa`;
  if (giorni < 7) return `${giorni}g fa`;
  if (giorni < 30) return `${Math.floor(giorni / 7)} sett. fa`;
  return allora.toLocaleDateString("it-IT");
}
