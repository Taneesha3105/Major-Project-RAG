import { CheckCircle2, FileSearch, History, ScanText, ShieldAlert, Sparkles } from "lucide-react";
import { Logo } from "./AppLayout";

const FEATURES = [
  { icon: Sparkles, title: "Evidence-backed answers", text: "Every answer cites the exact page in your data room." },
  { icon: ScanText, title: "Reads scanned documents", text: "Built-in OCR for scanned PDFs and images." },
  { icon: ShieldAlert, title: "AI risk register", text: "Flags red flags, contradictions and missing information." },
  { icon: History, title: "Defensible audit trail", text: "Role-based access with a full activity log." },
];

export default function AuthLayout({ children }) {
  return (
    <div className="auth-page">
      <section className="auth-brand">
        <div className="auth-brand-inner">
          <Logo />
          <h1>
            Due diligence
            <br />
            <span>at deal speed.</span>
          </h1>
          <p className="auth-lead">
            The AI workspace for M&amp;A teams. Upload the data room, ask questions in plain English and get
            answers grounded in the evidence.
          </p>
          <ul className="auth-features">
            {FEATURES.map(({ icon: Icon, title, text }) => (
              <li key={title}>
                <span>
                  <Icon size={18} />
                </span>
                <div>
                  <strong>{title}</strong>
                  <p>{text}</p>
                </div>
              </li>
            ))}
          </ul>
          <div className="auth-preview" aria-hidden>
            <div className="auth-preview-head">
              <FileSearch size={14} /> Project Atlas · AI Assistant
            </div>
            <p className="auth-preview-q">Do any contracts allow termination on a change of control?</p>
            <p className="auth-preview-a">
              Yes. The Brightwater MSA lets the customer terminate immediately on a change of control
              <span className="cite-chip">1</span>, and that customer is ~20% of revenue
              <span className="cite-chip">2</span>.
            </p>
            <div className="auth-preview-flag">
              <CheckCircle2 size={13} /> Logged as a <b>critical</b> finding
            </div>
          </div>
        </div>
      </section>
      <section className="auth-form-side">{children}</section>
    </div>
  );
}
