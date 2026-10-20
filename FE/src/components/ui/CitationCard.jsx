import { ExternalLink, FileText } from "lucide-react";
import { CATEGORIES } from "../../lib/constants";
import { classNames } from "../../lib/format";

/** One piece of evidence: document, page/section, snippet. Clicking opens the source document. */
export function CitationCard({ citation, active, onOpen, compact }) {
  const category = CATEGORIES[citation.category] || CATEGORIES.other;
  const location = [
    citation.page_number ? `Page ${citation.page_number}` : null,
    citation.section ? citation.section : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <article
      id={`citation-${citation.index}`}
      className={classNames("citation-card", active && "active", compact && "compact")}
    >
      <header>
        <span className="citation-index">{citation.index}</span>
        <div className="citation-doc">
          <strong title={citation.filename}>
            <FileText size={13} /> {citation.filename}
          </strong>
          <span>
            <i style={{ background: category.color }} /> {category.label}
            {location && ` · ${location}`}
          </span>
        </div>
        {onOpen && (
          <button className="icon-btn ghost sm" onClick={() => onOpen(citation)} title="Open document">
            <ExternalLink size={14} />
          </button>
        )}
      </header>
      <p className="citation-snippet">{citation.snippet}</p>
    </article>
  );
}
