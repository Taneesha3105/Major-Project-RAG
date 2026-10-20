import { Bot, ChevronDown, FileSearch, ListChecks, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { dealsApi, diligenceApi } from "../../api/services";
import { openDocument } from "../../components/documents/DocumentDrawer";
import { CitationCard } from "../../components/ui/CitationCard";
import { Modal } from "../../components/ui/Overlay";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Field,
  IconButton,
  Input,
  PageLoader,
  ProgressBar,
  ProgressRing,
  Segmented,
  Select,
  Textarea,
} from "../../components/ui/primitives";
import { useToast } from "../../context/ToastContext";
import { useAsync } from "../../hooks/useAsync";
import { CATEGORIES, CATEGORY_KEYS, CHECKLIST_STATUS, COVERAGE, P, PRIORITIES } from "../../lib/constants";
import { classNames, timeAgo } from "../../lib/format";
import { useDeal } from "./DealContext";

const DONE = ["completed", "not_applicable"];

function AddItemModal({ open, onClose, onSave }) {
  const [form, setForm] = useState({ category: "financial", title: "", description: "", priority: "medium" });
  const [saving, setSaving] = useState(false);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    const ok = await onSave({ ...form, description: form.description || null });
    setSaving(false);
    if (ok) {
      setForm({ category: form.category, title: "", description: "", priority: "medium" });
      onClose();
    }
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add request"
      subtitle="Add an item to the due-diligence request list."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="item-form" loading={saving}>
            Add item
          </Button>
        </>
      }
    >
      <form id="item-form" className="form-grid" onSubmit={submit}>
        <Field label="Request" required className="span-2">
          <Input value={form.title} onChange={set("title")} required minLength={2} placeholder="e.g. Data processing agreements with sub-processors" />
        </Field>
        <Field label="Workstream">
          <Select value={form.category} onChange={set("category")} options={CATEGORY_KEYS.map((key) => ({ value: key, label: CATEGORIES[key].label }))} />
        </Field>
        <Field label="Priority">
          <Select value={form.priority} onChange={set("priority")} options={Object.entries(PRIORITIES).map(([value, v]) => ({ value, label: v.label }))} />
        </Field>
        <Field label="Details" className="span-2">
          <Textarea rows={3} value={form.description} onChange={set("description")} />
        </Field>
      </form>
    </Modal>
  );
}

