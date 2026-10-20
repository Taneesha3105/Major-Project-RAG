import { Building2, Briefcase, Lock, Mail, User } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button, Field, Input } from "../components/ui/primitives";
import { useAuth } from "../context/AuthContext";
import AuthLayout from "../layouts/AuthLayout";

function passwordStrength(password) {
  let score = 0;
  if (password.length >= 8) score += 1;
  if (password.length >= 12) score += 1;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score += 1;
  if (/\d/.test(password)) score += 1;
  if (/[^A-Za-z0-9]/.test(password)) score += 1;
  return score;
}

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", organization: "", job_title: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const strength = passwordStrength(form.password);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await register({
        ...form,
        organization: form.organization || null,
        job_title: form.job_title || null,
      });
      navigate("/", { replace: true });
    } catch (err) {
      setError(err.message.replace("Value error, ", ""));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthLayout>
      <form className="auth-card" onSubmit={submit}>
        <div className="auth-card-head">
          <h2>Create your account</h2>
          <p>New accounts join as analysts. An administrator can change your role.</p>
        </div>
        {error && <div className="alert alert-danger">{error}</div>}
        <Field label="Full name" required>
          <Input icon={User} value={form.full_name} onChange={set("full_name")} placeholder="Priya Sharma" required minLength={2} />
        </Field>
        <Field label="Work email" required>
          <Input icon={Mail} type="email" value={form.email} onChange={set("email")} placeholder="you@company.com" required />
        </Field>
        <div className="form-row">
          <Field label="Organisation">
            <Input icon={Building2} value={form.organization} onChange={set("organization")} placeholder="Firm or company" />
          </Field>
          <Field label="Job title">
            <Input icon={Briefcase} value={form.job_title} onChange={set("job_title")} placeholder="M&A Analyst" />
          </Field>
        </div>
        <Field label="Password" required hint="At least 8 characters with letters and numbers.">
          <Input icon={Lock} type="password" value={form.password} onChange={set("password")} required autoComplete="new-password" />
        </Field>
        {form.password && (
          <div className="strength">
            {[0, 1, 2, 3, 4].map((i) => (
              <span key={i} className={i < strength ? `on s${strength}` : ""} />
            ))}
            <em>{["Very weak", "Weak", "Fair", "Good", "Strong", "Excellent"][strength]}</em>
          </div>
        )}
        <Button type="submit" loading={loading} className="btn-block btn-lg">
          Create account
        </Button>
        <p className="auth-switch">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
