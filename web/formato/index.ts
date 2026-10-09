/* Date, numeri e plurali dei frontend Sentira: un solo modo di leggere gli orari del
   backend e di scrivere numeri in italiano. Solo `Intl`, nessuna libreria. */

/** Il backend salva `DateTime` naive in UTC e li serializza senza offset
 *  ("2026-10-03T14:00:00"): `new Date()` li leggerebbe come ora locale, sfasati di
 *  1-2 ore. Qui si forza l'UTC se manca l'offset. Una data senza ora ("2026-10-03")
 *  resta la mezzanotte locale di quel giorno. */
export function parseUtc(iso: string): Date {
  if (/^\d{4}-\d{2}-\d{2}$/.test(iso)) return new Date(`${iso}T00:00:00`);
  return new Date(/(Z|[+-]\d{2}:?\d{2})$/i.test(iso) ? iso : `${iso}Z`);
}

const relativo = new Intl.RelativeTimeFormat("it", { numeric: "auto" });

/** "ora", "5 minuti fa", "3 ore fa", "ieri", "4 giorni fa"; dopo una settimana la data. */
export function dataRelativa(iso: string): string {
  const quando = parseUtc(iso);
  const min = Math.floor((Date.now() - quando.getTime()) / 60000);
  if (min < 1) return "ora"; // anche un orologio del server appena avanti
  if (min < 60) return relativo.format(-min, "minute");
  const ore = Math.floor(min / 60);
  if (ore < 24) return relativo.format(-ore, "hour");
  const giorni = Math.floor(ore / 24);
  if (giorni < 7) return relativo.format(-giorni, "day");
  return data(iso, "media");
}

const STILI = {
  breve: { day: "numeric", month: "short" }, // 3 ott
  numerica: { day: "2-digit", month: "2-digit", year: "numeric" }, // 03/10/2026
  media: { dateStyle: "medium" }, // 3 ott 2026
  mediaOra: { dateStyle: "medium", timeStyle: "short" }, // 3 ott 2026, 16:05
} satisfies Record<string, Intl.DateTimeFormatOptions>;

/** Una data del backend in italiano, "—" se manca o non è una data. */
export function data(iso: string | null | undefined, stile: keyof typeof STILI = "numerica"): string {
  if (!iso) return "—";
  const d = parseUtc(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleString("it-IT", STILI[stile]);
}

/** 12.345 / 3,50 con `decimali` fissi; "—" se manca. */
export function numero(n: number | null | undefined, decimali = 0): string {
  if (n == null) return "—";
  return n.toLocaleString("it-IT", { minimumFractionDigits: decimali, maximumFractionDigits: decimali });
}

/** 1.235 € con `decimali` fissi; "—" se manca. */
export function euro(n: number | null | undefined, decimali = 0): string {
  if (n == null) return "—";
  return n.toLocaleString("it-IT", {
    style: "currency", currency: "EUR", minimumFractionDigits: decimali, maximumFractionDigits: decimali,
  });
}

/** "1 veicolo" / "2 veicoli": `plurale(n, "veicolo", "veicoli")`. */
export function plurale(n: number, uno: string, molti: string): string {
  return `${n} ${n === 1 ? uno : molti}`;
}