function ChecklistRow({ item, members, canEdit, onUpdate, onDelete, dealId, toast }) {
  const [open, setOpen] = useState(false);
  const coverage = item.ai_coverage ? COVERAGE[item.ai_coverage] : null;
  return (
    <li className={classNames("check-row", DONE.includes(item.status) && "done", open && "open")}>
      <div className="check-main">
        <Select
          className={`status-select tone-${CHECKLIST_STATUS[item.status].tone}`}
          value={item.status}
          disabled={!canEdit}
          onChange={(e) => onUpdate(item, { status: e.target.value })}
          options={Object.entries(CHECKLIST_STATUS).map(([value, v]) => ({ value, label: v.label }))}
        />
        <button className="check-text" onClick={() => setOpen((v) => !v)}>
          <strong>{item.title}</strong>
          {item.description && <span>{item.description}</span>}
        </button>
        <div className="check-side">
          {coverage && (
            <Badge tone={coverage.tone} icon={Bot}>
              {coverage.label}
            </Badge>
          )}
          <Badge tone={PRIORITIES[item.priority].tone}>{PRIORITIES[item.priority].label}</Badge>
          <Select
            className="assignee-select"
            value={item.assignee?.id || ""}
            disabled={!canEdit}
            onChange={(e) => onUpdate(item, { assignee_id: e.target.value || null })}
            placeholder="Unassigned"
            options={members.map((m) => ({ value: m.user.id, label: m.user.full_name }))}
          />
          <IconButton icon={ChevronDown} label="Details" size="sm" className={open ? "rotated" : ""} onClick={() => setOpen((v) => !v)} />
        </div>
      </div>
      {open && (
        <div className="check-detail">
          {item.ai_note ? (
            <div className={`ai-note tone-${coverage?.tone}`}>
              <Bot size={15} />
              <div>
                <strong>AI evidence review</strong>
                <p>{item.ai_note}</p>
                <small>Reviewed {timeAgo(item.ai_reviewed_at)}</small>
              </div>
            </div>
          ) : (
            <p className="muted">Not reviewed by AI yet. Run “AI evidence review” to check this request against the data room.</p>
          )}
          {item.ai_citations?.length > 0 && (
            <div className="evidence-list">
              {item.ai_citations.map((c) => (
                <CitationCard key={c.index} citation={c} compact onOpen={() => openDocument(dealId, c.document_id, toast)} />
              ))}
            </div>
          )}
          {canEdit && (
            <div className="check-detail-actions">
              <Textarea
                rows={2}
                defaultValue={item.notes || ""}
                placeholder="Reviewer notes…"
                onBlur={(e) => e.target.value !== (item.notes || "") && onUpdate(item, { notes: e.target.value || null })}
              />
              <Button variant="ghost-danger" size="sm" icon={Trash2} onClick={() => onDelete(item)}>
                Remove
              </Button>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

export default function ChecklistTab() {
  const { deal, can, reloadDeal } = useDeal();
  const toast = useToast();
  const [view, setView] = useState("all");
  const [adding, setAdding] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [collapsed, setCollapsed] = useState({});
  const { data, error, loading, reload, setData } = useAsync(
    () => Promise.all([diligenceApi.checklist(deal.id), dealsApi.members(deal.id)]),
    [deal.id],
  );

  const items = data?.[0] || [];
  const members = data?.[1] || [];
  const groups = useMemo(() => {
    const filtered = items.filter((item) => {
      if (view === "open") return !DONE.includes(item.status);
      if (view === "missing") return item.ai_coverage === "missing";
      if (view === "flagged") return item.status === "flagged";
      return true;
    });
    return CATEGORY_KEYS.map((key) => ({ key, items: filtered.filter((i) => i.category === key), all: items.filter((i) => i.category === key) })).filter(
      (g) => g.items.length,
    );
  }, [items, view]);

  if (loading && !data) return <PageLoader />;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  const done = items.filter((i) => DONE.includes(i.status)).length;
  const pct = items.length ? Math.round((100 * done) / items.length) : 0;
  const reviewed = items.filter((i) => i.ai_coverage);
  const coverageCounts = { found: 0, partial: 0, missing: 0 };
  reviewed.forEach((i) => (coverageCounts[i.ai_coverage] += 1));
  const canEdit = can(P.CHECKLIST_EDIT);

  const setItems = (updater) => setData(([list, rest]) => [updater(list), rest]);

  const update = async (item, payload) => {
    try {
      const updated = await diligenceApi.updateItem(deal.id, item.id, payload);
      setItems((list) => list.map((i) => (i.id === item.id ? updated : i)));
      if (payload.status) reloadDeal();
    } catch (err) {
      toast.error(err);
    }
  };

  const remove = async (item) => {
    try {
      await diligenceApi.removeItem(deal.id, item.id);
      setItems((list) => list.filter((i) => i.id !== item.id));
      reloadDeal();
    } catch (err) {
      toast.error(err);
    }
  };

  const add = async (payload) => {
    try {
      const created = await diligenceApi.createItem(deal.id, payload);
      setItems((list) => [...list, created]);
      reloadDeal();
      toast.success("Request added.");
      return true;
    } catch (err) {
      toast.error(err);
      return false;
    }
  };

  const review = async () => {
    setReviewing(true);
    try {
      const result = await diligenceApi.reviewChecklist(deal.id);
      toast.success(`${result.found} found · ${result.partial} partial · ${result.missing} missing`, "AI evidence review complete");
      reload({ silent: true });
    } catch (err) {
      toast.error(err);
    } finally {
      setReviewing(false);
    }
  };

  return (
    <div className="checklist">
      <div className="checklist-summary">
        <Card className="checklist-progress">
          <ProgressRing value={pct} size={96} stroke={9} label={`${pct}%`} sublabel="complete" />
          <div>
            <h3>Request list progress</h3>
            <p className="muted">
              {done} of {items.length} requests completed or not applicable.
            </p>
            {reviewed.length > 0 && (
              <div className="coverage-badges">
                <Badge tone="success">{coverageCounts.found} evidenced</Badge>
                <Badge tone="warning">{coverageCounts.partial} partial</Badge>
                <Badge tone="danger">{coverageCounts.missing} not in data room</Badge>
              </div>
            )}
          </div>
        </Card>
        <Card className="checklist-ai">
          <span className="analysis-icon">
            <FileSearch size={20} />
          </span>
          <div>
            <h3>AI evidence review</h3>
            <p className="muted">Gemini checks every open request against the data room and flags what is missing or incomplete.</p>
          </div>
          {can(P.ANALYSIS_RUN) && (
            <Button icon={Bot} onClick={review} loading={reviewing} disabled={!items.length}>
              {reviewing ? "Reviewing…" : "Run review"}
            </Button>
          )}
        </Card>
      </div>

      <div className="toolbar">
        <Segmented
          value={view}
          onChange={setView}
          options={[
            { value: "all", label: "All", count: items.length },
            { value: "open", label: "Open", count: items.length - done },
            { value: "missing", label: "Missing evidence", count: coverageCounts.missing },
            { value: "flagged", label: "Flagged", count: items.filter((i) => i.status === "flagged").length },
          ]}
        />
        {canEdit && (
          <Button variant="secondary" icon={Plus} onClick={() => setAdding(true)}>
            Add request
          </Button>
        )}
      </div>

      {groups.length === 0 ? (
        <Card>
          <EmptyState icon={ListChecks} title="Nothing here" description={items.length ? "No requests match this view." : "Add requests to build the diligence checklist."} />
        </Card>
      ) : (
        groups.map((group) => {
          const meta = CATEGORIES[group.key];
          const Icon = meta.icon;
          const groupDone = group.all.filter((i) => DONE.includes(i.status)).length;
          const isCollapsed = collapsed[group.key];
          return (
            <Card key={group.key} padded={false} className="check-group">
              <button className="check-group-head" onClick={() => setCollapsed({ ...collapsed, [group.key]: !isCollapsed })}>
                <span className="coverage-icon" style={{ color: meta.color, background: `${meta.color}1a` }}>
                  <Icon size={16} />
                </span>
                <strong>{meta.label}</strong>
                <span className="muted">
                  {groupDone}/{group.all.length}
                </span>
                <div className="check-group-progress">
                  <ProgressBar value={(100 * groupDone) / group.all.length} size="sm" />
                </div>
                <ChevronDown size={16} className={isCollapsed ? "" : "rotated"} />
              </button>
              {!isCollapsed && (
                <ul className="check-list">
                  {group.items.map((item) => (
                    <ChecklistRow key={item.id} item={item} members={members} canEdit={canEdit} onUpdate={update} onDelete={remove} dealId={deal.id} toast={toast} />
                  ))}
                </ul>
              )}
            </Card>
          );
        })
      )}
      <AddItemModal open={adding} onClose={() => setAdding(false)} onSave={add} />
    </div>
  );
}
