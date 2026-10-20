import { Bot, FileSearch, Plus, ShieldAlert, Sparkles, User } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { dealsApi, diligenceApi } from "../../api/services";
import RiskDrawer from "../../components/risks/RiskDrawer";
import RiskFormModal from "../../components/risks/RiskFormModal";
import { ConfirmDialog } from "../../components/ui/Overlay";
import { Badge, Button, Card, EmptyState, ErrorState, PageLoader, ProgressBar, Select } from "../../components/ui/primitives";
import { useToast } from "../../context/ToastContext";
import { useAsync, useInterval } from "../../hooks/useAsync";
import { CATEGORIES, FINDING_STATUS, FINDING_TYPES, P, SEVERITIES } from "../../lib/constants";
import { classNames, timeAgo } from "../../lib/format";
import { useDeal } from "./DealContext";

export default function RisksTab() {
  const { deal, can, reloadDeal } = useDeal();
  const toast = useToast();
  const [filters, setFilters] = useState({ severity: "", finding_type: "", status: "active", category: "" });
  const [selectedId, setSelectedId] = useState(null);
  const [creating, setCreating] = useState(false);
  const [toDelete, setToDelete] = useState(null);
  const [run, setRun] = useState(null);
  const [starting, setStarting] = useState(false);

  const { data, error, loading, reload, setData } = useAsync(
    () => Promise.all([diligenceApi.risks(deal.id), dealsApi.members(deal.id), diligenceApi.analysisRuns(deal.id)]),
    [deal.id],
  );

  useEffect(() => {
    if (data) setRun(data[2][0] || null);
  }, [data]);

  const running = run && ["queued", "running"].includes(run.status);
  useInterval(
    async () => {
      const latest = await diligenceApi.analysisRun(deal.id, run.id);
      setRun(latest);
      if (latest.status === "completed") {
        toast.success(`AI analysis found ${latest.findings_count} finding(s).`, "Analysis complete");
        reload({ silent: true });
        reloadDeal();
      } else if (latest.status === "failed") {
        toast.error(latest.error_message || "Analysis failed.", "Analysis failed");
      }
    },
    2500,
    Boolean(running),
  );

  const findings = data?.[0] || [];
  const members = data?.[1] || [];
  const counts = useMemo(() => {
    const active = findings.filter((f) => ["open", "under_review"].includes(f.status));
    return Object.fromEntries(Object.keys(SEVERITIES).map((key) => [key, active.filter((f) => f.severity === key).length]));
  }, [findings]);

  if (loading && !data) return <PageLoader />;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  const visible = findings
    .filter((f) => !filters.severity || f.severity === filters.severity)
    .filter((f) => !filters.finding_type || f.finding_type === filters.finding_type)
    .filter((f) => !filters.category || f.category === filters.category)
    .filter((f) =>
      filters.status === "active" ? ["open", "under_review"].includes(f.status) : !filters.status || f.status === filters.status,
    )
    .sort((a, b) => SEVERITIES[a.severity].rank - SEVERITIES[b.severity].rank || new Date(b.created_at) - new Date(a.created_at));
  const selected = findings.find((f) => f.id === selectedId);

  const setFindings = (updater) => setData(([list, ...rest]) => [updater(list), ...rest]);
  const replaceFinding = (finding) => {
    setFindings((list) => list.map((f) => (f.id === finding.id ? finding : f)));
    reloadDeal();
  };

  const startAnalysis = async () => {
    setStarting(true);
    try {
      setRun(await diligenceApi.startAnalysis(deal.id, { categories: [], replace_previous_ai_findings: true }));
      toast.info("Gemini is reviewing every workstream in the data room.", "AI analysis started");
    } catch (err) {
      toast.error(err);
    } finally {
      setStarting(false);
    }
  };

  const confirmDelete = async () => {
    try {
      await diligenceApi.removeRisk(deal.id, toDelete.id);
      setFindings((list) => list.filter((f) => f.id !== toDelete.id));
      setSelectedId(null);
      setToDelete(null);
      reloadDeal();
      toast.success("Finding deleted.");
    } catch (err) {
      toast.error(err);
    }
  };

  const setFilter = (key) => (e) => setFilters({ ...filters, [key]: e.target.value });

  return (
    <div className="risks">
      <div className="risk-summary">
        {Object.entries(SEVERITIES).map(([key, meta]) => (
          <button
            key={key}
            className={classNames("sev-tile", `sev-${key}`, filters.severity === key && "active")}
            onClick={() => setFilters({ ...filters, severity: filters.severity === key ? "" : key })}
          >
            <span>{meta.label}</span>
            <strong>{counts[key]}</strong>
            <small>open</small>
          </button>
        ))}
        <Card className="analysis-card" padded>
          <div className="analysis-card-inner">
            <span className="analysis-icon">
              <Sparkles size={20} />
            </span>
            <div className="analysis-text">
              <strong>AI due-diligence analysis</strong>
              {running ? (
                <>
                  <span>Reviewing workstreams… {run.progress}%</span>
                  <ProgressBar value={Math.max(run.progress, 6)} size="sm" />
                </>
              ) : run ? (
                <span>
                  Last run {timeAgo(run.completed_at || run.created_at)} ·{" "}
                  {run.status === "failed" ? <em className="text-danger">failed</em> : `${run.findings_count} findings`}
                </span>
              ) : (
                <span>Detect risks, contradictions and gaps across the data room.</span>
              )}
            </div>
            {can(P.ANALYSIS_RUN) && (
              <Button icon={Bot} onClick={startAnalysis} loading={starting || running} disabled={deal.stats.ready_document_count === 0}>
                {running ? "Running" : run ? "Re-run" : "Run analysis"}
              </Button>
            )}
          </div>
        </Card>
      </div>

      <Card padded={false}>
        <div className="table-toolbar">
          <div className="table-toolbar-left">
            <h3>Risk register</h3>
            <span className="muted">{visible.length} shown</span>
          </div>
          <div className="filters">
            <Select value={filters.status} onChange={setFilter("status")} options={[{ value: "active", label: "Open & under review" }, { value: "", label: "All statuses" }, ...Object.entries(FINDING_STATUS).map(([value, v]) => ({ value, label: v.label }))]} />
            <Select value={filters.finding_type} onChange={setFilter("finding_type")} placeholder="All types" options={Object.entries(FINDING_TYPES).map(([value, v]) => ({ value, label: v.label }))} />
            <Select value={filters.category} onChange={setFilter("category")} placeholder="All workstreams" options={Object.keys(CATEGORIES).map((key) => ({ value: key, label: CATEGORIES[key].label }))} />
            {can(P.FINDING_EDIT) && (
              <Button variant="secondary" icon={Plus} onClick={() => setCreating(true)}>
                Add finding
              </Button>
            )}
          </div>
        </div>

        {visible.length === 0 ? (
          <EmptyState
            icon={ShieldAlert}
            title={findings.length ? "No findings match these filters" : "No findings yet"}
            description={findings.length ? "Adjust the filters above." : "Run the AI analysis or log findings manually as you review documents."}
          />
        ) : (
          <ul className="finding-list">
            {visible.map((finding) => (
              <li key={finding.id} onClick={() => setSelectedId(finding.id)} className={`sev-row-${finding.severity}`}>
                <span className={`sev-bar sev-${finding.severity}`} />
                <div className="finding-main">
                  <div className="finding-title">
                    <strong>{finding.title}</strong>
                    <Badge tone={FINDING_TYPES[finding.finding_type].tone}>{FINDING_TYPES[finding.finding_type].label}</Badge>
                  </div>
                  <p>{finding.description}</p>
                  <div className="finding-meta">
                    <span className="cat-pill">
                      <i style={{ background: CATEGORIES[finding.category]?.color }} />
                      {CATEGORIES[finding.category]?.label}
                    </span>
                    <span>{finding.source === "ai" ? <Bot size={12} /> : <User size={12} />} {finding.source === "ai" ? "AI" : "Manual"}</span>
                    {finding.citations.length > 0 && (
                      <span>
                        <FileSearch size={12} /> {finding.citations.length} source{finding.citations.length > 1 ? "s" : ""}
                      </span>
                    )}
                    {finding.owner && <span>Owner: {finding.owner.full_name}</span>}
                  </div>
                </div>
                <div className="finding-side">
                  <Badge tone={SEVERITIES[finding.severity].tone}>{SEVERITIES[finding.severity].label}</Badge>
                  <Badge tone={FINDING_STATUS[finding.status].tone} dot>
                    {FINDING_STATUS[finding.status].label}
                  </Badge>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {selected && (
        <RiskDrawer
          dealId={deal.id}
          finding={selected}
          members={members}
          canEdit={can(P.FINDING_EDIT)}
          onClose={() => setSelectedId(null)}
          onChanged={replaceFinding}
          onDelete={setToDelete}
        />
      )}
      <RiskFormModal
        open={creating}
        onClose={() => setCreating(false)}
        dealId={deal.id}
        members={members}
        onSaved={(finding) => {
          setFindings((list) => [finding, ...list]);
          reloadDeal();
        }}
      />
      <ConfirmDialog open={Boolean(toDelete)} onClose={() => setToDelete(null)} onConfirm={confirmDelete} title="Delete finding?" message={`"${toDelete?.title}" will be removed from the risk register.`} />
    </div>
  );
}
