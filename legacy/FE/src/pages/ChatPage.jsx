import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Sparkles } from "lucide-react";

import ChatComposer from "../components/ChatComposer";
import ChatTranscript from "../components/ChatTranscript";
import { sampleQuestions } from "../lib/chat";

function ChatPage({
  activeProviderName,
  canSend,
  chatProvider,
  error,
  isProviderBlocked,
  isStreaming,
  messages,
  onNavigateToDocuments,
  onProviderChange,
  onQuestionChange,
  onRetrievalModeChange,
  onRerankStrategyChange,
  onResponseModeChange,
  onStopStreaming,
  onSubmit,
  onTopKChange,
  onUseAllDocuments,
  providerStatus,
  question,
  retrievalMode,
  retrievalModeOptions,
  rerankStrategy,
  rerankStrategyOptions,
  responseMode,
  selectedDocumentSummary,
  selectedProviderInfo,
  status,
  topK,
}) {
  const hasConversationStarted = messages.some((message) => message.role === "user");
  const [showQuickPrompts, setShowQuickPrompts] = useState(true);
  const promptsAutoCollapsedRef = useRef(false);
  const shouldReduceMotion = useReducedMotion();

  useEffect(() => {
    if (hasConversationStarted && !promptsAutoCollapsedRef.current) {
      setShowQuickPrompts(false);
      promptsAutoCollapsedRef.current = true;
      return;
    }

    if (!hasConversationStarted) {
      setShowQuickPrompts(true);
      promptsAutoCollapsedRef.current = false;
    }
  }, [hasConversationStarted]);

  return (
    <div className="page-stack">
      <section className="page-hero surface-card">
        <p className="eyebrow">Grounded Chat</p>
        <h2>Chat with your documents</h2>
        <p className="hero-copy">
          Keep the chat page focused, choose a document only when you need tighter retrieval, and
          let the message metadata show where each answer came from.
        </p>
        <p className="page-status-text">
          Status: {status}
          {" | "}
          Scope: {selectedDocumentSummary ? selectedDocumentSummary.filename : "All documents"}
          {" | "}
          Provider: {activeProviderName}
          {providerStatus ? "" : " (checking...)"}
        </p>

        <div className="hero-actions">
          <button
            type="button"
            className="ghost-button ghost-button-inline"
            onClick={onNavigateToDocuments}
          >
            {selectedDocumentSummary ? "Change document scope" : "Open documents"}
          </button>
          <button type="button" className="secondary-button" onClick={onUseAllDocuments}>
            Use all documents
          </button>
          <button
            type="button"
            className="ghost-button ghost-button-inline"
            onClick={() => setShowQuickPrompts((current) => !current)}
            aria-expanded={showQuickPrompts}
          >
            {showQuickPrompts ? "Hide sample questions" : "Show sample questions"}
          </button>
        </div>

        <AnimatePresence initial={false}>
          {showQuickPrompts ? (
            <motion.div
              className="quick-prompts-panel"
              initial={shouldReduceMotion ? false : { opacity: 0, height: 0, y: -6 }}
              animate={shouldReduceMotion ? {} : { opacity: 1, height: "auto", y: 0 }}
              exit={shouldReduceMotion ? {} : { opacity: 0, height: 0, y: -6 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
            >
              <p className="quick-prompts-help">
                Upload relevant documents first, then try these examples to get grounded answers.
              </p>

              <div className="quick-prompts">
                {sampleQuestions.map((sample) => (
                  <button
                    key={sample}
                    type="button"
                    className="quick-prompt"
                    onClick={() => onQuestionChange(sample)}
                    disabled={isStreaming}
                  >
                    <Sparkles size={15} />
                    {sample}
                  </button>
                ))}
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </section>

      <section className="chat-page-shell surface-card">
        <div className="section-heading section-heading-spread page-section-header">
          <div>
            <p className="section-kicker">Conversation</p>
            <h3>Retrieval-aware chat</h3>
          </div>
        </div>

        <ChatTranscript messages={messages} />

        <ChatComposer
          canSend={canSend}
          chatProvider={chatProvider}
          error={error}
          isProviderBlocked={isProviderBlocked}
          isStreaming={isStreaming}
          onOpenDocuments={onNavigateToDocuments}
          onProviderChange={onProviderChange}
          onQuestionChange={onQuestionChange}
          onRetrievalModeChange={onRetrievalModeChange}
          onRerankStrategyChange={onRerankStrategyChange}
          onResponseModeChange={onResponseModeChange}
          onStopStreaming={onStopStreaming}
          onSubmit={onSubmit}
          onTopKChange={onTopKChange}
          question={question}
          retrievalMode={retrievalMode}
          retrievalModeOptions={retrievalModeOptions}
          rerankStrategy={rerankStrategy}
          rerankStrategyOptions={rerankStrategyOptions}
          responseMode={responseMode}
          selectedDocumentSummary={selectedDocumentSummary}
          selectedProviderInfo={selectedProviderInfo}
          topK={topK}
        />
      </section>
    </div>
  );
}

export default ChatPage;
