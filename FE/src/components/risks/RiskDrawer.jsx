import { Bot, Lightbulb, Trash2, User } from "lucide-react";
import { useEffect, useState } from "react";
import { diligenceApi } from "../../api/services";
import { useToast } from "../../context/ToastContext";
import { CATEGORIES, FINDING_STATUS, FINDING_TYPES, SEVERITIES } from "../../lib/constants";
import { formatDate } from "../../lib/format";
import { openDocument } from "../documents/DocumentDrawer";
import { CitationCard } from "../ui/CitationCard";
import { Drawer } from "../ui/Overlay";
import { Badge, Button, Field, Select, Textarea } from "../ui/primitives";

export default function RiskDrawer({ dealId, finding, members, canEdit, onClose, onChanged, onDelete }) {
  const toast = useToast();
  const [note, setNote] = useState(finding?.resolution_note || "");
  const [saving, setSaving] = useState(false);
  useEffect(() => setNote(finding?.resolution_note || ""), [finding?.id, finding?.resolution_note]);
  if (!finding) return null;

  const update = async (payload, message) => {
    setSaving(true);
    try {
      onChanged(await diligenceApi.updateRisk(dealId, finding.id, payload));
      if (message) toast.success(message);
    } catch (error) {
      toast.error(error);
    } finally {
      setSaving(false);
    }
  };

  const severity = SEVERITIES[finding.severity];
  return (
    <Drawer
      open
      onClose={onClose}
      width={620}
      title={finding.title}
      subtitle={`${CATEGORIES[finding.category]?.label} · logged ${formatDate(finding.created_at)}`}
      headerExtra={
        <div className="drawer-badges">
          <Badge tone={severity.tone}>{severity.label}</Badge>
          <Badge tone={FINDING_TYPES[finding.finding_type].tone}>{FINDING_TYPES[finding.finding_type].label}</Badge>
          <Badge tone={FINDING_STATUS[finding.status].tone} dot>
            {FINDING_STATUS[finding.status].label}
          </Badge>
          <Badge tone="neutral" icon={finding.source === "ai" ? Bot : User}>
            {finding.source === "ai" ? "AI-identified" : "Manual"}
          </Badge>
        </div>
      }
      footer={
        canEdit && (
          <>
            <Button variant="ghost-danger" icon={Trash2} onClick={() => onDelete(finding)}>
              Delete
            </Button>
            <span className="spacer" />
            <Button variant="secondary" onClick={() => update({ status: "dismissed" }, "Finding dismissed.")} disabled={saving}>
              Dismiss
            </Button>
            <Button onClick={() => update({ status: "mitigated", resolution_note: note || null }, "Marked as mitigated.")} loading={saving}>
              Mark mitigated
            </Button>
          </>
        )
      }
    >
      <div className="stack">
        <p className="finding-description">{finding.description}</p>
        {finding.financial_impact && (
          <div className="impact">
            <span>Estimated impact</span>
            <strong>{finding.financial_impact}</strong>
          </div>
        )}
        {finding.recommendation && (
          <div className="recommendation">
            <Lightbulb size={16} />
            <div>
              <strong>Recommended action</strong>
              <p>{finding.recommendation}</p>
            </div>
          </div>
        )}

        {canEdit && (
          <div className="form-grid">
            <Field label="Status">
              <Select
                value={finding.status}
                onChange={(e) => update({ status: e.target.value }, "Status updated.")}
                options={Object.entries(FINDING_STATUS).map(([value, v]) => ({ value, label: v.label }))}
              />
            </Field>
            <Field label="Severity">
              <Select
                value={finding.severity}
                onChange={(e) => update({ severity: e.target.value }, "Severity updated.")}
                options={Object.entries(SEVERITIES).map(([value, v]) => ({ value, label: v.label }))}
              />
            </Field>
            <Field label="Owner" className="span-2">
              <Select
                value={finding.owner?.id || ""}
                onChange={(e) => update({ owner_id: e.target.value || null }, "Owner updated.")}
                placeholder="Unassigned"
                options={(members || []).map((m) => ({ value: m.user.id, label: m.user.full_name }))}
              />
            </Field>
            <Field label="Resolution / review notes" className="span-2">
              <Textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Questions sent to seller, SPA protection agreed, etc." />
            </Field>
            {note !== (finding.resolution_note || "") && (
              <div className="span-2 right">
                <Button size="sm" variant="secondary" onClick={() => update({ resolution_note: note || null }, "Notes saved.")} loading={saving}>
                  Save notes
                </Button>
              </div>
            )}
          </div>
        )}

        <section>
          <h4 className="section-title">Evidence ({finding.citations.length})</h4>
          {finding.citations.length ? (
            <div className="evidence-list">
              {finding.citations.map((citation) => (
                <CitationCard key={citation.index} citation={citation} compact onOpen={() => openDocument(dealId, citation.document_id, toast)} />
              ))}
            </div>
          ) : (
            <p className="muted">No document evidence attached{finding.finding_type === "missing_information" ? " — this is an information gap." : "."}</p>
          )}
        </section>
      </div>
    </Drawer>
  );
}
