import { AlertCircle, Bot, Check, Copy, FileSearch, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { classNames } from "../../lib/format";
import { Markdown } from "../ui/Markdown";
import { Avatar } from "../ui/primitives";

export default function ChatMessage({ message, userName, active, activeCitation, onSelect, onCitation, onFeedback }) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";
  const citedCount = (message.citations || []).filter((c) => c.cited).length;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  };

  if (isUser) {
    return (
      <div className="msg msg-user">
        <div className="msg-bubble">{message.content}</div>
        <Avatar name={userName} size={30} />
      </div>
    );
  }

  return (
    <div className={classNames("msg msg-ai", active && "active", message.error && "error")}>
      <span className="msg-avatar">
        <Bot size={16} />
      </span>
      <div className="msg-main">
        <div className="msg-bubble" onClick={onSelect}>
          {message.error ? (
            <p className="msg-error">
              <AlertCircle size={15} /> {message.content}
            </p>
          ) : message.content ? (
            <Markdown onCitation={(index) => onCitation(message, index)} activeCitation={active ? activeCitation : null}>
              {message.content}
            </Markdown>
          ) : (
            <div className="typing">
              <span />
              <span />
              <span />
              <em>{message.citations?.length ? `Analysing ${message.citations.length} sources…` : "Searching the data room…"}</em>
            </div>
          )}
          {message.streaming && message.content && <span className="caret" />}
        </div>
        {!message.streaming && !message.error && (
          <div className="msg-actions">
            {message.citations?.length > 0 && (
              <button className={classNames("msg-sources", active && "active")} onClick={onSelect}>
                <FileSearch size={13} />
                {citedCount || message.citations.length} source{(citedCount || message.citations.length) > 1 ? "s" : ""}
              </button>
            )}
            <button className="icon-btn ghost sm" onClick={copy} title="Copy answer">
              {copied ? <Check size={13} /> : <Copy size={13} />}
            </button>
            {onFeedback && message.id && !String(message.id).startsWith("tmp") && (
              <>
                <button
                  className={classNames("icon-btn ghost sm", message.feedback === 1 && "on-good")}
                  onClick={() => onFeedback(message, message.feedback === 1 ? 0 : 1)}
                  title="Helpful"
                >
                  <ThumbsUp size={13} />
                </button>
                <button
                  className={classNames("icon-btn ghost sm", message.feedback === -1 && "on-bad")}
                  onClick={() => onFeedback(message, message.feedback === -1 ? 0 : -1)}
                  title="Not helpful"
                >
                  <ThumbsDown size={13} />
                </button>
              </>
            )}
            {message.latency_ms && <span className="msg-latency">{(message.latency_ms / 1000).toFixed(1)}s</span>}
          </div>
        )}
      </div>
    </div>
  );
}
