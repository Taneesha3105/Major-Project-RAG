import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import ScrollJumpControls from "./components/ScrollJumpControls";
import WorkspaceHeader from "./components/WorkspaceHeader";
import { useThemePreference } from "./hooks/useThemePreference";
import {
  createMessage,
  defaultTopK,
  readErrorMessage,
  rerankStrategyOptions as baseRerankStrategyOptions,
  retrievalModeOptions as baseRetrievalModeOptions,
} from "./lib/chat";
import ChatPage from "./pages/ChatPage";
import DocumentsPage from "./pages/DocumentsPage";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;

function normalizePath(pathname) {
  if (pathname === "/" || pathname === "" || pathname === "/chat") {
    return "/chat";
  }

  if (pathname === "/documents") {
    return "/documents";
  }

  return "/chat";
}

function mergeMessageLatency(message, latencyPatch) {
  return {
    ...message,
    meta: {
      ...(message.meta || {}),
      latency: {
        ...(message.meta?.latency || {}),
        ...latencyPatch,
      },
    },
  };
}

function AppRouter() {
  const [currentPath, setCurrentPath] = useState(() => normalizePath(window.location.pathname));
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const [selectedDocumentDetail, setSelectedDocumentDetail] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [documentsError, setDocumentsError] = useState("");
  const [documentNotice, setDocumentNotice] = useState("All documents are selected for chat.");
  const [uploadFile, setUploadFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [deletingDocumentId, setDeletingDocumentId] = useState(null);
  const [providerStatus, setProviderStatus] = useState(null);
  const [messages, setMessages] = useState(() => [
    createMessage(
      "assistant",
      "Ask a grounded question across all documents or first choose a document from the Documents page for tighter retrieval.",
    ),
  ]);
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(defaultTopK);
  const [chatProvider, setChatProvider] = useState("default");
  const [retrievalMode, setRetrievalMode] = useState("default");
  const [rerankStrategy, setRerankStrategy] = useState("default");
  const [responseMode, setResponseMode] = useState("stream");
  const [isStreaming, setIsStreaming] = useState(false);
  const [status, setStatus] = useState("Ready");
  const [error, setError] = useState("");
  const abortControllerRef = useRef(null);
  const uploadInputRef = useRef(null);
  const { resolvedTheme, toggleTheme } = useThemePreference();

  const selectedDocumentSummary = useMemo(
    () => documents.find((document) => String(document.id) === selectedDocumentId) || null,
    [documents, selectedDocumentId],
  );
  const selectedProviderInfo = useMemo(() => {
    if (!providerStatus) {
      return null;
    }

    const effectiveProvider =
      chatProvider === "default" ? providerStatus.defaults.chat_provider : chatProvider;

    return (
      providerStatus.chat_providers.find((provider) => provider.name === effectiveProvider) || null
    );
  }, [chatProvider, providerStatus]);
  const rerankStrategyOptions = useMemo(() => {
    const availableStrategies = new Set(providerStatus?.reranker?.available_strategies || ["fast"]);
    return baseRerankStrategyOptions.map((option) => {
      if (option.value === "default" || availableStrategies.has(option.value)) {
        return option;
      }
      return {
        ...option,
        disabled: true,
        label: `${option.label} (Unavailable)`,
      };
    });
  }, [providerStatus]);
  const retrievalModeOptions = useMemo(() => {
    return baseRetrievalModeOptions;
  }, []);
  const activeProviderName =
    selectedProviderInfo?.name ||
    (providerStatus ? providerStatus.defaults.chat_provider : "Checking provider status");
  const canSend = question.trim().length > 0 && !isStreaming;
  const isProviderBlocked = Boolean(selectedProviderInfo && !selectedProviderInfo.configured);

  useEffect(() => {
    const nextPath = normalizePath(window.location.pathname);

    if (nextPath !== window.location.pathname) {
      window.history.replaceState({}, "", nextPath);
    }

    function handlePopState() {
      setCurrentPath(normalizePath(window.location.pathname));
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (rerankStrategy === "default") {
      return;
    }

    const availableStrategies = new Set(providerStatus?.reranker?.available_strategies || ["fast"]);
    if (!availableStrategies.has(rerankStrategy)) {
      setRerankStrategy("default");
    }
  }, [providerStatus, rerankStrategy]);

  useEffect(() => {
    let ignore = false;

    async function loadProviderStatus() {
      try {
        const response = await fetch(`${apiBaseUrl}/providers/status`);

        if (!response.ok) {
          return;
        }

        const data = await response.json();
        if (!ignore) {
          setProviderStatus(data);
        }
      } catch {
        if (!ignore) {
          setProviderStatus(null);
        }
      }
    }

    loadProviderStatus();

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    void loadDocuments();
  }, []);

  function navigateTo(path) {
    const nextPath = normalizePath(path);

    if (nextPath === currentPath) {
      return;
    }

    window.history.pushState({}, "", nextPath);
    setCurrentPath(nextPath);
  }

  async function loadDocuments(nextSelectedDocumentId = selectedDocumentId) {
    setDocumentsLoading(true);
    setDocumentsError("");

    try {
      const response = await fetch(`${apiBaseUrl}/documents`);
      if (!response.ok) {
        const detail = await readErrorMessage(response);
        throw new Error(detail || "Unable to load documents.");
      }

      const data = await response.json();
      const nextDocuments = data.documents || [];
      const hasSelectedDocument = nextSelectedDocumentId
        ? nextDocuments.some((document) => String(document.id) === String(nextSelectedDocumentId))
        : false;

      setDocuments(nextDocuments);

      if (nextSelectedDocumentId && !hasSelectedDocument) {
        setSelectedDocumentId("");
        setSelectedDocumentDetail(null);
      } else if (nextSelectedDocumentId && hasSelectedDocument) {
        await loadDocumentDetail(nextSelectedDocumentId);
      }
    } catch (loadError) {
      setDocuments([]);
      setDocumentsError(loadError.message || "Unable to load documents.");
    } finally {
      setDocumentsLoading(false);
    }
  }

  async function loadDocumentDetail(documentId) {
    try {
      const response = await fetch(`${apiBaseUrl}/documents/${documentId}`);

      if (!response.ok) {
        const detail = await readErrorMessage(response);
        throw new Error(detail || "Unable to load document details.");
      }

      const data = await response.json();
      setSelectedDocumentDetail(data);
    } catch (detailError) {
      setSelectedDocumentDetail(null);
      setDocumentsError(detailError.message || "Unable to load document details.");
    }
  }

  async function handleDocumentUpload(event) {
    event.preventDefault();
    if (!uploadFile || isUploading) {
      return;
    }

    setIsUploading(true);
    setDocumentsError("");
    setDocumentNotice("Uploading document...");

    const formData = new FormData();
    formData.append("file", uploadFile);

    try {
      const response = await fetch(`${apiBaseUrl}/documents/ingest/file`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const detail = await readErrorMessage(response);
        throw new Error(detail || "Unable to upload the document.");
      }

      const data = await response.json();
      const nextDocumentId = String(data.document_id);

      setUploadFile(null);
      if (uploadInputRef.current) {
        uploadInputRef.current.value = "";
      }

      setSelectedDocumentId(nextDocumentId);
      setDocumentNotice(data.message);
      await loadDocuments(nextDocumentId);
    } catch (uploadError) {
      setDocumentsError(uploadError.message || "Unable to upload the document.");
      setDocumentNotice("Upload failed.");
    } finally {
      setIsUploading(false);
    }
  }

  async function handleDeleteDocument(document) {
    if (
      deletingDocumentId ||
      !window.confirm(`Delete "${document.filename}" and all of its chunks?`)
    ) {
      return;
    }

    setDeletingDocumentId(document.id);
    setDocumentsError("");

    try {
      const response = await fetch(`${apiBaseUrl}/documents/${document.id}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        const detail = await readErrorMessage(response);
        throw new Error(detail || "Unable to delete the document.");
      }

      const data = await response.json();
      const nextSelectedDocumentId =
        String(document.id) === selectedDocumentId ? "" : selectedDocumentId;

      if (!nextSelectedDocumentId) {
        setSelectedDocumentId("");
        setSelectedDocumentDetail(null);
        setDocumentNotice("All documents are selected for chat.");
      } else {
        setDocumentNotice(data.message);
      }

      await loadDocuments(nextSelectedDocumentId);
    } catch (deleteError) {
      setDocumentsError(deleteError.message || "Unable to delete the document.");
    } finally {
      setDeletingDocumentId(null);
    }
  }

  function handleDocumentSelection(nextDocumentId) {
    setSelectedDocumentId(nextDocumentId);
    setDocumentsError("");

    if (!nextDocumentId) {
      setSelectedDocumentDetail(null);
      setDocumentNotice("All documents are selected for chat.");
      return;
    }

    const nextDocument = documents.find((document) => String(document.id) === nextDocumentId);
    if (nextDocument) {
      setDocumentNotice(`Selected "${nextDocument.filename}" for chat.`);
    }

    void loadDocumentDetail(nextDocumentId);
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!canSend) {
      return;
    }

    if (isProviderBlocked && selectedProviderInfo) {
      setError(selectedProviderInfo.missing_message || "The selected provider is not configured.");
      setStatus("Provider not configured");
      return;
    }

    const trimmedQuestion = question.trim();
    const payload = {
      question: trimmedQuestion,
      top_k: Number(topK),
    };

    if (selectedDocumentId) {
      payload.document_id = Number(selectedDocumentId);
    }

    if (chatProvider !== "default") {
      payload.provider = chatProvider;
    }
    if (rerankStrategy !== "default") {
      payload.rerank_strategy = rerankStrategy;
    }
    if (retrievalMode !== "default") {
      payload.retrieval_mode = retrievalMode;
    }

    const userMessage = createMessage("user", trimmedQuestion);
    const assistantMessage = createMessage("assistant", "", {
      isStreaming: responseMode === "stream",
      isLoading: true,
      meta: null,
    });

    setMessages((current) => [...current, userMessage, assistantMessage]);
    setQuestion("");
    setError("");
    setStatus(responseMode === "stream" ? "Connecting to stream..." : "Generating answer...");
    setIsStreaming(responseMode === "stream");

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      const requestStartedAt = performance.now();

      if (responseMode === "stream") {
        const response = await fetch(`${apiBaseUrl}/chat/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
          signal: abortController.signal,
        });

        if (!response.ok || !response.body) {
          const detail = await readErrorMessage(response);
          throw new Error(detail || "Unable to start the streaming response.");
        }

        setStatus("Streaming answer...");
        await consumeStream(response.body, assistantMessage.id, requestStartedAt);
        setStatus("Stream complete");
      } else {
        const response = await fetch(`${apiBaseUrl}/chat/ask`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(payload),
          signal: abortController.signal,
        });

        if (!response.ok) {
          const detail = await readErrorMessage(response);
          throw new Error(detail || "Unable to generate the answer.");
        }

        const data = await response.json();
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantMessage.id
              ? {
                  ...message,
                  content: data.answer,
                  isStreaming: false,
                  isLoading: false,
                  meta: {
                    provider: data.provider,
                    provider_used: data.provider_used,
                    answer_path: data.answer_path,
                    retrieval_mode: data.retrieval_mode,
                    rerank_strategy: data.rerank_strategy,
                    rerank_fallback_used: data.rerank_fallback_used,
                    context_count: data.context_count,
                    context_refs: data.context_refs,
                    latency: data.latency,
                  },
                }
              : message,
          ),
        );
        setStatus("Answer ready");
      }
    } catch (streamError) {
      if (streamError.name === "AbortError") {
        setStatus("Streaming stopped");
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantMessage.id
              ? {
                  ...message,
                  isStreaming: false,
                  isLoading: false,
                  content: message.content || "Streaming stopped before a full answer was returned.",
                }
              : message,
          ),
        );
      } else {
        setError(streamError.message || "Something went wrong while generating the answer.");
        setStatus("Stream failed");
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantMessage.id
              ? {
                  ...message,
                  isStreaming: false,
                  isLoading: false,
                  content:
                    message.content ||
                    "I could not complete the response. Check the backend and try again.",
                }
              : message,
          ),
        );
      }
    } finally {
      abortControllerRef.current = null;
      setIsStreaming(false);
    }
  }

  async function consumeStream(stream, assistantMessageId, startedAt) {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let firstChunkMs = null;
    const pendingStreamUpdate = {
      delta: "",
      meta: null,
      latencyPatch: {},
      frameId: null,
    };

    function flushPendingStreamUpdate() {
      const nextDelta = pendingStreamUpdate.delta;
      const nextMeta = pendingStreamUpdate.meta;
      const nextLatencyPatch = pendingStreamUpdate.latencyPatch;
      const hasLatencyPatch = Object.keys(nextLatencyPatch).length > 0;

      if (!nextDelta && !nextMeta && !hasLatencyPatch) {
        return;
      }

      pendingStreamUpdate.delta = "";
      pendingStreamUpdate.meta = null;
      pendingStreamUpdate.latencyPatch = {};

      setMessages((current) =>
        current.map((message) => {
          if (message.id !== assistantMessageId) {
            return message;
          }

          let nextMessage = message;

          if (nextMeta) {
            nextMessage = {
              ...nextMessage,
              meta: {
                ...(nextMessage.meta || {}),
                ...nextMeta,
                latency: {
                  ...(nextMessage.meta?.latency || {}),
                  ...(nextMeta.latency || {}),
                },
              },
            };
          }

          if (hasLatencyPatch) {
            nextMessage = mergeMessageLatency(nextMessage, nextLatencyPatch);
          }

          if (nextDelta) {
            nextMessage = {
              ...nextMessage,
              isLoading: false,
              content: `${nextMessage.content}${nextDelta}`,
            };
          }

          return nextMessage;
        }),
      );
    }

    function scheduleStreamUpdate() {
      if (pendingStreamUpdate.frameId !== null) {
        return;
      }

      pendingStreamUpdate.frameId = window.requestAnimationFrame(() => {
        pendingStreamUpdate.frameId = null;
        flushPendingStreamUpdate();
      });
    }

    while (true) {
      const { done, value } = await reader.read();

      if (done) {
        if (buffer.trim()) {
          firstChunkMs = processEvents(
            buffer,
            assistantMessageId,
            startedAt,
            firstChunkMs,
            pendingStreamUpdate,
            scheduleStreamUpdate,
          );
        }
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";

      for (const eventBlock of events) {
        firstChunkMs = processEvents(
          eventBlock,
          assistantMessageId,
          startedAt,
          firstChunkMs,
          pendingStreamUpdate,
          scheduleStreamUpdate,
        );
      }
    }

    if (pendingStreamUpdate.frameId !== null) {
      window.cancelAnimationFrame(pendingStreamUpdate.frameId);
      pendingStreamUpdate.frameId = null;
    }
    flushPendingStreamUpdate();

    const streamTotalMs = Math.round(performance.now() - startedAt);

    setMessages((current) =>
      current.map((message) =>
        message.id === assistantMessageId
          ? {
              ...mergeMessageLatency(message, {
                stream_total_ms: streamTotalMs,
                ...(firstChunkMs !== null ? { stream_first_chunk_ms: firstChunkMs } : {}),
              }),
              isStreaming: false,
              isLoading: false,
            }
          : message,
      ),
      );
  }

  function processEvents(
    eventBlock,
    assistantMessageId,
    startedAt,
    firstChunkMs,
    pendingStreamUpdate,
    scheduleStreamUpdate,
  ) {
    const lines = eventBlock.split("\n").filter(Boolean);
    let eventName = "message";
    const dataLines = [];

    for (const line of lines) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      }

      if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }

    if (dataLines.length === 0) {
      return firstChunkMs;
    }

    const payload = JSON.parse(dataLines.join("\n"));

    if (eventName === "metadata") {
      pendingStreamUpdate.meta = {
        ...(pendingStreamUpdate.meta || {}),
        ...payload,
        latency: {
          ...(pendingStreamUpdate.meta?.latency || {}),
          ...(payload.latency || {}),
        },
      };
      scheduleStreamUpdate();
      return firstChunkMs;
    }

    if (eventName === "chunk") {
      const nextFirstChunkMs =
        firstChunkMs === null ? Math.round(performance.now() - startedAt) : firstChunkMs;
      pendingStreamUpdate.delta += payload.delta;

      if (firstChunkMs === null) {
        pendingStreamUpdate.latencyPatch = {
          ...pendingStreamUpdate.latencyPatch,
          stream_first_chunk_ms: nextFirstChunkMs,
        };
      }

      scheduleStreamUpdate();
      return nextFirstChunkMs;
    }

    if (eventName === "done") {
      setStatus(payload.message || "Stream complete");
    }

    return firstChunkMs;
  }

  function stopStreaming() {
    abortControllerRef.current?.abort();
  }

  return (
    <main className="app-shell">
      <div className="ambient-glow ambient-glow-left" />
      <div className="ambient-glow ambient-glow-right" />

      <div className="workspace-shell">
        <WorkspaceHeader
          currentPath={currentPath}
          onNavigate={navigateTo}
          onToggleTheme={toggleTheme}
          resolvedTheme={resolvedTheme}
        />

        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={currentPath}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
          >
            {currentPath === "/documents" ? (
              <DocumentsPage
                deletingDocumentId={deletingDocumentId}
                documentNotice={documentNotice}
                documents={documents}
                documentsError={documentsError}
                documentsLoading={documentsLoading}
                isUploading={isUploading}
                onDeleteDocument={handleDeleteDocument}
                onNavigateToChat={() => navigateTo("/chat")}
                onRefresh={() => loadDocuments()}
                onSelectDocument={handleDocumentSelection}
                onUpload={handleDocumentUpload}
                onUploadFileChange={setUploadFile}
                onUseAllDocuments={() => handleDocumentSelection("")}
                selectedDocumentDetail={selectedDocumentDetail}
                selectedDocumentId={selectedDocumentId}
                uploadFile={uploadFile}
                uploadInputRef={uploadInputRef}
              />
            ) : (
              <ChatPage
                activeProviderName={activeProviderName}
                canSend={canSend}
                chatProvider={chatProvider}
                error={error}
                isProviderBlocked={isProviderBlocked}
                isStreaming={isStreaming}
                messages={messages}
                onNavigateToDocuments={() => navigateTo("/documents")}
                onProviderChange={setChatProvider}
                onQuestionChange={setQuestion}
                onRetrievalModeChange={setRetrievalMode}
                onRerankStrategyChange={setRerankStrategy}
                onResponseModeChange={setResponseMode}
                onStopStreaming={stopStreaming}
                onSubmit={handleSubmit}
                onTopKChange={setTopK}
                onUseAllDocuments={() => handleDocumentSelection("")}
                providerStatus={providerStatus}
                question={question}
                retrievalMode={retrievalMode}
                retrievalModeOptions={retrievalModeOptions}
                rerankStrategy={rerankStrategy}
                rerankStrategyOptions={rerankStrategyOptions}
                responseMode={responseMode}
                selectedDocumentSummary={selectedDocumentSummary}
                selectedProviderInfo={selectedProviderInfo}
                status={status}
                topK={topK}
              />
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      <ScrollJumpControls visible={currentPath === "/chat"} />
    </main>
  );
}

export default AppRouter;
