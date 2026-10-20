import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const CITATION = /\[(\d{1,2})\](?!\()/g;

/** Render LLM markdown; `[n]` markers become clickable citation chips. */
export function Markdown({ children, onCitation, activeCitation }) {
  const source = (children || "").replace(CITATION, (_, n) => `[${n}](#cite-${n})`);
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a({ href = "", children: label, ...props }) {
            if (href.startsWith("#cite-")) {
              const index = Number(href.slice(6));
              return (
                <button
                  type="button"
                  className={`cite-chip${activeCitation === index ? " active" : ""}`}
                  onClick={() => onCitation?.(index)}
                  title={`View source ${index}`}
                >
                  {index}
                </button>
              );
            }
            return (
              <a href={href} target="_blank" rel="noreferrer" {...props}>
                {label}
              </a>
            );
          },
          table: ({ children: content }) => (
            <div className="table-scroll">
              <table>{content}</table>
            </div>
          ),
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}
