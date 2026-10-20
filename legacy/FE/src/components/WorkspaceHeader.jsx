import { Files, MessageSquareText, MoonStar, Sparkles, SunMedium } from "lucide-react";

function WorkspaceHeader({ currentPath, onNavigate, onToggleTheme, resolvedTheme }) {
  return (
    <header className="workspace-header surface-card">
      <div className="brand-block">
        <div className="brand-icon">
          <Sparkles size={18} />
        </div>
        <div>
          <p className="eyebrow">RAG Chatbot</p>
          <h1>Grounded Workspace</h1>
        </div>
      </div>

      <nav className="workspace-nav" aria-label="Primary">
        <button
          type="button"
          className={`nav-pill ${currentPath === "/chat" ? "nav-pill-active" : ""}`}
          onClick={() => onNavigate("/chat")}
        >
          <MessageSquareText size={16} />
          Chat
        </button>
        <button
          type="button"
          className={`nav-pill ${currentPath === "/documents" ? "nav-pill-active" : ""}`}
          onClick={() => onNavigate("/documents")}
        >
          <Files size={16} />
          Documents
        </button>
      </nav>

      <div className="header-actions">
        <button
          type="button"
          className="icon-button"
          onClick={onToggleTheme}
          aria-label={resolvedTheme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          title={resolvedTheme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        >
          {resolvedTheme === "dark" ? <SunMedium size={18} /> : <MoonStar size={18} />}
        </button>
      </div>
    </header>
  );
}

export default WorkspaceHeader;
