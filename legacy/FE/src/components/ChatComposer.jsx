import { useEffect, useId, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  Check,
  ChevronDown,
  Files,
  Minus,
  Plus,
  SendHorizontal,
  SlidersHorizontal,
  Sparkles,
  Square,
} from "lucide-react";

import { providerOptions, responseModeOptions } from "../lib/chat";

function clampTopK(value) {
  const numericValue = Number(value);

  if (Number.isNaN(numericValue)) {
    return 1;
  }

  return Math.min(10, Math.max(1, numericValue));
}

function CustomSelect({ label, onChange, options, shouldReduceMotion, value }) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef(null);
  const selectedOption =
    options.find((option) => String(option.value) === String(value)) || options[0];

  useEffect(() => {
    function handleOutsideClick(event) {
      if (!containerRef.current?.contains(event.target)) {
        setIsOpen(false);
      }
    }

    function handleEscape(event) {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    }

    document.addEventListener("mousedown", handleOutsideClick);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
      document.removeEventListener("keydown", handleEscape);
    };
  }, []);

  function handleSelect(nextValue) {
    onChange(nextValue);
    setIsOpen(false);
  }

  return (
    <label className="field field-select">
      <span>{label}</span>
      <div
        ref={containerRef}
        className={`custom-select ${isOpen ? "custom-select-open" : ""}`}
      >
        <button
          type="button"
          className="custom-select-trigger"
          aria-expanded={isOpen}
          aria-haspopup="listbox"
          onClick={() => setIsOpen((current) => !current)}
        >
          <span className="custom-select-value">{selectedOption?.label}</span>
          <ChevronDown size={18} className="custom-select-chevron" />
        </button>

        <AnimatePresence initial={false}>
          {isOpen ? (
            <motion.div
              className="custom-select-menu"
              role="listbox"
              initial={shouldReduceMotion ? false : { opacity: 0, y: -6, scale: 0.98 }}
              animate={shouldReduceMotion ? {} : { opacity: 1, y: 0, scale: 1 }}
              exit={shouldReduceMotion ? {} : { opacity: 0, y: -4, scale: 0.98 }}
              transition={{ duration: 0.16, ease: "easeOut" }}
            >
              {options.map((option) => {
                const isSelected = String(option.value) === String(value);

                return (
                  <button
                    key={option.value}
                    type="button"
                    className={`custom-select-option ${
                      isSelected ? "custom-select-option-selected" : ""
                    }`}
                    role="option"
                    aria-selected={isSelected}
                    disabled={option.disabled}
                    onClick={() => handleSelect(option.value)}
                  >
                    <span>{option.label}</span>
                    {isSelected ? <Check size={16} /> : null}
                  </button>
                );
              })}
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </label>
  );
}

function TopKCounter({ onChange, value }) {
  const safeValue = clampTopK(value);
  const [isInputFocused, setIsInputFocused] = useState(false);
  const labelId = useId();

  function updateValue(nextValue) {
    onChange(String(clampTopK(nextValue)));
  }

  return (
    <div className="field">
      <span id={labelId}>Top K</span>
      <div className={`topk-stepper ${isInputFocused ? "topk-stepper-input-focused" : ""}`}>
        <button
          type="button"
          className="topk-stepper-button topk-stepper-button-decrement"
          onClick={() => updateValue(safeValue - 1)}
          disabled={safeValue <= 1}
          aria-label="Decrease Top K"
        >
          <Minus size={16} />
        </button>

        <div className="topk-stepper-value">
          <input
            className="topk-stepper-input"
            type="number"
            min="1"
            max="10"
            inputMode="numeric"
            value={safeValue}
            aria-labelledby={labelId}
            onChange={(event) => updateValue(event.target.value)}
            onFocus={() => setIsInputFocused(true)}
            onBlur={() => setIsInputFocused(false)}
          />
        </div>

        <button
          type="button"
          className="topk-stepper-button topk-stepper-button-increment"
          onClick={() => updateValue(safeValue + 1)}
          disabled={safeValue >= 10}
          aria-label="Increase Top K"
        >
          <Plus size={16} />
        </button>
      </div>
    </div>
  );
}

function ChatComposer({
  canSend,
  chatProvider,
  error,
  isProviderBlocked,
  isStreaming,
  onOpenDocuments,
  onProviderChange,
  onQuestionChange,
  onRetrievalModeChange,
  onRerankStrategyChange,
  onResponseModeChange,
  onStopStreaming,
  onSubmit,
  onTopKChange,
  question,
  retrievalMode,
  rerankStrategy,
  rerankStrategyOptions,
  retrievalModeOptions,
  responseMode,
  selectedDocumentSummary,
  selectedProviderInfo,
  topK,
}) {
  const shouldReduceMotion = useReducedMotion();
  const [showAdvanced, setShowAdvanced] = useState(false);

  function handleQuestionKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit(event);
    }
  }

  return (
    <form className="composer-card" onSubmit={onSubmit}>
      <div className="composer-header">
        <div>
          <p className="section-kicker">Compose</p>
          <h3>Ask the knowledge base a grounded question.</h3>
        </div>

        <button type="button" className="scope-button" onClick={onOpenDocuments}>
          <Files size={16} />
          {selectedDocumentSummary ? selectedDocumentSummary.filename : "All documents"}
        </button>
      </div>

      <label className="field">
        <span>Question</span>
        <div className="textarea-shell">
          <textarea
            rows="5"
            value={question}
            onChange={(event) => onQuestionChange(event.target.value)}
            onKeyDown={handleQuestionKeyDown}
            placeholder="Ask about implementation details, architecture decisions, or facts grounded in your uploaded documents..."
          />
          <div className="textarea-meta">
            <span>
              Scope: {selectedDocumentSummary ? selectedDocumentSummary.filename : "All documents"}
            </span>
            <span>{question.trim().length} characters</span>
          </div>
        </div>
      </label>

      <div className="composer-toolbar">
        <button
          type="button"
          className="ghost-button ghost-button-inline"
          onClick={() => setShowAdvanced((current) => !current)}
          aria-expanded={showAdvanced}
        >
          <SlidersHorizontal size={16} />
          Advanced controls
        </button>
        <span className="composer-hint">Press Enter to send, Shift + Enter for a new line</span>
      </div>

      <AnimatePresence initial={false}>
        {showAdvanced ? (
          <motion.div
            className="advanced-panel"
            initial={shouldReduceMotion ? false : { opacity: 0, height: 0 }}
            animate={shouldReduceMotion ? {} : { opacity: 1, height: "auto" }}
            exit={shouldReduceMotion ? {} : { opacity: 0, height: 0 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
          >
            <div className="advanced-grid">
              <CustomSelect
                label="Chat Provider"
                options={providerOptions}
                shouldReduceMotion={shouldReduceMotion}
                value={chatProvider}
                onChange={onProviderChange}
              />

              <CustomSelect
                label="Response Mode"
                options={responseModeOptions}
                shouldReduceMotion={shouldReduceMotion}
                value={responseMode}
                onChange={onResponseModeChange}
              />

              <CustomSelect
                label="Retrieval Mode"
                options={retrievalModeOptions}
                shouldReduceMotion={shouldReduceMotion}
                value={retrievalMode}
                onChange={onRetrievalModeChange}
              />

              <CustomSelect
                label="Rerank Mode"
                options={rerankStrategyOptions}
                shouldReduceMotion={shouldReduceMotion}
                value={rerankStrategy}
                onChange={onRerankStrategyChange}
              />

              <TopKCounter value={topK} onChange={onTopKChange} />
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      {error ? <p className="error-banner">{error}</p> : null}
      {isProviderBlocked && selectedProviderInfo ? (
        <p className="warning-banner">
          <Sparkles size={16} />
          {selectedProviderInfo.missing_message}
        </p>
      ) : null}

      <div className="composer-actions">
        <button type="submit" className="primary-button" disabled={!canSend || isProviderBlocked}>
          <SendHorizontal size={16} />
          {responseMode === "stream" ? "Send with stream" : "Send response"}
        </button>
        <button
          type="button"
          className="secondary-button"
          disabled={!isStreaming || responseMode !== "stream"}
          onClick={onStopStreaming}
        >
          <Square size={16} />
          Stop stream
        </button>
      </div>
    </form>
  );
}

export default ChatComposer;
