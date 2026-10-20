import { Eye, FileSpreadsheet, FileText, FileType2, FolderLock, Image, Loader2, ScanText, Search, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { documentsApi } from "../../api/services";
import DocumentDrawer, { openDocument } from "../../components/documents/DocumentDrawer";
import UploadPanel from "../../components/documents/UploadPanel";
import { ConfirmDialog } from "../../components/ui/Overlay";
import { Badge, Card, EmptyState, ErrorState, IconButton, Input, PageLoader } from "../../components/ui/primitives";
import { useToast } from "../../context/ToastContext";
import { useAsync, useInterval } from "../../hooks/useAsync";
import { CATEGORIES, DOC_STATUS, P } from "../../lib/constants";
import { classNames, formatBytes, timeAgo } from "../../lib/format";
import { useDeal } from "./DealContext";

function FileIcon({ extension }) {
  if ([".xlsx", ".xlsm", ".csv"].includes(extension)) return <FileSpreadsheet size={18} className="ft ft-sheet" />;
  if ([".docx"].includes(extension)) return <FileType2 size={18} className="ft ft-word" />;
  if ([".pdf"].includes(extension)) return <FileText size={18} className="ft ft-pdf" />;
  if ([".txt", ".md"].includes(extension)) return <FileText size={18} className="ft" />;
  return <Image size={18} className="ft ft-image" />;
}

export default function DataRoomTab() {
  const { deal, can, reloadDeal } = useDeal();
  const toast = useToast();
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [toDelete, setToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const { data: documents, error, loading, reload, setData } = useAsync(() => documentsApi.list(deal.id), [deal.id]);

  const processing = documents?.some((d) => ["queued", "processing"].includes(d.status));
  // AI summaries land a few seconds after a document is indexed; keep polling briefly for them.
  const awaitingSummary = documents?.some(
    (d) => d.status === "ready" && !d.summary && d.processed_at && Date.now() - new Date(d.processed_at).getTime() < 90000,
  );
  useInterval(
    async () => {
      const before = documents?.filter((d) => d.status === "ready").length;
      const fresh = await reload({ silent: true });
      if (fresh && fresh.filter((d) => d.status === "ready").length !== before) reloadDeal();
    },
    3000,
    Boolean(processing || awaitingSummary),
  );

  const counts = useMemo(() => {
    const map = {};
    (documents || []).forEach((d) => (map[d.category] = (map[d.category] || 0) + 1));
    return map;
  }, [documents]);

  if (loading && !documents) return <PageLoader />;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  const visible = documents.filter(
    (d) => (!category || d.category === category) && (!search || d.filename.toLowerCase().includes(search.toLowerCase())),
  );
  const selected = documents.find((d) => d.id === selectedId);

  const replaceDoc = (doc) => setData((list) => list.map((d) => (d.id === doc.id ? doc : d)));

  const confirmDelete = async () => {
    setDeleting(true);
    try {
      await documentsApi.remove(deal.id, toDelete.id);
      setData((list) => list.filter((d) => d.id !== toDelete.id));
      if (selectedId === toDelete.id) setSelectedId(null);
      toast.success(`"${toDelete.filename}" deleted.`);
      setToDelete(null);
      reloadDeal();
    } catch (err) {
      toast.error(err);
    } finally {
      setDeleting(false);
    }
  };

  const readyCount = documents.filter((d) => d.status === "ready").length;
  const ocrCount = documents.filter((d) => d.ocr_applied).length;

  return (
    <div className="dataroom">
      {can(P.DOCUMENT_UPLOAD) && (
        <Card title="Add documents" subtitle="Files are extracted, OCR'd if scanned, chunked and embedded for AI search." icon={FolderLock}>
          <UploadPanel
            dealId={deal.id}
            onUploaded={() => {
              reload({ silent: true });
              reloadDeal();
            }}
          />
        </Card>
      )}

      <Card padded={false}>
        <div className="table-toolbar">
          <div className="table-toolbar-left">
            <h3>Virtual data room</h3>
            <span className="muted">
              {readyCount}/{documents.length} indexed{ocrCount > 0 && ` · ${ocrCount} OCR`}
              {processing && (
                <span className="processing-hint">
                  <Loader2 size={13} className="spin" /> processing
                </span>
              )}
            </span>
          </div>
          <Input icon={Search} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Filter by file name" className="table-search" />
        </div>
        <div className="chip-row">
          <button className={classNames("chip", !category && "active")} onClick={() => setCategory("")}>
            All <b>{documents.length}</b>
          </button>
          {Object.entries(counts).map(([key, count]) => (
            <button key={key} className={classNames("chip", category === key && "active")} onClick={() => setCategory(key)}>
              <i style={{ background: CATEGORIES[key]?.color }} />
              {CATEGORIES[key]?.label} <b>{count}</b>
            </button>
          ))}
        </div>

        {visible.length === 0 ? (
          <EmptyState
            icon={FolderLock}
            title={documents.length ? "No documents match" : "The data room is empty"}
            description={documents.length ? "Try another filter." : "Upload financial statements, contracts, tax filings and other diligence documents."}
          />
        ) : (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th>Document</th>
                  <th>Workstream</th>
                  <th>Status</th>
                  <th className="hide-sm">Details</th>
                  <th className="hide-sm">Uploaded</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {visible.map((doc) => {
                  const status = DOC_STATUS[doc.status];
                  const meta = CATEGORIES[doc.category];
                  return (
                    <tr key={doc.id} onClick={() => setSelectedId(doc.id)} className="clickable">
                      <td>
                        <div className="doc-name">
                          <FileIcon extension={doc.file_extension} />
                          <div>
                            <strong className="truncate" title={doc.filename}>
                              {doc.filename}
                            </strong>
                            {doc.summary && <span className="truncate">{doc.summary}</span>}
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className="cat-pill">
                          <i style={{ background: meta?.color }} />
                          {meta?.label}
                        </span>
                      </td>
                      <td>
                        <Badge tone={status.tone} dot className={doc.status === "processing" ? "pulsing" : ""}>
                          {status.label}
                        </Badge>
                      </td>
                      <td className="hide-sm muted">
                        {formatBytes(doc.file_size)}
                        {doc.page_count ? ` · ${doc.page_count}p` : ""}
                        {doc.ocr_applied && (
                          <span className="ocr-tag" title="Text recognised with OCR">
                            <ScanText size={12} /> OCR
                          </span>
                        )}
                      </td>
                      <td className="hide-sm muted">
                        {timeAgo(doc.created_at)}
                        {doc.uploaded_by_name && <small> · {doc.uploaded_by_name}</small>}
                      </td>
                      <td className="row-actions" onClick={(e) => e.stopPropagation()}>
                        <IconButton icon={Eye} label="Open original" size="sm" onClick={() => openDocument(deal.id, doc.id, toast)} />
                        {can(P.DOCUMENT_DELETE) && <IconButton icon={Trash2} label="Delete" size="sm" variant="ghost danger" onClick={() => setToDelete(doc)} />}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {selected && (
        <DocumentDrawer
          dealId={deal.id}
          document={selected}
          onClose={() => setSelectedId(null)}
          onChanged={replaceDoc}
          onDelete={setToDelete}
          canEdit={can(P.DOCUMENT_UPLOAD)}
          canDelete={can(P.DOCUMENT_DELETE)}
        />
      )}
      <ConfirmDialog
        open={Boolean(toDelete)}
        onClose={() => setToDelete(null)}
        onConfirm={confirmDelete}
        loading={deleting}
        title="Delete document?"
        message={`"${toDelete?.filename}" and its indexed content will be removed from the data room. AI answers will no longer cite it.`}
      />
    </div>
  );
}
