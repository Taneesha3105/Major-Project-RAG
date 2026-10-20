import {
  Activity,
  Bot,
  Briefcase,
  CheckSquare,
  FileUp,
  LogIn,
  MessageSquare,
  ShieldAlert,
  UserPlus,
} from "lucide-react";
import { timeAgo } from "../lib/format";

const ICONS = {
  document: FileUp,
  chat: MessageSquare,
  analysis: Bot,
  finding: ShieldAlert,
  checklist: CheckSquare,
  deal: Briefcase,
  user: LogIn,
};

function iconFor(action) {
  if (action.startsWith("deal.member")) return UserPlus;
  return ICONS[action.split(".")[0]] || Activity;
}

export default function ActivityFeed({ items, showDeal = false, dealNames = {} }) {
  return (
    <ol className="activity">
      {items.map((item) => {
        const Icon = iconFor(item.action);
        return (
          <li key={item.id}>
            <span className={`activity-icon a-${item.action.split(".")[0]}`}>
              <Icon size={14} />
            </span>
            <div>
              <p>{item.summary}</p>
              <span>
                {timeAgo(item.created_at)}
                {item.user_name && ` · ${item.user_name}`}
                {showDeal && item.deal_id && dealNames[item.deal_id] && ` · ${dealNames[item.deal_id]}`}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
