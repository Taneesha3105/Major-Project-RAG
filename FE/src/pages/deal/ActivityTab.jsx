import { History } from "lucide-react";
import { dealsApi } from "../../api/services";
import ActivityFeed from "../../components/ActivityFeed";
import { Card, EmptyState, ErrorState, PageLoader } from "../../components/ui/primitives";
import { useAsync } from "../../hooks/useAsync";
import { useDeal } from "./DealContext";

export default function ActivityTab() {
  const { deal } = useDeal();
  const { data, error, loading, reload } = useAsync(() => dealsApi.activity(deal.id, 200), [deal.id]);
  if (loading && !data) return <PageLoader />;
  if (error) return <ErrorState error={error} onRetry={reload} />;
  return (
    <Card title="Audit trail" subtitle="Every upload, question, finding and decision on this deal — for defensibility." icon={History}>
      {data.length ? <ActivityFeed items={data} /> : <EmptyState icon={History} title="No activity yet" />}
    </Card>
  );
}
