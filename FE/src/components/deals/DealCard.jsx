import { ArrowRight, FileText, ListChecks, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { DEAL_TYPES, STAGE_LABELS } from "../../lib/constants";
import { formatMoney } from "../../lib/format";
import { Badge, ProgressRing } from "../ui/primitives";

export function StageBadge({ stage }) {
  return (
    <span className="stage-badge" data-stage={stage}>
      {STAGE_LABELS[stage]}
    </span>
  );
}

export default function DealCard({ deal }) {
  const { stats } = deal;
  const checklistPct = stats.checklist_total ? Math.round((100 * stats.checklist_completed) / stats.checklist_total) : 0;
  return (
    <Link to={`/deals/${deal.id}`} className="deal-card">
      <div className="deal-card-top">
        <div>
          <div className="deal-card-badges">
            {deal.code_name && <span className="code-badge">{deal.code_name}</span>}
            <StageBadge stage={deal.stage} />
          </div>
          <h3>{deal.name}</h3>
          <p className="deal-parties">
            <span>{deal.acquirer_name}</span>
            <ArrowRight size={13} />
            <span>{deal.target_name}</span>
          </p>
        </div>
        <ProgressRing value={stats.readiness_score} size={58} stroke={6} sublabel="ready" />
      </div>
      <div className="deal-card-meta">
        <Badge tone="neutral">{DEAL_TYPES[deal.deal_type]}</Badge>
        {deal.target_industry && <Badge tone="neutral">{deal.target_industry}</Badge>}
        <strong className="deal-value">{formatMoney(deal.deal_value, deal.currency)}</strong>
      </div>
      <div className="deal-card-stats">
        <span>
          <FileText size={14} /> {stats.ready_document_count}/{stats.document_count} docs
        </span>
        <span className={stats.critical_risk_count ? "text-danger" : ""}>
          <ShieldAlert size={14} /> {stats.open_risk_count} open
          {stats.critical_risk_count > 0 && ` · ${stats.critical_risk_count} critical`}
        </span>
        <span>
          <ListChecks size={14} /> {checklistPct}%
        </span>
      </div>
    </Link>
  );
}
