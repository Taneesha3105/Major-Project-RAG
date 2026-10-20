import { useEffect, useMemo, useRef } from "react";
import { motion } from "framer-motion";
import { Bot, Clock3, FileStack, Sparkles, UserRound } from "lucide-react";

import {
  formatLatency,
  formatRerankStrategyLabel,
  formatRetrievalModeLabel,
  formatSimilarity,
  formatTime,
} from "../lib/chat";

function MessageMetadata({ meta }) {
  if (!meta) {
    return null;
  }

  const totalLatency = meta.latency?.total_ms;
  const retrievalLatency = meta.latency?.retrieval?.total_ms;
  const rerankLatency = meta.latency?.rerank_ms;
  const generationLatency = meta.latency?.llm_generation_ms;
  const preparationLatency = meta.latency?.preparation_ms;
  const streamFirstChunkLatency = meta.latency?.stream_first_chunk_ms;
  const streamTotalLatency = meta.latency?.stream_total_ms;
  const sourceRefs = meta.context_refs || [];
  const providerUsed = meta.provider_used !== false;
  const answerPath = meta.answer_path || "llm";
  const retrievalMode = meta.retrieval_mode;
  const rerankStrategy = meta.rerank_strategy;
  const rerankFallbackUsed = meta.rerank_fallback_used === true;

  function getRerankLabel() {
    if (!rerankStrategy) {
      return null;
    }

    const baseLabel = `Rerank ${formatRerankStrategyLabel(rerankStrategy)}`;
    if (rerankFallbackUsed) {
      return `${baseLabel} -> custom fallback`;
    }
    return baseLabel;
  }

  function getRetrievalLabel() {
    if (!retrievalMode) {
      return null;
    }

    return `Retrieval ${formatRetrievalModeLabel(retrievalMode)}`;
  }

  function getAnswerOriginLabel() {
    if (providerUsed) {
      return meta.provider;
    }

    if (answerPath === "composer") {
      return "Local composer";
    }

    if (answerPath === "clarify") {
      return "Clarification";
    }

    return "No provider call";
  }

  function MetaChip({ children, className = "", icon: Icon }) {
    const classes = ["meta-chip", className].filter(Boolean).join(" ");
    return (
      <span className={classes}>
        <Icon size={14} />
        {children}
      </span>
    );
  }

  return (
    <div className="message-support">
      <div className="message-metrics">
        {getAnswerOriginLabel() ? (
          <MetaChip className="chip-model" icon={Sparkles}>
            {getAnswerOriginLabel()}
          </MetaChip>
        ) : null}
        {!providerUsed && meta.provider ? (
          <MetaChip className="chip-model" icon={Sparkles}>
            Selected {meta.provider}
          </MetaChip>
        ) : null}
        {typeof meta.context_count === "number" ? (
          <MetaChip className="chip-source-count" icon={FileStack}>
            {meta.context_count} source{meta.context_count === 1 ? "" : "s"}
          </MetaChip>
        ) : null}
        {getRerankLabel() ? (
          <MetaChip className="chip-strategy" icon={Sparkles}>
            {getRerankLabel()}
          </MetaChip>
        ) : null}
        {getRetrievalLabel() ? (
          <MetaChip className="chip-strategy" icon={Sparkles}>
            {getRetrievalLabel()}
          </MetaChip>
        ) : null}
        {totalLatency ? (
          <MetaChip className="chip-latency" icon={Clock3}>
            Total {formatLatency(totalLatency)}
          </MetaChip>
        ) : null}
        {retrievalLatency ? (
          <MetaChip className="chip-latency" icon={Clock3}>
            Retrieval {formatLatency(retrievalLatency)}
          </MetaChip>
        ) : null}
        {rerankLatency ? (
          <MetaChip className="chip-latency" icon={Clock3}>
            Rerank {formatLatency(rerankLatency)}
          </MetaChip>
        ) : null}
        {preparationLatency ? (
          <MetaChip className="chip-latency" icon={Clock3}>
            Prep {formatLatency(preparationLatency)}
          </MetaChip>
        ) : null}
        {streamFirstChunkLatency ? (
          <MetaChip className="chip-latency" icon={Clock3}>
            First chunk {formatLatency(streamFirstChunkLatency)}
          </MetaChip>
        ) : null}
        {streamTotalLatency ? (
          <MetaChip className="chip-latency" icon={Clock3}>
            Stream total {formatLatency(streamTotalLatency)}
          </MetaChip>
        ) : null}
        {generationLatency ? (
          <MetaChip className="chip-latency" icon={Clock3}>
            Generation {formatLatency(generationLatency)}
          </MetaChip>
        ) : null}
      </div>

      {sourceRefs.length > 0 ? (
        <div className="source-list">
          {sourceRefs.map((ref) => (
            <span key={`${ref.chunk_id}-${ref.chunk_index}`} className="source-chip">
              <span className="source-chip-file">{ref.filename}</span>
              <span className="source-chip-detail">Chunk {ref.chunk_index}</span>
              {formatSimilarity(ref.similarity_score) ? (
                <span className="source-chip-detail chip-score">
                  Score {formatSimilarity(ref.similarity_score)}
                </span>
              ) : null}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function TypingIndicator() {
  return (
    <span className="typing-indicator" aria-label="Assistant is responding">
      <span />
      <span />
      <span />
    </span>
  );
}

function ChatTranscript({ messages }) {
  const shouldStickToBottomRef = useRef(true);
  const latestMessage = messages[messages.length - 1] || null;

  const latestMessageSignature = useMemo(() => {
    if (!latestMessage) {
      return "empty";
    }

    return `${latestMessage.id}:${latestMessage.content.length}:${latestMessage.isStreaming}:${latestMessage.isLoading}`;
  }, [messages]);

  function updateScrollState() {
    const scrollTop = window.scrollY || window.pageYOffset || 0;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    const scrollHeight = Math.max(
      document.documentElement.scrollHeight,
      document.body.scrollHeight,
    );
    const nextCanScroll = scrollHeight > viewportHeight + 120;
    const nextNearBottom = scrollHeight - scrollTop - viewportHeight < 120;
    shouldStickToBottomRef.current = !nextCanScroll || nextNearBottom;
  }

  useEffect(() => {
    updateScrollState();

    function handleWindowChange() {
      updateScrollState();
    }

    window.addEventListener("scroll", handleWindowChange, { passive: true });
    window.addEventListener("resize", handleWindowChange);

    return () => {
      window.removeEventListener("scroll", handleWindowChange);
      window.removeEventListener("resize", handleWindowChange);
    };
  }, []);

  useEffect(() => {
    updateScrollState();

    if (shouldStickToBottomRef.current) {
      scrollToLatest(latestMessage?.isStreaming || latestMessage?.isLoading ? "auto" : "smooth");
    }
  }, [latestMessage, latestMessageSignature]);

  function scrollToLatest(behavior = "smooth") {
    const scrollHeight = Math.max(
      document.documentElement.scrollHeight,
      document.body.scrollHeight,
    );

    window.scrollTo({ top: scrollHeight, behavior });
  }

  return (
    <section className="messages-panel" aria-label="Conversation">
      <div className="messages-scroll" role="log" aria-live="polite">
        {messages.map((message, index) => {
          const isAssistant = message.role === "assistant";
          const showWaitingState = Boolean(message.isLoading && !message.content);
          const showStreamingState = Boolean(message.isStreaming);

          return (
            <motion.article
              key={message.id}
              className={`message-card message-${message.role}`}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                duration: 0.22,
                ease: "easeOut",
                delay: index > messages.length - 3 ? 0.03 : 0,
              }}
            >
              <div className="message-header">
                <div className="message-author">
                  <span
                    className={`message-avatar ${
                      isAssistant ? "message-avatar-assistant" : "message-avatar-user"
                    }`}
                  >
                    {isAssistant ? <Bot size={16} /> : <UserRound size={16} />}
                  </span>
                  <div>
                    <strong>{isAssistant ? "Assistant" : "You"}</strong>
                    <span>{formatTime(message.createdAt)}</span>
                  </div>
                </div>

                {showStreamingState ? (
                  <span className="stream-badge" aria-label="Streaming response in progress">
                    <span className="stream-badge-dot" />
                    Streaming
                  </span>
                ) : null}
              </div>

              {showWaitingState ? (
                <div className="message-content message-content-waiting">
                  <TypingIndicator />
                  {showStreamingState ? (
                    <span className="typing-text">Retrieving context and streaming a response...</span>
                  ) : null}
                </div>
              ) : (
                <p className="message-content">{message.content || "..."}</p>
              )}
              <MessageMetadata meta={message.meta} />
            </motion.article>
          );
        })}
      </div>
    </section>
  );
}

export default ChatTranscript;
