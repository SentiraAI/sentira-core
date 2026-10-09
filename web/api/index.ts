/* Client HTTP dei frontend Sentira. Uso:

     import { createClient, getJson, messaggio, useApi } from "sentira-core/api";
     const { data, error, refetch } = useApi<Stats>("/api/stats");
     try { await createClient().post("/api/x", corpo); } catch (e) { toast.error(messaggio(e, "Salvataggio fallito")); } */
export * from "./cliente";
export { useApi } from "./useApi";
