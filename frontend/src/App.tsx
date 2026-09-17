import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  Boxes,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  ExternalLink,
  LayoutDashboard,
  LogOut,
  Menu,
  Package,
  Radio,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  ShoppingBag,
  Users,
  Wallet,
  X,
} from "lucide-react";
import { api, post, type RecordData } from "./api";
import { ErrorBox, Loading, Modal, Submit } from "./ui";
import Dashboard from "./Dashboard";
import {
  Inventory,
  Catalog,
  Orders,
  Payments,
  Customers,
  Integrations,
  Settings,
  Audit,
} from "./pages";
import { StockForm, ImportForm, Storefront } from "./forms";

const navigation = [
  {
    section: "WORKSPACE",
    items: [
      { id: "dashboard", label: "Overview", icon: LayoutDashboard },
      { id: "inventory", label: "Inventory", icon: Boxes },
      { id: "catalog", label: "Catalog", icon: Package },
      { id: "orders", label: "Orders", icon: ShoppingBag },
      { id: "payments", label: "Payments", icon: Wallet },
      { id: "customers", label: "Customers", icon: Users },
    ],
  },
  {
    section: "MANAGE",
    items: [
      { id: "integrations", label: "Integrations", icon: Radio },
      { id: "settings", label: "Store settings", icon: Settings2 },
      { id: "audit", label: "Audit log", icon: ShieldCheck },
    ],
  },
];

export type PageProps = {
  refresh: number;
  navigate: (page: string) => void;
  notify: (message: string) => void;
  changed: () => void;
  openStock: () => void;
  openImport: () => void;
};

