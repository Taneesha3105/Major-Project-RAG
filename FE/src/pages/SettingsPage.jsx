import { Cpu, KeyRound, Moon, Palette, Sun, UserRound } from "lucide-react";
import { useState } from "react";
import { authApi, dashboardApi } from "../api/services";
import { Avatar, Badge, Button, Card, Field, Input, Segmented } from "../components/ui/primitives";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import { useToast } from "../context/ToastContext";
import { useAsync } from "../hooks/useAsync";
import { ROLES } from "../lib/constants";

export default function SettingsPage() {
  const { user, setUser } = useAuth();
  const { theme, setTheme } = useTheme();
  const toast = useToast();
  const [profile, setProfile] = useState({ full_name: user.full_name, job_title: user.job_title || "", organization: user.organization || "" });
  const [passwords, setPasswords] = useState({ current_password: "", new_password: "", confirm: "" });
  const [saving, setSaving] = useState("");
  const { data: status } = useAsync(() => dashboardApi.status(), []);

  const saveProfile = async (event) => {
    event.preventDefault();
    setSaving("profile");
    try {
      setUser(await authApi.updateMe({ ...profile, job_title: profile.job_title || null, organization: profile.organization || null }));
      toast.success("Profile updated.");
    } catch (error) {
      toast.error(error);
    } finally {
      setSaving("");
    }
  };

  const changePassword = async (event) => {
    event.preventDefault();
    if (passwords.new_password !== passwords.confirm) {
      toast.error("New passwords do not match.");
      return;
    }
    setSaving("password");
    try {
      await authApi.changePassword({ current_password: passwords.current_password, new_password: passwords.new_password });
      setPasswords({ current_password: "", new_password: "", confirm: "" });
      toast.success("Password changed.");
    } catch (error) {
      toast.error(error.message.replace("Value error, ", ""));
    } finally {
      setSaving("");
    }
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Account</p>
          <h1>Settings</h1>
        </div>
      </header>
      <div className="settings-grid">
        <Card title="Profile" icon={UserRound}>
          <div className="profile-head">
            <Avatar name={user.full_name} size={56} />
            <div>
              <strong>{user.full_name}</strong>
              <span>{user.email}</span>
              <Badge tone={ROLES[user.role].tone}>{ROLES[user.role].label}</Badge>
            </div>
          </div>
          <form className="stack" onSubmit={saveProfile}>
            <Field label="Full name">
              <Input value={profile.full_name} onChange={(e) => setProfile({ ...profile, full_name: e.target.value })} required minLength={2} />
            </Field>
            <div className="form-row">
              <Field label="Job title">
                <Input value={profile.job_title} onChange={(e) => setProfile({ ...profile, job_title: e.target.value })} />
              </Field>
              <Field label="Organisation">
                <Input value={profile.organization} onChange={(e) => setProfile({ ...profile, organization: e.target.value })} />
              </Field>
            </div>
            <div className="right">
              <Button type="submit" loading={saving === "profile"}>
                Save profile
              </Button>
            </div>
          </form>
        </Card>

        <Card title="Security" icon={KeyRound}>
          <form className="stack" onSubmit={changePassword}>
            <Field label="Current password">
              <Input type="password" value={passwords.current_password} onChange={(e) => setPasswords({ ...passwords, current_password: e.target.value })} required autoComplete="current-password" />
            </Field>
            <Field label="New password" hint="At least 8 characters with letters and numbers.">
              <Input type="password" value={passwords.new_password} onChange={(e) => setPasswords({ ...passwords, new_password: e.target.value })} required autoComplete="new-password" />
            </Field>
            <Field label="Confirm new password">
              <Input type="password" value={passwords.confirm} onChange={(e) => setPasswords({ ...passwords, confirm: e.target.value })} required autoComplete="new-password" />
            </Field>
            <div className="right">
              <Button type="submit" loading={saving === "password"}>
                Change password
              </Button>
            </div>
          </form>
        </Card>

        <Card title="Appearance" icon={Palette}>
          <Segmented
            value={theme}
            onChange={setTheme}
            options={[
              { value: "light", label: <><Sun size={14} /> Light</> },
              { value: "dark", label: <><Moon size={14} /> Dark</> },
            ]}
          />
        </Card>

        <Card title="AI & system" icon={Cpu} subtitle="Models powering this workspace">
          {status ? (
            <dl className="facts">
              <div>
                <dt>LLM</dt>
                <dd>
                  Gemini · {status.llm_model}{" "}
                  <Badge tone={status.llm_configured ? "success" : "danger"}>{status.llm_configured ? "Connected" : "Not configured"}</Badge>
                </dd>
              </div>
              <div>
                <dt>Embeddings</dt>
                <dd>{status.embedding_model}</dd>
              </div>
              <div>
                <dt>Reranker</dt>
                <dd>{status.reranker_model ? `FlashRank · ${status.reranker_model}` : "Disabled"}</dd>
              </div>
              <div>
                <dt>OCR</dt>
                <dd>{status.ocr_engine ? (status.ocr_engine === "rapidocr" ? "RapidOCR (PP-OCR, local)" : "Gemini Vision") : "Disabled"}</dd>
              </div>
              <div>
                <dt>Database</dt>
                <dd>
                  PostgreSQL + pgvector <Badge tone={status.database ? "success" : "danger"}>{status.database ? "Healthy" : "Down"}</Badge>
                </dd>
              </div>
            </dl>
          ) : (
            <p className="muted">Loading…</p>
          )}
        </Card>
      </div>
    </div>
  );
}
