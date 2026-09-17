import { useEffect, useRef, type ReactNode } from "react";
import {
  ArrowUpRight,
  Check,
  ChevronRight,
  Loader2,
  Search,
  X,
} from "lucide-react";
import { human } from "./api";

export function Badge({ status }: { status: string }) {
  const good = [
    "AVAILABLE",
    "COMPLETED",
    "APPROVED",
    "PAID",
    "DELIVERED",
    "ACTIVE",
    "HEALTHY",
    "ENABLED",
  ];
  const warn = [
    "PENDING",
    "RESERVED",
    "UNDER_REVIEW",
    "WAITING_RECEIPT",
    "DELIVERING",
    "CREATED",
  ];
  const bad = ["FAILED", "REJECTED", "INVALID", "QUARANTINED", "BLOCKED"];
  return (
    <span
      className={`badge ${good.includes(status) ? "good" : warn.includes(status) ? "warn" : bad.includes(status) ? "bad" : "neutral"}`}
    >
      <i />
      {human(status)}
    </span>
  );
}

export function Modal({
  title,
  subtitle,
  children,
  close,
  wide = false,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  close: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const before = document.activeElement as HTMLElement;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      if (event.key === "Tab") {
        const elements = ref.current?.querySelectorAll<HTMLElement>(
          "button:not(:disabled), input, select, textarea, a[href]",
        );
        if (!elements?.length) return;
        const first = elements[0],
          last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        }
        if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    ref.current?.querySelector<HTMLElement>("input, button")?.focus();
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      before?.focus();
    };
  }, [close]);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        ref={ref}
        className={`modal ${wide ? "wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal-header">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button
            className="icon-button"
            onClick={close}
            aria-label="Close dialog"
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function SearchBox({
  value,
  onChange,
  placeholder = "Search…",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="search-box">
      <Search size={17} />
      <input
        aria-label={placeholder}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button onClick={() => onChange("")} aria-label="Clear search">
          <X size={14} />
        </button>
      )}
    </div>
  );
}
export function Empty({
  title = "Nothing here yet",
  text = "Your results will appear here.",
}: {
  title?: string;
  text?: string;
}) {
  return (
    <div className="empty-state">
      <Search size={26} />
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading">
      <Loader2 size={24} className="spin" /> Loading workspace…
    </div>
  );
}
export function ErrorBox({ message }: { message: string }) {
  return message ? (
    <div className="error-box" role="alert">
      {message}
    </div>
  ) : null;
}
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions && <div className="heading-actions">{actions}</div>}
    </div>
  );
}
export function PanelHeading({
  title,
  subtitle,
  action,
  onAction,
}: {
  title: string;
  subtitle?: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div className="panel-heading">
      <div>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {action && (
        <button className="text-button" onClick={onAction}>
          {action}
          <ChevronRight size={15} />
        </button>
      )}
    </div>
  );
}
export function Submit({
  busy,
  children,
}: {
  busy: boolean;
  children: ReactNode;
}) {
  return (
    <button className="button primary" type="submit" disabled={busy}>
      {busy ? <Loader2 size={16} className="spin" /> : <Check size={16} />}
      {children}
    </button>
  );
}
export function Trend({ children }: { children: ReactNode }) {
  return (
    <span className="trend">
      <ArrowUpRight size={13} />
      {children}
    </span>
  );
}
