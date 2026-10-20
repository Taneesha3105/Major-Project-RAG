import { classNames } from "../../lib/format";

export function StatCard({ icon: Icon, label, value, hint, tone = "primary", onClick }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag className={classNames("stat-card", onClick && "clickable")} onClick={onClick}>
      <span className={`stat-icon tone-${tone}`}>
        <Icon size={18} />
      </span>
      <div className="stat-body">
        <span className="stat-label">{label}</span>
        <strong className="stat-value">{value}</strong>
        {hint && <span className="stat-hint">{hint}</span>}
      </div>
    </Tag>
  );
}
