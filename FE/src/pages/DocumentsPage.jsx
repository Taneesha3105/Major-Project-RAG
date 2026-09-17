import { ArrowLeft, FileUp, FolderOpenDot, RefreshCw } from "lucide-react";

import { formatDate } from "../lib/chat";

function DocumentsPage({
  deletingDocumentId,
  documentNotice,
  documents,
  documentsError,
  documentsLoading,
  isUploading,
  onDeleteDocument,
  onNavigateToChat,
  onRefresh,
  onSelectDocument,
  onUpload,
  onUploadFileChange,
  onUseAllDocuments,
  selectedDocumentDetail,
  selectedDocumentId,
  uploadFile,
  uploadInputRef,
}) {
  return (
    <div className="page-stack">
      <section className="page-hero surface-card">
        <p className="eyebrow">Documents</p>
        <h2>Manage the knowledge base</h2>
        <p className="hero-copy">
          Upload source files, including UTF-8 text, PDF, and DOCX documents, inspect document
          details, preview the first stored chunks, and pick the exact document you want chat to
          search.
        </p>

        <div className="hero-actions">
          <button type="button" className="ghost-button ghost-button-inline" onClick={onNavigateToChat}>
            <ArrowLeft size={16} />
            Back to chat
          </button>
          <button type="button" className="secondary-button" onClick={onUseAllDocuments}>
            <FolderOpenDot size={16} />
            Use all documents
          </button>
        </div>
      </section>

      <div className="documents-layout">
        <section className="documents-sidebar surface-card">
          <div className="section-heading section-heading-spread page-section-header">
            <div>
              <p className="section-kicker">Upload</p>
              <h3>Add or refresh sources</h3>
            </div>

            <button type="button" className="ghost-button ghost-button-inline" onClick={onRefresh}>
              <RefreshCw size={16} />
              Refresh
            </button>
          </div>

          <form className="upload-form" onSubmit={onUpload}>
            <label className="field">
              <span>Upload file</span>
              <input
                ref={uploadInputRef}
                type="file"
                accept=".txt,.md,.csv,.log,.json,.py,.js,.ts,.tsx,.jsx,.html,.css,.pdf,.docx"
                onChange={(event) => onUploadFileChange(event.target.files?.[0] || null)}
              />
            </label>

            <p className="page-status-text">PDF and DOCX parsing is supported for machine-readable files only. OCR is not supported.</p>

            <button type="submit" className="primary-button" disabled={!uploadFile || isUploading}>
              <FileUp size={16} />
              {isUploading ? "Uploading..." : "Upload document"}
            </button>
          </form>

          <div className="document-notice">{documentNotice}</div>
          {documentsError ? <p className="error-banner">{documentsError}</p> : null}

          <section className="detail-surface">
            <div className="section-heading">
              <h3>Selected document</h3>
            </div>

            {selectedDocumentDetail ? (
              <article className="detail-card">
                <div className="detail-header">
                  <strong>{selectedDocumentDetail.filename}</strong>
                  <span>ID {selectedDocumentDetail.id}</span>
                </div>

                <div className="detail-grid">
                  <span>Chunks {selectedDocumentDetail.chunk_count}</span>
                  <span>Embedded {selectedDocumentDetail.embedded_chunk_count}</span>
                  <span>Source {selectedDocumentDetail.source_type || "Unknown"}</span>
                  <span>Format {selectedDocumentDetail.source_format || "Unknown"}</span>
                  <span>Parser {selectedDocumentDetail.parser_name || "Unknown"}</span>
                  <span>Embedding {selectedDocumentDetail.embedding_provider || "Not configured"}</span>
                </div>

                <p className="hash-line">Hash {selectedDocumentDetail.content_hash}</p>

                {selectedDocumentDetail.chunk_previews?.length > 0 ? (
                  <div className="chunk-preview-list">
                    {selectedDocumentDetail.chunk_previews.map((chunk) => (
                      <article key={chunk.id} className="chunk-preview-card">
                        <div className="detail-header">
                          <strong>Chunk {chunk.chunk_index}</strong>
                          <span>{chunk.character_count} chars</span>
                        </div>
                        <p className="message-content">{chunk.preview_text}</p>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="empty-state">
                    <strong>No document selected</strong>
                    <p>Select a document from the library to inspect its details and previews.</p>
                  </div>
                )}
              </article>
            ) : (
              <div className="empty-state">
                <strong>All documents are active</strong>
                <p>Chat currently searches across the entire document library.</p>
              </div>
            )}
          </section>
        </section>

        <section className="documents-main surface-card">
          <div className="section-heading section-heading-spread page-section-header">
            <div>
              <p className="section-kicker">Library</p>
              <h3>Available documents</h3>
            </div>
            <span className="page-status-text">{documents.length} documents loaded</span>
          </div>

          <div className="documents-list documents-list-page">
            {documentsLoading ? (
              <p className="status-text">Loading documents...</p>
            ) : documents.length === 0 ? (
              <div className="empty-state">
                <strong>No documents yet</strong>
                <p>Upload your first file to start grounding answers in your own content.</p>
              </div>
            ) : (
              documents.map((document) => {
                const isSelected = String(document.id) === selectedDocumentId;

                return (
                  <article
                    key={document.id}
                    className={`document-card ${isSelected ? "document-card-selected" : ""}`}
                  >
                    <button
                      type="button"
                      className="document-select-button"
                      onClick={() => onSelectDocument(String(document.id))}
                    >
                      <div className="detail-header">
                        <strong>{document.filename}</strong>
                        <span>{formatDate(document.created_at)}</span>
                      </div>
                      <div className="detail-grid">
                        <span>ID {document.id}</span>
                        <span>{document.chunk_count} chunks</span>
                        <span>{document.embedded_chunk_count} embedded</span>
                        <span>{document.embedding_provider || "No provider"}</span>
                      </div>
                    </button>

                    <div className="document-card-actions">
                      <button
                        type="button"
                        className="secondary-button"
                        onClick={() => onSelectDocument(String(document.id))}
                      >
                        {isSelected ? "Selected" : "Select"}
                      </button>
                      <button
                        type="button"
                        className="danger-button"
                        onClick={() => onDeleteDocument(document)}
                        disabled={deletingDocumentId === document.id}
                      >
                        {deletingDocumentId === document.id ? "Deleting..." : "Delete"}
                      </button>
                    </div>
                  </article>
                );
              })
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

export default DocumentsPage;
