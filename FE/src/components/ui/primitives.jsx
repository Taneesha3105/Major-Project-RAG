import { Loader2 } from "lucide-react";
import { forwardRef } from "react";
import { classNames, initials } from "../../lib/format";

export function Button({ variant = "primary", size, icon: Icon, loading, children, className, ...props }) {
  return (
    <button
      className={classNames("btn", `btn-${variant}`, size && `btn-${size}`, className)}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading ? <Loader2 size={16} className="spin" /> : Icon && <Icon size={16} />}
      {children && <span>{children}</span>}
    </button>
  );
}

export function IconButton({ icon: Icon, label, variant = "ghost", size, className, ...props }) {
  return (
    <button
      className={classNames("icon-btn", variant, size, className)}
      aria-label={label}
      title={label}
      {...props}
    >
      <Icon size={size === "sm" ? 14 : 17} />
    </button>
  );
}

export function Badge({ tone = "neutral", children, dot, icon: Icon, className }) {
  return (
    <span className={classNames("badge", `badge-${tone}`, className)}>
      {dot && <span className="badge-dot" />}
      {Icon && <Icon size={12} />}
      {children}
    </span>
  );
}

export function Spinner({ size = 20, label }) {
  return (
    <span className="spinner-wrap" role="status">
      <Loader2 size={size} className="spin" />
      {label && <span>{label}</span>}
    </span>
  );
}

export function PageLoader({ label = "Loading…" }) {
  return (
    <div className="page-loader">
      <Spinner size={28} label={label} />
    </div>
  );
}

export function Card({ title, subtitle, actions, children, className, padded = true, icon: Icon }) {
  return (
    <section className={classNames("card", padded && "card-padded", className)}>
      {(title || actions) && (
        <header className="card-header">
          <div className="card-title-wrap">
            {Icon && (
              <span className="card-icon">
                <Icon size={16} />
              </span>
            )}
            <div>
              {title && <h3 className="card-title">{title}</h3>}
              {subtitle && <p className="card-subtitle">{subtitle}</p>}
            </div>
          </div>
          {actions && <div className="card-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function EmptyState({ icon: Icon, title, description, action, compact }) {
  return (
    <div className={classNames("empty-state", compact && "compact")}>
      {Icon && (
        <div className="empty-icon">
          <Icon size={compact ? 22 : 28} />
        </div>
      )}
      <h4>{title}</h4>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="error-state">
      <p>{error?.message || "Something went wrong."}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function Field({ label, hint, error, children, required, className }) {
  return (
    <label className={classNames("field", className)}>
      {label && (
        <span className="field-label">
          {label}
          {required && <em>*</em>}
        </span>
      )}
      {children}
      {error ? <span className="field-error">{error}</span> : hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

export const Input = forwardRef(function Input({ icon: Icon, className, ...props }, ref) {
  if (!Icon) return <input ref={ref} className={classNames("input", className)} {...props} />;
  return (
    <div className={classNames("input-with-icon", className)}>
      <Icon size={16} />
      <input ref={ref} className="input" {...props} />
    </div>
  );
});

export function Select({ options, className, placeholder, ...props }) {
  return (
    <select className={classNames("input select", className)} {...props}>
      {placeholder !== undefined && <option value="">{placeholder}</option>}
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

export function Textarea({ className, ...props }) {
  return <textarea className={classNames("input textarea", className)} {...props} />;
}

export function Avatar({ name, size = 32 }) {
  const hue = [...(name || "?")].reduce((sum, ch) => sum + ch.charCodeAt(0), 0) % 360;
  return (
    <span
      className="avatar"
      style={{ width: size, height: size, fontSize: size * 0.38, background: `hsl(${hue} 65% 52%)` }}
      aria-hidden
    >
      {initials(name) || "?"}
    </span>
  );
}

export function ProgressBar({ value, tone = "primary", size = "md" }) {
  return (
    <div className={classNames("progress", `progress-${size}`)}>
      <div className={`progress-fill tone-${tone}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export function ProgressRing({ value = 0, size = 64, stroke = 7, label, sublabel }) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, value));
  const tone = clamped >= 70 ? "var(--success)" : clamped >= 40 ? "var(--warning)" : "var(--danger)";
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={radius} strokeWidth={stroke} className="ring-track" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          stroke={tone}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - clamped / 100)}
          className="ring-value"
        />
      </svg>
      <div className="ring-label">
        <strong style={{ fontSize: size * 0.24 }}>{label ?? `${Math.round(clamped)}`}</strong>
        {sublabel && <span>{sublabel}</span>}
      </div>
    </div>
  );
}

export function Skeleton({ height = 16, width = "100%", radius = 8 }) {
  return <span className="skeleton" style={{ height, width, borderRadius: radius }} />;
}

export function Segmented({ value, onChange, options }) {
  return (
    <div className="segmented" role="tablist">
      {options.map((option) => (
        <button
          key={option.value}
          role="tab"
          aria-selected={value === option.value}
          className={classNames(value === option.value && "active")}
          onClick={() => onChange(option.value)}
        >
          {option.label}
          {option.count !== undefined && <span className="segmented-count">{option.count}</span>}
        </button>
      ))}
    </div>
  );
}
