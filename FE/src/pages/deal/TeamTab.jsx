import { UserMinus, UserPlus, Users } from "lucide-react";
import { useState } from "react";
import { dealsApi, usersApi } from "../../api/services";
import { Modal } from "../../components/ui/Overlay";
import { Avatar, Badge, Button, Card, EmptyState, ErrorState, Field, IconButton, PageLoader, Select } from "../../components/ui/primitives";
import { useAuth } from "../../context/AuthContext";
import { useToast } from "../../context/ToastContext";
import { useAsync } from "../../hooks/useAsync";
import { MEMBER_ROLES, P, ROLES } from "../../lib/constants";
import { formatDate } from "../../lib/format";
import { useDeal } from "./DealContext";

function AddMemberModal({ open, onClose, dealId, existingIds, onAdded }) {
  const toast = useToast();
  const { can } = useAuth();
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState("member");
  const [saving, setSaving] = useState(false);
  const { data: users } = useAsync(() => (open && can(P.USER_DIRECTORY) ? usersApi.list() : Promise.resolve([])), [open]);
  const candidates = (users || []).filter((u) => u.is_active && !existingIds.includes(u.id));

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      onAdded(await dealsApi.addMember(dealId, { user_id: userId, member_role: role }));
      toast.success("Team member added.");
      setUserId("");
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
      title="Add team member"
      subtitle="Members can access this deal's data room according to their role."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="member-form" loading={saving} disabled={!userId}>
            Add member
          </Button>
        </>
      }
    >
      <form id="member-form" className="stack" onSubmit={submit}>
        <Field label="User">
          <Select
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder={candidates.length ? "Select a user" : "No other users available"}
            options={candidates.map((u) => ({ value: u.id, label: `${u.full_name} · ${u.email} (${ROLES[u.role].label})` }))}
            required
          />
        </Field>
        <Field label="Deal role" hint="Observers have read-only access regardless of their platform role.">
          <Select value={role} onChange={(e) => setRole(e.target.value)} options={Object.entries(MEMBER_ROLES).map(([value, label]) => ({ value, label }))} />
        </Field>
      </form>
    </Modal>
  );
}

export default function TeamTab() {
  const { deal, can, reloadDeal } = useDeal();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const { data: members, error, loading, reload, setData } = useAsync(() => dealsApi.members(deal.id), [deal.id]);
  if (loading && !members) return <PageLoader />;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  const remove = async (member) => {
    try {
      await dealsApi.removeMember(deal.id, member.id);
      setData((list) => list.filter((m) => m.id !== member.id));
      reloadDeal();
    } catch (err) {
      toast.error(err);
    }
  };

  return (
    <Card
      title="Deal team"
      subtitle="Only members (and administrators) can see this deal."
      icon={Users}
      actions={
        can(P.MEMBERS_MANAGE) && (
          <Button icon={UserPlus} onClick={() => setAdding(true)}>
            Add member
          </Button>
        )
      }
    >
      {members.length === 0 ? (
        <EmptyState icon={Users} title="No members" />
      ) : (
        <ul className="member-list">
          {members.map((member) => (
            <li key={member.id}>
              <Avatar name={member.user.full_name} size={40} />
              <div className="member-info">
                <strong>{member.user.full_name}</strong>
                <span>{member.user.email}</span>
              </div>
              <Badge tone={ROLES[member.user.role].tone}>{ROLES[member.user.role].label}</Badge>
              <Badge tone={member.member_role === "lead" ? "purple" : "neutral"}>{MEMBER_ROLES[member.member_role]}</Badge>
              <span className="muted hide-sm">Added {formatDate(member.added_at)}</span>
              {can(P.MEMBERS_MANAGE) && <IconButton icon={UserMinus} label="Remove from deal" variant="ghost danger" onClick={() => remove(member)} />}
            </li>
          ))}
        </ul>
      )}
      <AddMemberModal
        open={adding}
        onClose={() => setAdding(false)}
        dealId={deal.id}
        existingIds={members.map((m) => m.user.id)}
        onAdded={(member) => {
          setData((list) => [...list, member]);
          reloadDeal();
        }}
      />
    </Card>
  );
}
