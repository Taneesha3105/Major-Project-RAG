import { Briefcase, Plus, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { dealsApi } from "../api/services";
import DealCard from "../components/deals/DealCard";
import DealFormModal from "../components/deals/DealFormModal";
import { Button, Card, EmptyState, ErrorState, Input, Segmented, Skeleton } from "../components/ui/primitives";
import { useAuth } from "../context/AuthContext";
import { useAsync } from "../hooks/useAsync";
import { P, STAGES } from "../lib/constants";

export default function DealsPage() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("search") || "");
  const [stage, setStage] = useState("");
  const [creating, setCreating] = useState(false);
  const urlSearch = params.get("search") || "";

  useEffect(() => setSearch(urlSearch), [urlSearch]);

  const { data: deals, error, loading, reload } = useAsync(
    () => dealsApi.list({ search: urlSearch, stage }),
    [urlSearch, stage],
  );

  const applySearch = (event) => {
    event.preventDefault();
    setParams(search ? { search } : {});
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Portfolio</p>
          <h1>Deals</h1>
          <p className="page-subtitle">Every transaction you are working on, with live diligence readiness.</p>
        </div>
        {can(P.DEAL_CREATE) && (
          <Button icon={Plus} onClick={() => setCreating(true)}>
            New deal
          </Button>
        )}
      </header>

      <div className="toolbar">
        <form onSubmit={applySearch} className="toolbar-search">
          <Input icon={Search} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by deal, target, acquirer or code name" />
        </form>
        <Segmented
          value={stage}
          onChange={setStage}
          options={[{ value: "", label: "All" }, ...STAGES.filter((s) => s.key !== "terminated").map((s) => ({ value: s.key, label: s.label }))]}
        />
      </div>

      {error ? (
        <ErrorState error={error} onRetry={reload} />
      ) : loading && !deals ? (
        <div className="deal-grid">
          {[0, 1, 2].map((i) => (
            <div key={i} className="deal-card">
              <Skeleton height={18} width="40%" />
              <Skeleton height={24} width="70%" />
              <Skeleton height={14} width="55%" />
            </div>
          ))}
        </div>
      ) : deals.length === 0 ? (
        <Card>
          <EmptyState
            icon={Briefcase}
            title={urlSearch || stage ? "No deals match your filters" : "No deals yet"}
            description={urlSearch || stage ? "Try a different search or stage." : "Create a deal to open its virtual data room."}
            action={can(P.DEAL_CREATE) && !urlSearch && <Button icon={Plus} onClick={() => setCreating(true)}>Create a deal</Button>}
          />
        </Card>
      ) : (
        <div className="deal-grid">
          {deals.map((deal) => (
            <DealCard key={deal.id} deal={deal} />
          ))}
        </div>
      )}

      <DealFormModal open={creating} onClose={() => setCreating(false)} onSaved={(deal) => navigate(`/deals/${deal.id}`)} />
    </div>
  );
}
