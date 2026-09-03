function renderContent(text) {
  return text.split("\n").map((line, lineIdx) => (
    <div key={lineIdx}>
      {line.split(/(https?:\/\/[^\s]+)/g).map((part, i) =>
        /^https?:\/\//.test(part) ? (
          <a key={i} href={part} target="_blank" rel="noreferrer">
            {part}
          </a>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </div>
  ));
}

export default function MessageBubble({ role, content }) {
  const isUser = role === "user";
  return (
    <div className={`message-row ${isUser ? "user" : "agent"}`}>
      <div className={`message-bubble ${isUser ? "user" : "agent"}`}>
        {renderContent(content)}
      </div>
    </div>
  );
}
