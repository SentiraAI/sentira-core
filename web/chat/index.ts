/* La chat dei frontend Sentira. Uso, in una pagina dell'app:

     import { Chat } from "sentira-core/chat";
     <Chat chiaveSessione="rossella_session_id" testata={<SidebarTrigger />} />

   Titolo, descrizione e domande d'esempio arrivano da GET /api/chat/config
   (sentira_core.chat sul backend): qui non c'è niente di specifico del cliente. */
export { Chat } from "./Chat";
export { GraficoChat } from "./GraficoChat";
