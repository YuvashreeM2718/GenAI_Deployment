const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function sendMessage(sessionId, message, onEvent) {
  const response = await fetch(`${API_BASE_URL}/chat`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ session_id: sessionId, message }),
  });

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.status}`);
  }

  if (!response.body) {
    throw new Error("Chat response does not contain a stream");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function processEvent(rawEvent) {
    const eventType =
      rawEvent
        .split("\n")
        .find((line) => line.startsWith("event:"))
        ?.slice(6)
        .trim() || "message";
    const data = rawEvent
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart())
      .join("\n")
      .trim();

    if (!data || data === "[DONE]") return;

    onEvent?.({ type: eventType, ...JSON.parse(data) });
  }

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    events.forEach(processEvent);

    if (done) break;
  }

  if (buffer.trim()) processEvent(buffer);
}

export async function fetchSession(sessionId) {
  const response = await fetch(`${API_BASE_URL}/session/${sessionId}`);
  if (!response.ok) {
    return null;
  }
  return response.json();
}
