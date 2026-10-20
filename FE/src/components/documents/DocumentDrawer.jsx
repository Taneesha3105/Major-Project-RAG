import { Download, FileText, Layers, RefreshCcw, ScanText, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import { documentsApi } from "../../api/services";
import { useToast } from "../../context/ToastContext";
import { useAsync } from "../../hooks/useAsync";
import { CATEGORIES, CATEGORY_KEYS, DOC_STATUS } from "../../lib/constants";
import { formatBytes, formatDate } from "../../lib/format";
import { Drawer } from "../ui/Overlay";
import { Badge, Button, EmptyState, Field, Select, Spinner } from "../ui/primitives";

export async function openDocument(dealId, documentId, toast) {
  const tab = window.open("", "_blank");
  try {
    const url = await documentsApi.fileUrl(dealId, documentId);
    if (tab) tab.location.href = url;
    else window.location.href = url;
  } catch (error) {
    tab?.close();
    toast?.error(error);
  }
}

export default function DocumentDrawer({ dealId, document, onClose, onChanged, onDelete, canEdit, canDelete }) {
  const toast = useToast();
  const [tab, setTab] = useState("insights");
  const { data: chunks, loading: chunksLoading } = useAsync(
    () => (document && tab === "content" ? documentsApi.chunks(dealId, document.id, 0, 30) : Promise.resolve(null)),
    [document?.id, tab],
  );
  if (!document) return null;
  const status = DOC_STATUS[document.status];

  const changeCategory = async (category) => {
    try {
      onChanged?.(await documentsApi.update(dealId, document.id, { category }));
      toast.success("Category updated.");
    } catch (error) {
      toast.error(error);
    }
  };

  const reprocess = async () => {
    try {
      onChanged?.(await documentsApi.reprocess(dealId, document.id));
      toast.info("Document queued for re-processing.");
    } catch (error) {
      toast.error(error);
    }
  };

  return (
    <Drawer
      open
      onClose={onClose}
      width={640}
      title={document.filename}
      subtitle={`${formatBytes(document.file_size)} · uploaded ${formatDate(document.created_at, true)}${document.uploaded_by_name ? ` by ${document.uploaded_by_name}` : ""}`}
      headerExtra={
        <div className="drawer-badges">
          <Badge tone={status.tone} dot>
            {status.label}
          </Badge>
          {document.page_count ? <Badge tone="neutral">{document.page_count} pages</Badge> : null}
          <Badge tone="neutral" icon={Layers}>
            {document.chunk_count} chunks
          </Badge>
          {document.ocr_applied && (
            <Badge tone="purple" icon={ScanText}>
              OCR · {document.ocr_page_count} page(s)
            </Badge>
          )}
        </div>
      }
      footer={
        <>
          {canDelete && (
            <Button variant="ghost-danger" icon={Trash2} onClick={() => onDelete(document)}>
              Delete
            </Button>
          )}
          <span className="spacer" />
          {canEdit && (
            <Button variant="secondary" icon={RefreshCcw} onClick={reprocess} disabled={document.status === "processing"}>
              Re-process
            </Button>
          )}
          <Button icon={Download} onClick={() => openDocument(dealId, document.id, toast)}>
            Open original
          </Button>
        </>
      }
    >
      {document.status === "failed" && <div className="alert alert-danger">{document.error_message}</div>}
      <div className="drawer-tabs">
        <button className={tab === "insights" ? "active" : ""} onClick={() => setTab("insights")}>
          <Sparkles size={14} /> AI insights
        </button>
        <button className={tab === "content" ? "active" : ""} onClick={() => setTab("content")}>
          <FileText size={14} /> Extracted text
        </button>
      </div>

      {tab === "insights" ? (
        <div className="stack">
          {canEdit && (
            <Field label="Workstream">
              <Select value={document.category} onChange={(e) => changeCategory(e.target.value)} options={CATEGORY_KEYS.map((key) => ({ value: key, label: CATEGORIES[key].label }))} />
            </Field>
          )}
          {document.description && <p className="muted">{document.description}</p>}
          <section>
            <h4 className="section-title">Summary</h4>
            {document.summary ? (
              <p className="doc-summary">{document.summary}</p>
            ) : (
              <p className="muted">
                {document.status === "ready" ? "Summary is being generated or unavailable." : "Available once processing completes."}
              </p>
            )}
          </section>
          <section>
            <h4 className="section-title">Key facts</h4>
            {document.key_facts?.length ? (
              <dl className="key-facts">
                {document.key_facts.map((fact, index) => (
                  <div key={index}>
                    <dt>{fact.label}</dt>
                    <dd>{fact.value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="muted">No key facts extracted yet.</p>
            )}
          </section>
        </div>
      ) : chunksLoading ? (
        <Spinner label="Loading extracted text…" />
      ) : chunks?.length ? (
        <ol className="chunk-list">
          {chunks.map((chunk) => (
            <li key={chunk.id}>
              <header>
                <span>#{chunk.chunk_index + 1}</span>
                {chunk.page_number && <span>Page {chunk.page_number}</span>}
                {chunk.section && <span className="truncate">{chunk.section}</span>}
                {chunk.is_ocr && (
                  <Badge tone="purple" icon={ScanText}>
                    OCR
                  </Badge>
                )}
              </header>
              <p>{chunk.content}</p>
            </li>
          ))}
        </ol>
      ) : (
        <EmptyState compact icon={FileText} title="No extracted text" description="The document has not been indexed yet." />
      )}
    </Drawer>
  );
}
