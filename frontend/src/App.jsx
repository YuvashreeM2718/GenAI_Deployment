import { useEffect, useState } from "react";
import ChatWindow from "./components/ChatWindow.jsx";
import { fetchSession, sendMessage } from "./api.js";

function getOrCreateSessionId() {
  let id = localStorage.getItem("session_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("session_id", id);
  }
  return id;
}

const WELCOME_MESSAGE = {
  role: "assistant",
  content:
    'Hi! I can help you get an interior design quotation. Tell me a bit about your property to get started — e.g. "I need interiors for my 3BHK apartment."',
};

export default function App() {
  const [sessionId, setSessionId] = useState(getOrCreateSessionId);
  const [messages, setMessages] = useState([WELCOME_MESSAGE]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  function handleNewSession() {
    if (loading) return;

    const newSessionId = crypto.randomUUID();
    localStorage.setItem("session_id", newSessionId);
    setSessionId(newSessionId);
    setMessages([WELCOME_MESSAGE]);
    setInput("");
  }

  // Restore prior conversation on load, if this session already has one.
  useEffect(() => {
    fetchSession(sessionId).then((data) => {
      if (data?.messages?.length) {
        //setMessages(data.messages);
      }
    });
  }, [sessionId]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
    setInput("");
    setLoading(true);

    try {
      await sendMessage(sessionId, text, (event) => {
        if (event.type !== "token" && event.type !== "reply") return;

        setMessages((prev) => {
          const next = [...prev];
          const lastMessage = next[next.length - 1];
          if (lastMessage?.role === "assistant") {
            next[next.length - 1] = {
              ...lastMessage,
              content:
                event.type === "token"
                  ? lastMessage.content + event.content
                  : event.content,
            };
          }
          return next;
        });
      });

      setMessages((prev) => {
        const next = [...prev];
        const lastMessage = next[next.length - 1];
        if (lastMessage?.role === "assistant" && !lastMessage.content) {
          next[next.length - 1] = { ...lastMessage, content: "(no reply)" };
        }
        return next;
      });
    } catch (err) {
      setMessages((prev) => {
        const next = [...prev];
        const lastMessage = next[next.length - 1];
        if (lastMessage?.role === "assistant") {
          next[next.length - 1] = {
            ...lastMessage,
            content: "Sorry, something went wrong reaching the server.",
          };
        }
        return next;
      });
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>Interior Design Quotation Assistant</h1>
        <button
          className="new-session-button"
          onClick={handleNewSession}
          disabled={loading}
          title="Start a new session"
        >
          New chat
        </button>
      </header>

      <ChatWindow messages={messages} loading={loading} />

      <div className="input-bar">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your message..."
          rows={1}
        />
        <button onClick={handleSend} disabled={loading}>
          Send
        </button>
      </div>
    </div>
  );
}
