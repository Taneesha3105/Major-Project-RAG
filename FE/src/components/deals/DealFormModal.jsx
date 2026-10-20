import { useEffect, useState } from "react";
import { dealsApi } from "../../api/services";
import { useToast } from "../../context/ToastContext";
import { DEAL_TYPES, STAGES } from "../../lib/constants";
import { Modal } from "../ui/Overlay";
import { Button, Field, Input, Select, Textarea } from "../ui/primitives";

const EMPTY = {
  name: "",
  code_name: "",
  deal_type: "acquisition",
  stage: "due_diligence",
  acquirer_name: "",
  target_name: "",
  target_industry: "",
  target_country: "",
  deal_value: "",
  currency: "USD",
  expected_close_date: "",
  description: "",
  seed_checklist: true,
};

const CURRENCIES = ["USD", "EUR", "GBP", "INR", "JPY", "CHF", "AUD", "CAD", "SGD", "AED"];

export default function DealFormModal({ open, onClose, deal, onSaved }) {
  const toast = useToast();
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const editing = Boolean(deal);

  useEffect(() => {
    if (!open) return;
    setForm(
      deal
        ? Object.fromEntries(Object.keys(EMPTY).map((key) => [key, deal[key] ?? EMPTY[key]]))
        : EMPTY,
    );
  }, [open, deal]);

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    const payload = {
      ...form,
      deal_value: form.deal_value === "" ? null : Number(form.deal_value),
      expected_close_date: form.expected_close_date || null,
      code_name: form.code_name || null,
      target_industry: form.target_industry || null,
      target_country: form.target_country || null,
      description: form.description || null,
    };
    if (editing) delete payload.seed_checklist;
    try {
      const saved = editing ? await dealsApi.update(deal.id, payload) : await dealsApi.create(payload);
      toast.success(editing ? "Deal updated." : "Deal created with a standard diligence checklist.");
      onSaved?.(saved);
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
      title={editing ? "Edit deal" : "New deal"}
      subtitle={editing ? deal.name : "Set up a workspace for a merger or acquisition."}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="deal-form" loading={saving}>
            {editing ? "Save changes" : "Create deal"}
          </Button>
        </>
      }
    >
      <form id="deal-form" className="form-grid" onSubmit={submit}>
        <Field label="Deal name" required className="span-2">
          <Input value={form.name} onChange={set("name")} placeholder="Acquisition of Nimbus Analytics" required minLength={2} />
        </Field>
        <Field label="Code name" hint="Used to keep the target confidential.">
          <Input value={form.code_name} onChange={set("code_name")} placeholder="ATLAS" maxLength={60} />
        </Field>
        <Field label="Deal type">
          <Select value={form.deal_type} onChange={set("deal_type")} options={Object.entries(DEAL_TYPES).map(([value, label]) => ({ value, label }))} />
        </Field>
        <Field label="Acquirer / buyer" required>
          <Input value={form.acquirer_name} onChange={set("acquirer_name")} placeholder="Orion Holdings" required />
        </Field>
        <Field label="Target company" required>
          <Input value={form.target_name} onChange={set("target_name")} placeholder="Nimbus Analytics Ltd" required />
        </Field>
        <Field label="Target industry">
          <Input value={form.target_industry} onChange={set("target_industry")} placeholder="Software / SaaS" />
        </Field>
        <Field label="Target country">
          <Input value={form.target_country} onChange={set("target_country")} placeholder="United Kingdom" />
        </Field>
        <Field label="Deal value">
          <div className="input-group">
            <Select value={form.currency} onChange={set("currency")} options={CURRENCIES.map((c) => ({ value: c, label: c }))} />
            <Input type="number" min="0" step="any" value={form.deal_value} onChange={set("deal_value")} placeholder="185000000" />
          </div>
        </Field>
        <Field label="Stage">
          <Select value={form.stage} onChange={set("stage")} options={STAGES.map((s) => ({ value: s.key, label: s.label }))} />
        </Field>
        <Field label="Expected close date">
          <Input type="date" value={form.expected_close_date || ""} onChange={set("expected_close_date")} />
        </Field>
        <Field label="Description / investment thesis" className="span-2">
          <Textarea rows={3} value={form.description || ""} onChange={set("description")} placeholder="Strategic rationale, scope, key considerations…" />
        </Field>
        {!editing && (
          <label className="checkbox span-2">
            <input type="checkbox" checked={form.seed_checklist} onChange={set("seed_checklist")} />
            <span>
              <strong>Add the standard M&amp;A due-diligence request list</strong>
              <small>42 items across financial, tax, legal, contracts, HR, IP, IT and regulatory workstreams.</small>
            </span>
          </label>
        )}
      </form>
    </Modal>
  );
}
