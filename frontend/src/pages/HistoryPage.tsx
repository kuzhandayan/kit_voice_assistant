import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, type ConversationSummary, type StoredMessage } from "../api/client";
import { Transcript } from "../components/Transcript";
import { when } from "../lib/format";

export function HistoryPage() {
  const { id } = useParams();
  const [items, setItems] = useState<ConversationSummary[] | null>(null);
  const [messages, setMessages] = useState<StoredMessage[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.history().then(setItems).catch(() => setError("History couldn't load. Refresh to try again."));
  }, []);

  useEffect(() => {
    setMessages(null);
    if (id) api.conversation(id).then((c) => setMessages(c.messages)).catch(() => setError("That conversation couldn't load."));
  }, [id]);

  return (
    <div className="history">
      <aside className="history__list" aria-label="Past conversations">
        <h1>History</h1>
        {error && <p className="notice notice--error">{error}</p>}
        {!items && !error && <p className="muted">Loading conversations…</p>}
        {items?.length === 0 && <p className="muted">No conversations yet. Talk to the assistant and they'll appear here.</p>}
        <ul>
          {items?.map((c) => (
            <li key={c.id}>
              <Link to={`/history/${c.id}`} className={c.id === id ? "active" : undefined} aria-current={c.id === id ? "page" : undefined}>
                <span className="history__title">{c.title}</span>
                <span className="muted">{when(c.updated_at)}</span>
              </Link>
            </li>
          ))}
        </ul>
      </aside>
      <section className="history__detail" aria-label="Conversation">
        {!id && <p className="muted">Pick a conversation to read it.</p>}
        {messages && <Transcript messages={messages.map((m) => ({ id: String(m.id), role: m.role, text: m.content }))} />}
      </section>
    </div>
  );
}
