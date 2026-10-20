import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Bot,
  FolderLock,
  LayoutGrid,
  ListChecks,
  Pencil,
  ShieldAlert,
  Trash2,
  Users,
} from "lucide-react";
import { Suspense, useCallback, useState } from "react";
import { Link, NavLink, Outlet, useNavigate, useParams } from "react-router-dom";
import { dealsApi } from "../../api/services";
import { StageBadge } from "../../components/deals/DealCard";
import DealFormModal from "../../components/deals/DealFormModal";
import StagePipeline from "../../components/deals/StagePipeline";
import { ConfirmDialog } from "../../components/ui/Overlay";
import { Button, ErrorState, IconButton, PageLoader } from "../../components/ui/primitives";
import { useToast } from "../../context/ToastContext";
import { useAsync } from "../../hooks/useAsync";
import { DEAL_TYPES, P } from "../../lib/constants";
import { classNames, formatMoney } from "../../lib/format";

const TABS = [
  { to: "", label: "Overview", icon: LayoutGrid, end: true },
  { to: "data-room", label: "Data room", icon: FolderLock },
  { to: "assistant", label: "AI assistant", icon: Bot },
  { to: "risks", label: "Risk register", icon: ShieldAlert },
  { to: "checklist", label: "Checklist", icon: ListChecks },
  { to: "team", label: "Team", icon: Users },
  { to: "activity", label: "Audit trail", icon: Activity },
];

export default function DealWorkspacePage() {
  const { dealId } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [busy, setBusy] = useState(false);
  const { data: deal, error, loading, reload, setData } = useAsync(() => dealsApi.get(dealId), [dealId]);

  const can = useCallback((permission) => Boolean(deal?.my_permissions?.includes(permission)), [deal]);
  const reloadDeal = useCallback(() => reload({ silent: true }), [reload]);

  if (loading && !deal) return <PageLoader label="Opening deal workspace…" />;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  const changeStage = async (stage) => {
    if (stage === deal.stage) return;
    try {
      const updated = await dealsApi.update(deal.id, { stage });
      setData((current) => ({ ...current, ...updated }));
      toast.success(`Deal moved to ${stage.replace("_", " ")}.`);
    } catch (err) {
      toast.error(err);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await dealsApi.remove(deal.id);
      toast.success("Deal deleted.");
      navigate("/deals");
    } catch (err) {
      toast.error(err);
      setBusy(false);
    }
  };

  return (
    <div className="page page-workspace">
      <section className="deal-hero">
        <div className="deal-hero-top">
          <Link to="/deals" className="back-link">
            <ArrowLeft size={15} /> All deals
          </Link>
          <div className="deal-hero-actions">
            {can(P.DEAL_EDIT) && (
              <Button variant="secondary" size="sm" icon={Pencil} onClick={() => setEditing(true)}>
                Edit
              </Button>
            )}
            {can(P.DEAL_DELETE) && <IconButton icon={Trash2} label="Delete deal" variant="ghost danger" onClick={() => setDeleting(true)} />}
          </div>
        </div>
        <div className="deal-hero-main">
          <div>
            <div className="deal-card-badges">
              {deal.code_name && <span className="code-badge">{deal.code_name}</span>}
              <StageBadge stage={deal.stage} />
              <span className="muted-chip">{DEAL_TYPES[deal.deal_type]}</span>
              {deal.my_member_role && <span className="muted-chip">You: {deal.my_member_role}</span>}
            </div>
            <h1>{deal.name}</h1>
            <p className="deal-parties lg">
              <span>{deal.acquirer_name}</span>
              <ArrowRight size={16} />
              <span>{deal.target_name}</span>
            </p>
          </div>
          <div className="deal-hero-value">
            <span>Deal value</span>
            <strong>{formatMoney(deal.deal_value, deal.currency)}</strong>
          </div>
        </div>
        <StagePipeline stage={deal.stage} onChange={can(P.DEAL_EDIT) ? changeStage : undefined} />
      </section>

      <nav className="tabs" aria-label="Deal sections">
        {TABS.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={label} to={to} end={end} className={({ isActive }) => classNames("tab", isActive && "active")}>
            <Icon size={16} />
            <span>{label}</span>
            {label === "Risk register" && deal.stats.open_risk_count > 0 && <span className="tab-count">{deal.stats.open_risk_count}</span>}
            {label === "Data room" && <span className="tab-count muted">{deal.stats.document_count}</span>}
          </NavLink>
        ))}
      </nav>

      <div className="tab-content">
        <Suspense fallback={<PageLoader />}>
          <Outlet context={{ deal, reloadDeal, can }} />
        </Suspense>
      </div>

      <DealFormModal open={editing} onClose={() => setEditing(false)} deal={deal} onSaved={(updated) => setData((c) => ({ ...c, ...updated }))} />
      <ConfirmDialog
        open={deleting}
        onClose={() => setDeleting(false)}
        onConfirm={remove}
        loading={busy}
        title="Delete this deal?"
        message={`This permanently deletes "${deal.name}", its data room, conversations, findings and checklist. This cannot be undone.`}
        confirmLabel="Delete deal"
      />
    </div>
  );
}
