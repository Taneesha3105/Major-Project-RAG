import { Search, UserPlus, UsersRound } from "lucide-react";
import { useState } from "react";
import { usersApi } from "../api/services";
import { Modal } from "../components/ui/Overlay";
import { Avatar, Badge, Button, Card, ErrorState, Field, Input, PageLoader, Select } from "../components/ui/primitives";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import { useAsync } from "../hooks/useAsync";
import { ROLES } from "../lib/constants";
import { formatDate, timeAgo } from "../lib/format";

const ROLE_HELP = {
  admin: "Full platform access including user management.",
  deal_lead: "Creates deals, manages teams, uploads, analyses.",
  analyst: "Uploads documents, uses the AI, edits findings & checklist.",
  viewer: "Read-only access plus the AI assistant.",
};

function CreateUserModal({ open, onClose, onCreated }) {
  const toast = useToast();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", role: "analyst", job_title: "" });
  const [saving, setSaving] = useState(false);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    try {
      onCreated(await usersApi.create({ ...form, job_title: form.job_title || null }));
      toast.success("User created.");
      setForm({ full_name: "", email: "", password: "", role: "analyst", job_title: "" });
      onClose();
    } catch (error) {
      toast.error(error.message.replace("Value error, ", ""));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Invite user"
      subtitle="Create an account and share the temporary password securely."
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="user-form" loading={saving}>
            Create user
          </Button>
        </>
      }
    >
      <form id="user-form" className="form-grid" onSubmit={submit}>
        <Field label="Full name" required>
          <Input value={form.full_name} onChange={set("full_name")} required minLength={2} />
        </Field>
        <Field label="Email" required>
          <Input type="email" value={form.email} onChange={set("email")} required />
        </Field>
        <Field label="Temporary password" required hint="8+ characters, letters and numbers.">
          <Input type="text" value={form.password} onChange={set("password")} required minLength={8} />
        </Field>
        <Field label="Job title">
          <Input value={form.job_title} onChange={set("job_title")} />
        </Field>
        <Field label="Role" className="span-2" hint={ROLE_HELP[form.role]}>
          <Select value={form.role} onChange={set("role")} options={Object.entries(ROLES).map(([value, v]) => ({ value, label: v.label }))} />
        </Field>
      </form>
    </Modal>
  );
}

export default function AdminUsersPage() {
  const { user: me } = useAuth();
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const { data: users, error, loading, reload, setData } = useAsync(() => usersApi.list(), []);
  if (loading && !users) return <PageLoader />;
  if (error) return <ErrorState error={error} onRetry={reload} />;

  const update = async (user, payload) => {
    try {
      const updated = await usersApi.update(user.id, payload);
      setData((list) => list.map((u) => (u.id === user.id ? updated : u)));
      toast.success(`${updated.full_name} updated.`);
    } catch (err) {
      toast.error(err);
    }
  };

  const visible = users.filter((u) => `${u.full_name} ${u.email}`.toLowerCase().includes(query.toLowerCase()));
  const roleCounts = Object.fromEntries(Object.keys(ROLES).map((r) => [r, users.filter((u) => u.role === r).length]));

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Administration</p>
          <h1>Users &amp; roles</h1>
          <p className="page-subtitle">Control who can access the platform and what they can do.</p>
        </div>
        <Button icon={UserPlus} onClick={() => setCreating(true)}>
          Invite user
        </Button>
      </header>

      <div className="role-grid">
        {Object.entries(ROLES).map(([key, role]) => (
          <div key={key} className="role-card">
            <Badge tone={role.tone}>{role.label}</Badge>
            <strong>{roleCounts[key]}</strong>
            <p>{ROLE_HELP[key]}</p>
          </div>
        ))}
      </div>

      <Card padded={false}>
        <div className="table-toolbar">
          <div className="table-toolbar-left">
            <h3>
              <UsersRound size={16} /> All users
            </h3>
            <span className="muted">{users.length} accounts</span>
          </div>
          <Input icon={Search} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search name or email" className="table-search" />
        </div>
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>User</th>
                <th>Role</th>
                <th>Status</th>
                <th className="hide-sm">Last sign-in</th>
                <th className="hide-sm">Joined</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((user) => (
                <tr key={user.id}>
                  <td>
                    <div className="doc-name">
                      <Avatar name={user.full_name} size={34} />
                      <div>
                        <strong>
                          {user.full_name} {user.id === me.id && <Badge tone="neutral">You</Badge>}
                        </strong>
                        <span>
                          {user.email}
                          {user.job_title && ` · ${user.job_title}`}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td>
                    <Select
                      value={user.role}
                      disabled={user.id === me.id}
                      onChange={(e) => update(user, { role: e.target.value })}
                      options={Object.entries(ROLES).map(([value, v]) => ({ value, label: v.label }))}
                      className="compact-select"
                    />
                  </td>
                  <td>
                    <label className="switch" title={user.is_active ? "Deactivate" : "Activate"}>
                      <input type="checkbox" checked={user.is_active} disabled={user.id === me.id} onChange={(e) => update(user, { is_active: e.target.checked })} />
                      <span />
                      <em>{user.is_active ? "Active" : "Inactive"}</em>
                    </label>
                  </td>
                  <td className="hide-sm muted">{user.last_login_at ? timeAgo(user.last_login_at) : "Never"}</td>
                  <td className="hide-sm muted">{formatDate(user.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <CreateUserModal open={creating} onClose={() => setCreating(false)} onCreated={(user) => setData((list) => [...list, user])} />
    </div>
  );
}
