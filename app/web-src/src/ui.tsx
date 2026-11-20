import React from "react";

type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger" | "subtle";
  size?: "sm" | "md";
  loading?: boolean;
};

export function Button({ variant = "subtle", size = "md", loading, children, ...rest }: ButtonProps) {
  return (
    <button className={`btn btn-${variant} btn-${size}`} disabled={rest.disabled || loading} {...rest}>
      {loading ? <span className="spinner" /> : null}
      {children}
    </button>
  );
}

export function Card({
  title,
  actions,
  children,
  className = "",
}: {
  title?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-head">
          <h3>{title}</h3>
          <div className="card-actions">{actions}</div>
        </header>
      )}
      <div className="card-body">{children}</div>
    </section>
  );
}

export function Badge({
  tone = "neutral",
  children,
  title,
}: {
  tone?: "neutral" | "good" | "warn" | "bad" | "info";
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

export function Field({
  label,
  hint,
  required,
  children,
  error,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
  error?: string;
}) {
  return (
    <label className="field">
      <span className="field-label">
        {label}
        {required ? <span className="req">*</span> : null}
      </span>
      {children}
      {hint ? <span className="field-hint">{hint}</span> : null}
      {error ? <span className="field-error">{error}</span> : null}
    </label>
  );
}

export const TextInput = (props: React.InputHTMLAttributes<HTMLInputElement>) => (
  <input className="input" {...props} />
);

export const TextArea = (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea className="input textarea" {...props} />
);

export const Select = (props: React.SelectHTMLAttributes<HTMLSelectElement>) => (
  <select className="input select" {...props} />
);

export function Checkbox({
  checked,
  onChange,
  label,
  title,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: React.ReactNode;
  title?: string;
}) {
  return (
    <label className="checkbox" title={title}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

export function Tabs({
  items,
  value,
  onChange,
}: {
  items: { id: string; label: React.ReactNode; badge?: React.ReactNode }[];
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {items.map((item) => (
        <button
          key={item.id}
          role="tab"
          aria-selected={value === item.id}
          className={`tab ${value === item.id ? "tab-active" : ""}`}
          onClick={() => onChange(item.id)}
        >
          {item.label}
          {item.badge != null ? <span className="tab-badge">{item.badge}</span> : null}
        </button>
      ))}
    </div>
  );
}

export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  wide,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  wide?: boolean;
}) {
  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className={`modal ${wide ? "modal-wide" : ""}`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="modal-head">
          <h3>{title}</h3>
          <button className="icon-btn" onClick={onClose} aria-label="close">
            ×
          </button>
        </header>
        <div className="modal-body">{children}</div>
        {footer ? <footer className="modal-foot">{footer}</footer> : null}
      </div>
    </div>
  );
}

export function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {hint ? <span className="stat-hint">{hint}</span> : null}
    </div>
  );
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: React.ReactNode }) {
  return (
    <div className="empty">
      <div className="empty-title">{title}</div>
      {hint ? <div className="empty-hint">{hint}</div> : null}
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}

export function Banner({ tone = "bad", children }: { tone?: "bad" | "warn" | "info" | "good"; children: React.ReactNode }) {
  return <div className={`banner banner-${tone}`}>{children}</div>;
}

export function Spinner() {
  return <span className="spinner" />;
}