export default function App() {
  const [page, setPage] = useState(
    location.hash.slice(1).split("?")[0] || "dashboard",
  );
  const [session, setSession] = useState<RecordData | null>(null);
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [modal, setModal] = useState("");
  const [mobile, setMobile] = useState(false);
  const [busy, setBusy] = useState(false);
  const navigate = (target: string) => {
    location.hash = target;
    setPage(target);
    setMobile(false);
    window.scrollTo(0, 0);
  };
  const close = useCallback(() => setModal(""), []);
  const notify = (message: string) => setToast(message);
  const changed = () => setRefresh((v) => v + 1);
  useEffect(() => {
    const onHash = () =>
      setPage(location.hash.slice(1).split("?")[0] || "dashboard");
    window.addEventListener("hashchange", onHash);
    api("/admin/auth/me")
      .then(setSession)
      .catch(async () => {
        const health = await api("/health");
        if (health.environment === "demo")
          setSession(await post("/admin/auth/demo"));
      })
      .catch(() => setSession(null))
      .finally(() => setBooting(false));
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    const shortcut = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setModal((current) => (current === "search" ? "" : "search"));
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(""), 4500);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  async function login(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      setSession(
        await post("/admin/auth/login", {
          username: form.get("username"),
          password: form.get("password"),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const current =
    navigation.flatMap((n) => n.items).find((n) => n.id === page) ??
    navigation[0].items[0];
  const props: PageProps = {
    refresh,
    navigate,
    notify,
    changed,
    openStock: () => setModal("stock"),
    openImport: () => setModal("import"),
  };
  const pages: Record<string, React.ComponentType<PageProps>> = {
    dashboard: Dashboard,
    inventory: Inventory,
    catalog: Catalog,
    orders: Orders,
    payments: Payments,
    customers: Customers,
    integrations: Integrations,
    settings: Settings,
    audit: Audit,
  };
  const Page = pages[page] ?? Dashboard;
  if (booting) return <Loading />;
  if (!session)
    return (
      <div className="login-screen">
        <div className="login-brand">
          <Logo /> arshisney<span>MARKETPLACE OPERATIONS</span>
        </div>
        <form className="login-card" onSubmit={login}>
          <div className="eyebrow">YOUR STORE, CONNECTED</div>
          <h1>Welcome back.</h1>
          <p>Sign in to your private marketplace workspace.</p>
          <ErrorBox message={error} />
          <label>
            Username
            <input name="username" required autoComplete="username" />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              required
              autoComplete="current-password"
            />
          </label>
          <Submit busy={busy}>Sign in securely</Submit>
          <small>
            <ShieldCheck size={14} /> Protected administrator access
          </small>
        </form>
      </div>
    );
  return (
    <div className="app-shell">
      {mobile && <div className="nav-scrim" onClick={() => setMobile(false)} />}
      <aside className={`sidebar ${mobile ? "open" : ""}`}>
        <a className="brand" href="#dashboard">
          <Logo />
          <span>
            arshisney<span className="brand-caption">MERCHANT WORKSPACE</span>
          </span>
        </a>
        <button className="store-switch" onClick={() => setModal("workspace")}>
          <div className="store-icon">
            <Send size={17} />
          </div>
          <span>
            <strong>Arshisney Store</strong>
            <small>Telegram marketplace</small>
          </span>
          <ChevronDown size={15} />
        </button>
        <nav>
          {navigation.map((section) => (
            <div className="nav-section" key={section.section}>
              <div className="nav-label">{section.section}</div>
              {section.items.map((item) => (
                <button
                  className={`nav-item ${page === item.id ? "active" : ""}`}
                  key={item.id}
                  onClick={() => navigate(item.id)}
                >
                  <item.icon size={18} strokeWidth={1.7} />
                  <span>{item.label}</span>
                  {page === item.id && <span className="active-dot" />}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="store-health">
            <span className="status-dot" />
            <span>{session.demo ? "Demo workspace" : "Private workspace"}</span>
            <span className="environment-tag">
              {session.demo ? "SANDBOX" : "ADMIN"}
            </span>
          </div>
          <button className="support-link" onClick={() => setModal("help")}>
            <CircleHelp size={17} />
            Workspace guide
            <ArrowUpRightIcon />
          </button>
          <div className="profile">
            <div className="avatar">AS</div>
            <span>
              <strong>{session.username ?? "Store administrator"}</strong>
              <small>
                {session.role
                  ? String(session.role).replaceAll("_", " ")
                  : "Administrator"}
              </small>
            </span>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={async () => {
                try {
                  await post("/admin/auth/logout");
                  setSession(null);
                } catch (e) {
                  notify((e as Error).message);
                }
              }}
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <main className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-menu"
              onClick={() => setMobile(true)}
              aria-label="Open navigation"
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{current.label}</strong>
          </div>
          <div className="topbar-actions">
            <button className="quick-search" onClick={() => setModal("search")}>
              <Search size={16} />
              <span>Quick navigation</span>
              <kbd>⌘ K</kbd>
            </button>
            <span className="topbar-divider" />
            <button
              className="store-preview-button"
              onClick={() => setModal("storefront")}
            >
              <Send size={15} />
              <span>
                {session.demo ? "Test storefront" : "Storefront preview"}
              </span>
              <ExternalLink size={13} />
            </button>
          </div>
        </header>
        <div className="content">
          <Page {...props} />
        </div>
        <footer className="page-footer">
          <span>
            Arshisney <i /> Marketplace operations
          </span>
          <span>
            <ShieldCheck size={13} /> Ledger-backed. Every unit accounted for.
          </span>
        </footer>
      </main>
      {toast && (
        <div className="toast" role="status">
          <ShieldCheck size={18} />
          {toast}
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setToast("")}
          >
            <X size={15} />
          </button>
        </div>
      )}
      {modal === "stock" && (
        <StockForm
          close={close}
          onSuccess={() => {
            close();
            changed();
            notify("Inventory unit added successfully.");
          }}
        />
      )}
      {modal === "import" && (
        <ImportForm
          close={close}
          onSuccess={() => {
            close();
            changed();
            notify("Inventory import completed.");
          }}
        />
      )}
      {modal === "storefront" && (
        <Storefront
          close={close}
          onChange={changed}
          demo={Boolean(session.demo)}
        />
      )}
      {modal === "search" && (
        <NavigationModal close={close} navigate={navigate} />
      )}
      {modal === "workspace" && (
        <Modal
          title="Arshisney Store"
          subtitle="One connected marketplace workspace"
          close={close}
        >
          <div className="modal-body">
            <div className="info-banner">
              <Send size={22} />
              <span>
                {session.demo
                  ? "You are in an isolated demo workspace. All customers, payments, and deliverables are synthetic."
                  : "This is your private administrator workspace."}
              </span>
            </div>
            <p>
              Manage inventory, review payments, and monitor every order from
              this workspace. Telegram and payment providers must be configured
              separately before accepting real transactions.
            </p>
            <button
              className="button primary"
              onClick={() => {
                close();
                navigate("integrations");
              }}
            >
              View integrations
              <ArrowRight size={16} />
            </button>
          </div>
        </Modal>
      )}
      {modal === "help" && (
        <Modal
          title="A good place to start"
          subtitle="Your marketplace, without the busywork."
          close={close}
        >
          <div className="modal-body guide">
            <div>
              <span>01</span>
              <section>
                <h3>Build your catalog</h3>
                <p>
                  Create a product type, set its price in USD, and choose a
                  country and delivery mode.
                </p>
              </section>
            </div>
            <div>
              <span>02</span>
              <section>
                <h3>Add authorized inventory</h3>
                <p>
                  Add individual units or import a CSV/JSON file. Every unit is
                  tracked and sensitive delivery payloads are encrypted.
                </p>
              </section>
            </div>
            <div>
              <span>03</span>
              <section>
                <h3>Review and fulfill</h3>
                <p>
                  Review manual top-ups before crediting balances. Checkout
                  allocates exact stock and records a ledger debit.
                </p>
              </section>
            </div>
            <div className="info-banner">
              This first release is not cleared for production. See
              docs/IMPLEMENTATION_STATUS.md for the launch checklist and
              integration gaps.
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Logo() {
  return (
    <div className="logo-mark">
      <svg width="26" height="28" viewBox="0 0 30 30" fill="none">
        <path
          d="M5 22 15 7l10 15M9 18h12M12 26h6"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}
function ArrowUpRightIcon() {
  return <ExternalLink size={14} className="push-right" />;
}
function NavigationModal({
  close,
  navigate,
}: {
  close: () => void;
  navigate: (p: string) => void;
}) {
  const [query, setQuery] = useState("");
  return (
    <Modal title="Go to…" close={close}>
      <div className="modal-body">
        <div className="search-box">
          <Search size={18} />
          <input
            autoFocus
            placeholder="Search workspace pages"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="quick-links">
          {navigation
            .flatMap((n) => n.items)
            .filter((n) => n.label.toLowerCase().includes(query.toLowerCase()))
            .map((n) => (
              <button
                key={n.id}
                onClick={() => {
                  navigate(n.id);
                  close();
                }}
              >
                <n.icon size={18} />
                {n.label}
                <ArrowRight size={15} />
              </button>
            ))}
        </div>
      </div>
    </Modal>
  );
}
