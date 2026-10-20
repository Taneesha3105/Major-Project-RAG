import { useEffect, useState } from "react";
import { diligenceApi } from "../../api/services";
import { useToast } from "../../context/ToastContext";
import { CATEGORIES, CATEGORY_KEYS, FINDING_TYPES, SEVERITIES } from "../../lib/constants";
import { Modal } from "../ui/Overlay";
import { Button, Field, Input, Select, Textarea } from "../ui/primitives";

const EMPTY = {
  title: "",
  description: "",
  category: "financial",
  finding_type: "risk",
  severity: "medium",
  recommendation: "",
  financial_impact: "",
  owner_id: "",
};

export default function RiskFormModal({ open, onClose, dealId, members, onSaved }) {
  const toast = useToast();
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (open) setForm(EMPTY);
  }, [open]);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      const saved = await diligenceApi.createRisk(dealId, {
        ...form,
        recommendation: form.recommendation || null,
        financial_impact: form.financial_impact || null,
        owner_id: form.owner_id || null,
      });
      toast.success("Finding added to the risk register.");
      onSaved(saved);
      onClose();
    } catch (error) {
      toast.error(error);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title="Log a finding"
      subtitle="Record a risk, contradiction or information gap identified during review."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="risk-form" loading={saving}>
            Add finding
          </Button>
        </>
      }
    >
      <form id="risk-form" className="form-grid" onSubmit={submit}>
        <Field label="Title" required className="span-2">
          <Input value={form.title} onChange={set("title")} required minLength={3} placeholder="Customer can terminate on change of control" />
        </Field>
        <Field label="Type">
          <Select value={form.finding_type} onChange={set("finding_type")} options={Object.entries(FINDING_TYPES).map(([value, v]) => ({ value, label: v.label }))} />
        </Field>
        <Field label="Severity">
          <Select value={form.severity} onChange={set("severity")} options={Object.entries(SEVERITIES).map(([value, v]) => ({ value, label: v.label }))} />
        </Field>
        <Field label="Workstream">
          <Select value={form.category} onChange={set("category")} options={CATEGORY_KEYS.map((key) => ({ value: key, label: CATEGORIES[key].label }))} />
        </Field>
        <Field label="Owner">
          <Select
            value={form.owner_id}
            onChange={set("owner_id")}
            placeholder="Unassigned"
            options={(members || []).map((m) => ({ value: m.user.id, label: m.user.full_name }))}
          />
        </Field>
        <Field label="Description" required className="span-2">
          <Textarea rows={4} value={form.description} onChange={set("description")} required minLength={3} placeholder="What is the issue and why does it matter?" />
        </Field>
        <Field label="Recommendation" className="span-2">
          <Textarea rows={2} value={form.recommendation} onChange={set("recommendation")} placeholder="e.g. Seek specific indemnity / escrow; request consent before signing" />
        </Field>
        <Field label="Estimated financial impact" className="span-2">
          <Input value={form.financial_impact} onChange={set("financial_impact")} placeholder="e.g. Up to USD 9.6m annual revenue at risk" />
        </Field>
      </form>
    </Modal>
  );
}
