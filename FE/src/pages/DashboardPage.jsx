import { Activity, Briefcase, FileCheck2, ListChecks, Plus, ShieldAlert, Siren } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bar, BarChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { dashboardApi, dealsApi } from "../api/services";
import ActivityFeed from "../components/ActivityFeed";
import DealCard from "../components/deals/DealCard";
import DealFormModal from "../components/deals/DealFormModal";
import { Button, Card, EmptyState, ErrorState, PageLoader } from "../components/ui/primitives";
import { StatCard } from "../components/ui/StatCard";
import { useAuth } from "../context/AuthContext";
import { useAsync } from "../hooks/useAsync";
import { CATEGORIES, P, SEVERITIES, STAGES } from "../lib/constants";
import { greeting } from "../lib/format";

const SEVERITY_COLORS = { critical: "#e11d48", high: "#f97316", medium: "#f59e0b", low: "#38bdf8" };

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const { name, value, payload: row } = payload[0];
  return (
    <div className="chart-tooltip">
      <strong>{row.label || name}</strong>
      <span>{value}</span>
    </div>
  );
}

export default function DashboardPage() {
  const { user, can } = useAuth();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const { data, error, loading, reload } = useAsync(
    () => Promise.all([dashboardApi.summary(), dealsApi.list()]),
    [],
  );

  if (loading && !data) return <PageLoader />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  const [summary, deals] = data;
  const dealNames = Object.fromEntries(deals.map((d) => [d.id, d.code_name || d.name]));

  const severityData = Object.keys(SEVERITIES)
    .map((key) => ({
      key,
      label: SEVERITIES[key].label,
      value: summary.risks_by_severity.find((b) => b.key === key)?.count || 0,
    }))
    .filter((row) => row.value > 0);
  const categoryData = summary.documents_by_category.slice(0, 8).map((b) => ({
    key: b.key,
    label: CATEGORIES[b.key]?.label || b.key,
    value: b.count,
  }));
  const stageCounts = Object.fromEntries(summary.deals_by_stage.map((b) => [b.key, b.count]));

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">{new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" })}</p>
          <h1>
            {greeting()}, {user.full_name.split(" ")[0]}
          </h1>
          <p className="page-subtitle">Here is the state of your deal pipeline and due-diligence workstreams.</p>
        </div>
        {can(P.DEAL_CREATE) && (
          <Button icon={Plus} onClick={() => setCreating(true)}>
            New deal
          </Button>
        )}
      </header>

      <div className="stat-grid">
        <StatCard icon={Briefcase} label="Active deals" value={summary.active_deals} hint={`${summary.total_deals} total`} onClick={() => navigate("/deals")} />
        <StatCard
          icon={FileCheck2}
          tone="success"
          label="Documents indexed"
          value={summary.documents_ready}
          hint={summary.documents_processing ? `${summary.documents_processing} processing` : `${summary.documents_total} uploaded`}
        />
        <StatCard icon={ShieldAlert} tone="warning" label="Open findings" value={summary.open_risks} hint="Risks, gaps & contradictions" />
        <StatCard icon={Siren} tone="danger" label="Critical findings" value={summary.critical_risks} hint="Potential deal-breakers" />
        <StatCard icon={ListChecks} tone="info" label="Checklist completion" value={`${summary.checklist_completion}%`} hint="Across all deals" />
      </div>

      {deals.length === 0 ? (
        <Card>
          <EmptyState
            icon={Briefcase}
            title="No deals yet"
            description={
              can(P.DEAL_CREATE)
                ? "Create your first deal to open a virtual data room and start due diligence."
                : "You have not been added to a deal team yet. Ask a deal lead to add you."
            }
            action={can(P.DEAL_CREATE) && <Button icon={Plus} onClick={() => setCreating(true)}>Create a deal</Button>}
          />
        </Card>
      ) : (
        <div className="dashboard-grid">
          <div className="dashboard-main">
            <Card
              title="Deal pipeline"
              subtitle="Deals by stage"
              actions={<Link to="/deals" className="link">View all</Link>}
            >
              <div className="stage-strip">
                {STAGES.filter((s) => s.key !== "terminated").map((stage) => (
                  <div key={stage.key} className="stage-cell" data-stage={stage.key}>
                    <strong>{stageCounts[stage.key] || 0}</strong>
                    <span>{stage.label}</span>
                  </div>
                ))}
              </div>
            </Card>

            <div className="chart-row">
              <Card title="Open findings by severity" icon={ShieldAlert}>
                {severityData.length ? (
                  <div className="donut-wrap">
                    <ResponsiveContainer width="100%" height={200}>
                      <PieChart>
                        <Pie data={severityData} dataKey="value" nameKey="label" innerRadius={58} outerRadius={84} paddingAngle={3} stroke="none">
                          {severityData.map((row) => (
                            <Cell key={row.key} fill={SEVERITY_COLORS[row.key]} />
                          ))}
                        </Pie>
                        <Tooltip content={<ChartTooltip />} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="donut-center">
                      <strong>{summary.open_risks}</strong>
                      <span>open</span>
                    </div>
                    <ul className="legend">
                      {severityData.map((row) => (
                        <li key={row.key}>
                          <i style={{ background: SEVERITY_COLORS[row.key] }} />
                          {row.label}
                          <b>{row.value}</b>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <EmptyState compact icon={ShieldAlert} title="No open findings" description="Run an AI analysis on a deal to populate the risk register." />
                )}
              </Card>
              <Card title="Data room composition" icon={FileCheck2}>
                {categoryData.length ? (
                  <ResponsiveContainer width="100%" height={230}>
                    <BarChart data={categoryData} layout="vertical" margin={{ left: 8, right: 16 }}>
                      <XAxis type="number" hide allowDecimals={false} />
                      <YAxis type="category" dataKey="label" width={130} tickLine={false} axisLine={false} tick={{ fill: "var(--text-muted)", fontSize: 12 }} />
                      <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--surface-hover)" }} />
                      <Bar dataKey="value" radius={[0, 6, 6, 0]} barSize={14}>
                        {categoryData.map((row) => (
                          <Cell key={row.key} fill={CATEGORIES[row.key]?.color || "#6366f1"} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyState compact icon={FileCheck2} title="No documents yet" description="Upload documents to a deal's data room." />
                )}
              </Card>
            </div>

            <div className="section-head">
              <h2>Your deals</h2>
              <Link to="/deals" className="link">All deals →</Link>
            </div>
            <div className="deal-grid">
              {deals.slice(0, 4).map((deal) => (
                <DealCard key={deal.id} deal={deal} />
              ))}
            </div>
          </div>

          <Card title="Recent activity" icon={Activity} className="dashboard-side">
            {summary.recent_activity.length ? (
              <ActivityFeed items={summary.recent_activity} showDeal dealNames={dealNames} />
            ) : (
              <EmptyState compact icon={Activity} title="No activity yet" />
            )}
          </Card>
        </div>
      )}

      <DealFormModal open={creating} onClose={() => setCreating(false)} onSaved={(deal) => navigate(`/deals/${deal.id}`)} />
    </div>
  );
}
