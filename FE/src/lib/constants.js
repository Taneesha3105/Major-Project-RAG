import {
  Banknote,
  Briefcase,
  Building2,
  FileText,
  Gavel,
  Leaf,
  Lightbulb,
  Monitor,
  Receipt,
  ScrollText,
  ShieldCheck,
  TrendingUp,
  Users,
  Wrench,
} from "lucide-react";

export const CATEGORIES = {
  financial: { label: "Financial", icon: Banknote, color: "#6366f1" },
  legal: { label: "Legal", icon: Gavel, color: "#8b5cf6" },
  tax: { label: "Tax", icon: Receipt, color: "#ec4899" },
  contracts: { label: "Contracts", icon: ScrollText, color: "#0ea5e9" },
  hr: { label: "HR & Employment", icon: Users, color: "#14b8a6" },
  intellectual_property: { label: "Intellectual Property", icon: Lightbulb, color: "#f59e0b" },
  regulatory: { label: "Regulatory & Compliance", icon: ShieldCheck, color: "#ef4444" },
  operational: { label: "Operational", icon: Wrench, color: "#64748b" },
  commercial: { label: "Commercial", icon: TrendingUp, color: "#22c55e" },
  it: { label: "IT & Cyber", icon: Monitor, color: "#06b6d4" },
  environmental: { label: "Environmental & ESG", icon: Leaf, color: "#84cc16" },
  corporate: { label: "Corporate", icon: Building2, color: "#a855f7" },
  other: { label: "Other", icon: FileText, color: "#94a3b8" },
};
export const CATEGORY_KEYS = Object.keys(CATEGORIES);

export const DEAL_TYPES = {
  acquisition: "Acquisition",
  merger: "Merger",
  asset_purchase: "Asset purchase",
  joint_venture: "Joint venture",
  divestiture: "Divestiture",
};

export const STAGES = [
  { key: "screening", label: "Screening" },
  { key: "loi", label: "LOI" },
  { key: "due_diligence", label: "Due diligence" },
  { key: "negotiation", label: "Negotiation" },
  { key: "closing", label: "Closing" },
  { key: "closed", label: "Closed" },
  { key: "terminated", label: "Terminated" },
];
export const STAGE_LABELS = Object.fromEntries(STAGES.map((s) => [s.key, s.label]));

export const SEVERITIES = {
  critical: { label: "Critical", tone: "critical", rank: 0 },
  high: { label: "High", tone: "danger", rank: 1 },
  medium: { label: "Medium", tone: "warning", rank: 2 },
  low: { label: "Low", tone: "info", rank: 3 },
};

export const FINDING_TYPES = {
  risk: { label: "Risk", tone: "danger" },
  contradiction: { label: "Contradiction", tone: "purple" },
  missing_information: { label: "Missing info", tone: "warning" },
  opportunity: { label: "Opportunity", tone: "success" },
};

export const FINDING_STATUS = {
  open: { label: "Open", tone: "danger" },
  under_review: { label: "Under review", tone: "warning" },
  mitigated: { label: "Mitigated", tone: "success" },
  accepted: { label: "Accepted", tone: "info" },
  dismissed: { label: "Dismissed", tone: "neutral" },
};

export const CHECKLIST_STATUS = {
  pending: { label: "Pending", tone: "neutral" },
  in_progress: { label: "In progress", tone: "info" },
  completed: { label: "Completed", tone: "success" },
  flagged: { label: "Flagged", tone: "danger" },
  not_applicable: { label: "N/A", tone: "neutral" },
};

export const COVERAGE = {
  found: { label: "Evidence found", tone: "success" },
  partial: { label: "Partial evidence", tone: "warning" },
  missing: { label: "Not in data room", tone: "danger" },
};

export const PRIORITIES = {
  high: { label: "High", tone: "danger" },
  medium: { label: "Medium", tone: "warning" },
  low: { label: "Low", tone: "neutral" },
};

export const ROLES = {
  admin: { label: "Administrator", tone: "purple" },
  deal_lead: { label: "Deal lead", tone: "info" },
  analyst: { label: "Analyst", tone: "success" },
  viewer: { label: "Viewer", tone: "neutral" },
};

export const MEMBER_ROLES = {
  lead: "Lead",
  member: "Member",
  observer: "Observer (read-only)",
};

export const DOC_STATUS = {
  queued: { label: "Queued", tone: "neutral" },
  processing: { label: "Processing", tone: "info" },
  ready: { label: "Indexed", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
};

export const ACCEPTED_FILES = ".pdf,.docx,.xlsx,.xlsm,.csv,.txt,.md,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp";

export const SUGGESTED_QUESTIONS = [
  { icon: Banknote, text: "Summarise the target's key financial metrics and trends." },
  { icon: ScrollText, text: "Which contracts contain change-of-control or assignment clauses?" },
  { icon: Gavel, text: "List all litigation, claims and contingent liabilities with amounts." },
  { icon: Briefcase, text: "Are there contradictions between the documents on revenue or customers?" },
  { icon: Receipt, text: "What tax exposures or open tax enquiries are disclosed?" },
  { icon: Users, text: "What retention or change-of-control payments are owed to employees?" },
];

export const P = {
  DEAL_CREATE: "deal:create",
  DEAL_EDIT: "deal:edit",
  DEAL_DELETE: "deal:delete",
  MEMBERS_MANAGE: "deal:members",
  DOCUMENT_UPLOAD: "document:upload",
  DOCUMENT_DELETE: "document:delete",
  CHAT: "chat:use",
  ANALYSIS_RUN: "analysis:run",
  FINDING_EDIT: "finding:edit",
  CHECKLIST_EDIT: "checklist:edit",
  USER_MANAGE: "user:manage",
  USER_DIRECTORY: "user:directory",
};
