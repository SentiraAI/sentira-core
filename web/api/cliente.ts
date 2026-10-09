/* L'unico modo in cui un frontend Sentira parla col suo backend.

   Cookie di sessione sempre (`credentials: "include"`), un 401 porta al login in un
   punto solo, e gli errori arrivano già come testo da mostrare: chi cattura legge
   `e.message` o usa `messaggio(e, "…")`, mai il JSON grezzo. */

const BASE = process.env.NEXT_PUBLIC_API_BASE || "";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

/** Il backend risponde `{"detail": "..."}` o, se la validazione Pydantic fallisce,
 *  `{"detail": [{"msg": "..."}]}`: all'utente va il testo, non il JSON. */
function messaggioErrore(status: number, corpo: string): string {
  try {
    const detail = JSON.parse(corpo)?.detail;
    if (typeof detail === "string" && detail) return detail;
    if (Array.isArray(detail)) {
      const msg = detail.map((d) => d?.msg).filter(Boolean).join("; ");
      if (msg) return msg;
    }
  } catch {
    // non è JSON: si guarda il testo qui sotto
  }
  // Una pagina HTML (es. 502 del proxy) non deve finire in un toast.
  const testo = corpo.trim();
  return testo && !testo.startsWith("<") && testo.length < 300 ? testo : `Errore ${status}`;
}

export async function request(method: string, path: string, init?: RequestInit): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, { ...init, credentials: "include", method });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e; // annullata da chi l'ha lanciata
    throw new ApiError(0, "Server non raggiungibile");
  }

  if (res.status === 401) {
    if (window.location.pathname !== "/login") window.location.href = "/login";
    throw new ApiError(401, "Sessione scaduta");
  }
  if (!res.ok) {
    const testo = await res.text().catch(() => "");
    throw new ApiError(res.status, messaggioErrore(res.status, testo));
  }
  return res;
}

// `body === undefined`, non `body ?`: 0, false e "" sono corpi validi.
function conJson(method: string, path: string, body?: unknown, init?: RequestInit) {
  return request(method, path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers as Record<string, string>) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

export function createClient() {
  return {
    get: (path: string, init?: RequestInit) => request("GET", path, init),
    post: (path: string, body?: unknown, init?: RequestInit) => conJson("POST", path, body, init),
    patch: (path: string, body?: unknown, init?: RequestInit) => conJson("PATCH", path, body, init),
    put: (path: string, body?: unknown, init?: RequestInit) => conJson("PUT", path, body, init),
    delete: (path: string, init?: RequestInit) => request("DELETE", path, init),
  };
}

export async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  return (await request("GET", path, init)).json();
}

export async function postJson<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
  return (await conJson("POST", path, body, init)).json();
}

/** Il testo da mostrare per un errore: quello del backend se c'è, altrimenti `fallback`. */
export function messaggio(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback;
}

/** Gli eventi di una risposta SSE (`data: {...}` per riga), già letti come JSON.
 *  Una riga che non è JSON si salta: meglio perdere un evento che la risposta. */
export async function* leggiSSE<T = Record<string, unknown>>(res: Response): AsyncGenerator<T> {
  const reader = res.body?.getReader();
  if (!reader) throw new Error("Nessuna risposta dal server");
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    const righe = buffer.split("\n");
    buffer = righe.pop() ?? "";
    for (const riga of righe) {
      if (!riga.startsWith("data: ")) continue;
      let evento: T;
      try {
        evento = JSON.parse(riga.slice(6));
      } catch {
        continue;
      }
      yield evento;
    }
  }
}
