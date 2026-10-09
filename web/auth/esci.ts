/** Logout e ritorno al login. Anche se la rete cade si va al login: restare su una
 *  pagina dopo aver premuto "Esci" sembrerebbe un bottone rotto. */
export async function esci(): Promise<void> {
  try {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
  } catch {
    // il cookie resta finché scade, ma l'utente ha chiesto di uscire
  }
  window.location.href = "/login";
}
