import { Bot, FileSearch, MessageSquarePlus, MessagesSquare, PanelLeftClose, PanelLeftOpen, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { chatApi, documentsApi } from "../../api/services";
import ChatMessage from "../../components/chat/ChatMessage";
import Composer from "../../components/chat/Composer";
import { openDocument } from "../../components/documents/DocumentDrawer";
import { CitationCard } from "../../components/ui/CitationCard";
import { EmptyState, IconButton, Spinner } from "../../components/ui/primitives";
import { useAuth } from "../../context/AuthContext";
import { useToast } from "../../context/ToastContext";
import { useAsync } from "../../hooks/useAsync";
import { P, SUGGESTED_QUESTIONS } from "../../lib/constants";
import { classNames, timeAgo } from "../../lib/format";
import { useDeal } from "./DealContext";

export default function AssistantTab() {
  const { deal, can } = useDeal();
  const { user } = useAuth();
  const toast = useToast();
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [selectedMessageId, setSelectedMessageId] = useState(null);
  const [activeCitation, setActiveCitation] = useState(null);
  const [scope, setScope] = useState([]);
  const [listOpen, setListOpen] = useState(true);
  const abortRef = useRef(null);
  const scrollRef = useRef(null);

  const { data: conversations, reload: reloadConversations, setData: setConversations } = useAsync(
    () => chatApi.conversations(deal.id),
    [deal.id],
  );
  const { data: documents } = useAsync(() => documentsApi.list(deal.id, { status: "ready" }), [deal.id]);
  const availableCategories = useMemo(() => [...new Set((documents || []).map((d) => d.category))], [documents]);

  useEffect(() => {
    if (!activeId) {
      setMessages([]);
      return;
    }
    if (streaming) return;
    let cancelled = false;
    setLoadingMessages(true);
    chatApi
      .messages(deal.id, activeId)
      .then((list) => {
        if (cancelled) return;
        setMessages(list);
        const lastAi = [...list].reverse().find((m) => m.role === "assistant");
        setSelectedMessageId(lastAi?.id || null);
      })
      .catch((error) => toast.error(error))
      .finally(() => !cancelled && setLoadingMessages(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeId, deal.id]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const updateMessage = (id, patch) =>
    setMessages((list) => list.map((m) => (m.id === id ? { ...m, ...(typeof patch === "function" ? patch(m) : patch) } : m)));

  const send = async (question) => {
    let conversationId = activeId;
    try {
      if (!conversationId) {
        const conversation = await chatApi.create(deal.id, null);
        conversationId = conversation.id;
        setConversations((list) => [conversation, ...(list || [])]);
        setActiveId(conversationId);
      }
    } catch (error) {
      toast.error(error);
      return;
    }

    const tempUser = { id: `tmp-u-${Date.now()}`, role: "user", content: question };
    const tempAi = { id: `tmp-a-${Date.now()}`, role: "assistant", content: "", citations: [], streaming: true };
    setMessages((list) => [...list, tempUser, tempAi]);
    setSelectedMessageId(tempAi.id);
    setActiveCitation(null);
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    let finalId = tempAi.id;

    try {
      await chatApi.ask(
        deal.id,
        conversationId,
        { question, scope: { categories: scope } },
        {
          meta: (data) => {
            updateMessage(tempAi.id, { citations: data.citations });
            setConversations((list) => (list || []).map((c) => (c.id === conversationId ? { ...c, title: data.conversation_title } : c)));
          },
          token: (data) => updateMessage(tempAi.id, (m) => ({ content: m.content + data.text })),
          done: (data) => {
            finalId = data.id;
            updateMessage(tempAi.id, { ...data, streaming: false });
            setSelectedMessageId(data.id);
          },
          error: (data) => updateMessage(tempAi.id, { content: data.message, error: true, streaming: false }),
        },
        controller.signal,
      );
    } catch (error) {
      updateMessage(tempAi.id, { content: error.message, error: true, streaming: false });
    } finally {
      if (controller.signal.aborted) updateMessage(finalId, { streaming: false });
      setStreaming(false);
      abortRef.current = null;
      reloadConversations({ silent: true });
    }
  };

  const stop = () => abortRef.current?.abort();

  const newChat = () => {
    if (streaming) return;
    setActiveId(null);
    setSelectedMessageId(null);
  };

  const removeConversation = async (conversation) => {
    try {
      await chatApi.remove(deal.id, conversation.id);
      setConversations((list) => list.filter((c) => c.id !== conversation.id));
      if (activeId === conversation.id) newChat();
    } catch (error) {
      toast.error(error);
    }
  };

  const feedback = async (message, value) => {
    try {
      const updated = await chatApi.feedback(deal.id, activeId, message.id, value);
      updateMessage(message.id, { feedback: updated.feedback });
    } catch (error) {
      toast.error(error);
    }
  };

  const showCitation = (message, index) => {
    setSelectedMessageId(message.id);
    setActiveCitation(index);
    setTimeout(() => document.getElementById(`citation-${index}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 50);
  };

  const selectedMessage = messages.find((m) => m.id === selectedMessageId);
  const citations = [...(selectedMessage?.citations || [])].sort((a, b) => Number(Boolean(b.cited)) - Number(Boolean(a.cited)) || a.index - b.index);
  const hasCitedFlags = citations.some((c) => c.cited !== undefined);

  return (
    <div className={classNames("assistant", !listOpen && "list-collapsed")}>
      <aside className="conv-list">
        <div className="conv-list-head">
          <button className="btn btn-primary btn-block" onClick={newChat} disabled={streaming || !can(P.CHAT)}>
            <MessageSquarePlus size={16} />
            <span>New conversation</span>
          </button>
        </div>
        <div className="conv-items">
          {!conversations ? (
            <Spinner />
          ) : conversations.length === 0 ? (
            <p className="muted conv-empty">Your conversations about this deal will appear here.</p>
          ) : (
            conversations.map((conversation) => (
              <div
                key={conversation.id}
                className={classNames("conv-item", conversation.id === activeId && "active")}
                onClick={() => !streaming && setActiveId(conversation.id)}
                role="button"
                tabIndex={0}
              >
                <MessagesSquare size={15} />
                <div>
                  <strong className="truncate">{conversation.title}</strong>
                  <span>{timeAgo(conversation.updated_at)}</span>
                </div>
                <button
                  className="icon-btn ghost sm conv-delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeConversation(conversation);
                  }}
                  aria-label="Delete conversation"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))
          )}
        </div>
      </aside>

      <section className="chat">
        <div className="chat-head">
          <IconButton icon={listOpen ? PanelLeftClose : PanelLeftOpen} label="Toggle conversations" onClick={() => setListOpen((v) => !v)} />
          <div>
            <strong>{conversations?.find((c) => c.id === activeId)?.title || "New conversation"}</strong>
            <span>
              Grounded in {documents?.length ?? 0} indexed document{documents?.length === 1 ? "" : "s"}
              {scope.length > 0 && ` · scoped to ${scope.length} workstream(s)`}
            </span>
          </div>
        </div>
        <div className="chat-scroll" ref={scrollRef}>
          {loadingMessages ? (
            <Spinner label="Loading conversation…" />
          ) : messages.length === 0 ? (
            <div className="chat-welcome">
              <span className="chat-welcome-icon">
                <Bot size={28} />
              </span>
              <h2>Ask anything about {deal.target_name}</h2>
              <p>
                DealLens searches the data room with hybrid semantic + keyword retrieval, re-ranks the evidence, and answers with
                citations you can verify.
              </p>
              {documents?.length === 0 && <div className="alert alert-warning">Upload and index documents in the data room first.</div>}
              <div className="suggestions">
                {SUGGESTED_QUESTIONS.map(({ icon: Icon, text }) => (
                  <button key={text} onClick={() => send(text)} disabled={streaming || !can(P.CHAT) || !documents?.length}>
                    <Icon size={16} />
                    <span>{text}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="messages">
              {messages.map((message) => (
                <ChatMessage
                  key={message.id}
                  message={message}
                  userName={user.full_name}
                  active={message.id === selectedMessageId}
                  activeCitation={activeCitation}
                  onSelect={() => setSelectedMessageId(message.id)}
                  onCitation={showCitation}
                  onFeedback={feedback}
                />
              ))}
            </div>
          )}
        </div>
        <Composer
          onSend={send}
          onStop={stop}
          streaming={streaming}
          disabled={!can(P.CHAT)}
          availableCategories={availableCategories}
          scope={scope}
          onScopeChange={setScope}
        />
      </section>

      <aside className="evidence">
        <div className="evidence-head">
          <FileSearch size={16} />
          <strong>Evidence</strong>
          {citations.length > 0 && <span className="muted">{citations.length} excerpts</span>}
        </div>
        {citations.length === 0 ? (
          <EmptyState compact icon={FileSearch} title="No sources selected" description="Source excerpts for the selected answer appear here." />
        ) : (
          <div className="evidence-list">
            {citations.map((citation, i) => (
              <div key={citation.index}>
                {hasCitedFlags && i > 0 && !citation.cited && citations[i - 1].cited && <p className="evidence-divider">Retrieved but not cited</p>}
                <CitationCard
                  citation={citation}
                  active={activeCitation === citation.index}
                  onOpen={() => openDocument(deal.id, citation.document_id, toast)}
                />
              </div>
            ))}
          </div>
        )}
      </aside>
    </div>
  );
}
