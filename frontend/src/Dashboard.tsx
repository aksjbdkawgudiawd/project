import { useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Boxes,
  CircleDollarSign,
  CreditCard,
  Package,
  Plus,
  Send,
  ShoppingBag,
  Users,
  Wallet,
} from "lucide-react";
import type { PageProps } from "./App";
import { count, date, money, rows, type RecordData } from "./api";
import { useData } from "./hooks";
import {
  Badge,
  Empty,
  ErrorBox,
  Loading,
  PageHeader,
  PanelHeading,
} from "./ui";

export default function Dashboard({
  refresh,
  navigate,
  openImport,
  openStock,
}: PageProps) {
  const { data, error, loading } = useData("/admin/dashboard", refresh);
  const [period, setPeriod] = useState("7");
  if (loading && !data) return <Loading />;
  if (!data) return <ErrorBox message={error} />;
  const stats = data.stats ?? data;
  const orders = rows(data.recent_orders);
  const stock = rows(data.low_stock);
  const series: RecordData[] = data.revenue_series ?? data.revenue_chart ?? [];
  const shownSeries = period === "7" ? series.slice(-7) : series;
  const totalRevenue = shownSeries.reduce(
    (total, item) =>
      total +
      (item.revenue_cents ?? item.total_cents ?? item.amount_cents ?? 0),
    0,
  );
  function exportReport() {
    const content = [
      "date,revenue_usd,orders",
      ...shownSeries.map(
        (row) =>
          `${row.date},${((row.revenue_cents ?? row.total_cents ?? 0) / 100).toFixed(2)},${row.orders ?? row.order_count ?? 0}`,
      ),
    ].join("\n");
    const url = URL.createObjectURL(new Blob([content], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "arshisney-revenue.csv";
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <>
      <PageHeader
        eyebrow="YOUR STORE AT A GLANCE"
        title="Overview"
        description="A little clarity for your day. Here’s how your marketplace is doing."
        actions={
          <>
            <button className="button secondary" onClick={exportReport}>
              <ArrowDownToLine size={16} />
              Export report
            </button>
            <button className="button primary" onClick={openStock}>
              <Plus size={17} />
              Add inventory
            </button>
          </>
        }
      />
      <ErrorBox message={error} />
      <div className="overview-banner">
        <div className="banner-symbol">
          <Send size={22} />
        </div>
        <div>
          <strong>One workspace. Your entire marketplace.</strong>
          <p>
            {data.demo
              ? "Demo workspace · synthetic customers, inventory, and payments. No live transactions."
              : "From the first top-up to the last delivery, keep everything in sync."}
          </p>
        </div>
        <button onClick={() => navigate("integrations")}>
          Manage integrations
          <ArrowUpRight size={16} />
        </button>
        <div className="banner-decoration" />
      </div>
      <div className="stat-grid">
        <Stat
          icon={CircleDollarSign}
          title="Revenue"
          value={money(stats.revenue_7d_cents ?? 0)}
          label="Last 7 days"
          accent="orange"
          line={series
            .slice(-7)
            .map(
              (row) =>
                (50 * row.revenue_cents) /
                Math.max(1, ...series.map((item) => item.revenue_cents)),
            )}
        />
        <Stat
          icon={ShoppingBag}
          title="Total orders"
          value={count(stats.total_orders ?? 0)}
          label="All-time orders"
          accent="purple"
          line={[]}
        />
        <Stat
          icon={Boxes}
          title="Available stock"
          value={count(stats.available_stock ?? 0)}
          label={`${count(stats.reserved_stock ?? 0)} units reserved`}
          accent="blue"
          line={[]}
        />
        <Stat
          icon={Users}
          title="Customers"
          value={count(stats.active_users ?? stats.total_users ?? 0)}
          label="Registered customers"
          accent="green"
          line={[]}
        />
      </div>
      <div className="dashboard-middle">
        <section className="panel revenue-panel">
          <div className="panel-heading">
            <div>
              <h2>Revenue overview</h2>
              <p>A closer look at your store’s performance</p>
            </div>
            <select
              aria-label="Revenue period"
              className="compact-select"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            >
              <option value="7">Last 7 days</option>
              <option value="14">Last 14 days</option>
            </select>
          </div>
          <div className="chart-summary">
            <strong>{money(totalRevenue)}</strong>
            <span>
              <i className="legend-dot" />
              Revenue in USD
            </span>
          </div>
          <RevenueChart series={shownSeries} />
        </section>
        <section className="panel attention-panel">
          <PanelHeading
            title="Needs attention"
            subtitle="A few things to keep an eye on"
          />
          <button
            className="attention-item"
            onClick={() => navigate("payments")}
          >
            <div className="attention-icon amber">
              <CreditCard size={20} />
            </div>
            <div>
              <strong>Manual payments</strong>
              <small>Waiting for your review</small>
            </div>
            <span className="count-chip amber">
              {stats.pending_manual_payments ?? 0}
            </span>
            <ChevronRightIcon />
          </button>
          <button
            className="attention-item"
            onClick={() => navigate("inventory")}
          >
            <div className="attention-icon lavender">
              <Package size={20} />
            </div>
            <div>
              <strong>Low-stock products</strong>
              <small>Time for a quick restock</small>
            </div>
            <span className="count-chip lavender">
              {data.low_stock_count ?? stock.length}
            </span>
            <ChevronRightIcon />
          </button>
          <button className="attention-item" onClick={() => navigate("orders")}>
            <div className="attention-icon pink">
              <ShoppingBag size={20} />
            </div>
            <div>
              <strong>Delivery issues</strong>
              <small>
                {stats.failed_deliveries == null
                  ? "Delivery monitoring not connected"
                  : "Orders that need a hand"}
              </small>
            </div>
            <span className="count-chip pink">
              {stats.failed_deliveries ?? "—"}
            </span>
            <ChevronRightIcon />
          </button>
          <div className="wallet-summary">
            <div>
              <Wallet size={17} />
              <span>Customer wallet liability</span>
            </div>
            <strong>{money(stats.wallet_liability_cents ?? 0)}</strong>
            <p>Total balance held across customer wallets</p>
          </div>
        </section>
      </div>
      <section className="panel orders-panel">
        <PanelHeading
          title="Recent orders"
          subtitle="The latest activity from your storefront"
          action="View all orders"
          onAction={() => navigate("orders")}
        />
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Order</th>
                <th>Customer</th>
                <th>Product</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Date</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {orders.slice(0, 5).map((order) => (
                <tr
                  key={order.id}
                  onClick={() => navigate("orders")}
                  className="clickable"
                >
                  <td>
                    <span className="order-number">
                      #
                      {order.number ??
                        order.order_number ??
                        String(order.id).slice(0, 8)}
                    </span>
                  </td>
                  <td>
                    <div className="customer-cell">
                      <span className="mini-avatar">
                        {(order.customer ?? order.username ?? "U")
                          .replace("@", "")
                          .slice(0, 2)
                          .toUpperCase()}
                      </span>
                      <span>{order.customer ?? order.username}</span>
                    </div>
                  </td>
                  <td>
                    <div className="product-cell">
                      <span>{order.flag ?? "🌐"}</span>
                      <span>
                        {order.product ??
                          order.sku_title ??
                          `${order.quantity ?? order.item_count} inventory units`}
                        <small>
                          {order.quantity ?? order.item_count}{" "}
                          {(order.quantity ?? order.item_count) === 1
                            ? "unit"
                            : "units"}
                        </small>
                      </span>
                    </div>
                  </td>
                  <td className="amount">{money(order.total_cents)}</td>
                  <td>
                    <Badge status={order.status} />
                  </td>
                  <td>
                    <span className="muted">{date(order.created_at)}</span>
                  </td>
                  <td>
                    <button
                      className="icon-button"
                      aria-label={`View order ${order.number ?? order.id}`}
                      onClick={() => navigate("orders")}
                    >
                      <ArrowUpRight size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!orders.length && (
            <Empty
              title="Your first order is up next"
              text="Orders will appear here as customers check out."
            />
          )}
        </div>
      </section>
      <div className="dashboard-bottom">
        <section className="panel stock-panel">
          <PanelHeading
            title="Stock watch"
            subtitle="A heads-up before the shelves go empty"
            action="View inventory"
            onAction={() => navigate("inventory")}
          />
          <div className="stock-watch-list">
            {stock.slice(0, 3).map((sku) => (
              <div className="stock-watch" key={sku.id}>
                <div className="country-icon">{sku.flag ?? "🌐"}</div>
                <div>
                  <strong>{sku.title}</strong>
                  <small>
                    {sku.country_name ?? sku.country_iso2} <span>·</span>{" "}
                    {money(sku.price_cents)} / unit
                  </small>
                </div>
                <div className="stock-level">
                  <strong>
                    {sku.available ?? sku.available_stock ?? 0} left
                  </strong>
                  <div>
                    <i
                      style={{
                        width: `${Math.max(5, Math.min(100, (sku.available ?? sku.available_stock ?? 0) * 10))}%`,
                      }}
                    />
                  </div>
                </div>
                <button
                  className="icon-button"
                  aria-label={`Restock ${sku.title}`}
                  onClick={openStock}
                >
                  <Plus size={17} />
                </button>
              </div>
            ))}
            {!stock.length && (
              <div className="stock-healthy">
                All stocked up. No low-stock products right now.
              </div>
            )}
          </div>
        </section>
        <section className="import-card">
          <div className="import-illustration">
            <div className="paper back" />
            <div className="paper">
              <ArrowDownToLine size={24} />
              <span />
              <span />
            </div>
            <div className="floating-plus">
              <Plus size={16} />
            </div>
          </div>
          <div>
            <div className="eyebrow">LESS CLICKING, MORE SELLING</div>
            <h2>Stock up in one go.</h2>
            <p>
              Bring your inventory together with a simple CSV or JSON import.
            </p>
            <button className="button secondary" onClick={openImport}>
              <ArrowDownToLine size={15} />
              Import inventory
              <ArrowRight size={15} />
            </button>
          </div>
        </section>
      </div>
    </>
  );
}

function Stat({
  icon: Icon,
  title,
  value,
  label,
  accent,
  line,
}: {
  icon: typeof Boxes;
  title: string;
  value: string;
  label: string;
  accent: string;
  line: number[];
}) {
  return (
    <section className="stat-card">
      <div className="stat-title">
        <span>{title}</span>
        <div className={`stat-icon ${accent}`}>
          <Icon size={17} />
        </div>
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-bottom">
        <span>{label}</span>
        <div className={`mini-bars ${accent}`} aria-hidden="true">
          {line.map((h, i) => (
            <i key={i} style={{ height: h * 0.58 }} />
          ))}
        </div>
      </div>
    </section>
  );
}

function RevenueChart({ series }: { series: RecordData[] }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const values = series.map(
    (p) => (p.revenue_cents ?? p.total_cents ?? p.amount_cents ?? 0) / 100,
  );
  const maximum = Math.max(4, ...values) * 1.15;
  const width = 700,
    height = 190,
    left = 48,
    right = 28,
    top = 15,
    bottom = 28;
  const points = values.map((n, i) => [
    left + (i / Math.max(1, values.length - 1)) * (width - left - right),
    top + (1 - n / maximum) * (height - top - bottom),
  ]);
  const line = points
    .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x},${y}`)
    .join(" ");
  const area = points.length
    ? `${line} L${points[points.length - 1][0]},${height - bottom} L${left},${height - bottom} Z`
    : "";
  return (
    <div className="chart">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Revenue chart. ${series.length} daily values, total ${money(values.reduce((a, b) => a + b, 0) * 100)}.`}
      >
        <defs>
          <linearGradient id="revenue-gradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#eb824f" stopOpacity=".2" />
            <stop offset="100%" stopColor="#eb824f" stopOpacity=".01" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3].map((i) => {
          const y = top + (i / 3) * (height - top - bottom);
          return (
            <g key={i}>
              <line
                x1={left}
                x2={width - right}
                y1={y}
                y2={y}
                stroke="#eaecef"
                strokeDasharray="4 4"
              />
              <text
                x={left - 12}
                y={y + 4}
                textAnchor="end"
                className="chart-label"
              >
                ${Math.round(maximum * (1 - i / 3))}
              </text>
            </g>
          );
        })}
        <path d={area} fill="url(#revenue-gradient)" />
        <path
          d={line}
          fill="none"
          stroke="#e97f47"
          strokeWidth="2.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {points.map(([x, y], i) => (
          <g
            key={i}
            onMouseEnter={() => setHovered(i)}
            onMouseLeave={() => setHovered(null)}
          >
            <circle cx={x} cy={y} r="18" fill="transparent" />
            <circle
              cx={x}
              cy={y}
              r={hovered === i ? "5" : "3"}
              fill="#e97f47"
              stroke="white"
              strokeWidth="2"
            />
            <title>
              {date(series[i].date)}: {money(values[i] * 100)}
            </title>
            {(series.length <= 8 || i % 5 === 0) && (
              <text
                x={x}
                y={height - 6}
                textAnchor="middle"
                className="chart-label"
              >
                {date(series[i].date)}
              </text>
            )}
          </g>
        ))}
      </svg>
      {!series.length && (
        <div className="chart-empty">
          Revenue will appear after your first sale
        </div>
      )}
    </div>
  );
}
function ChevronRightIcon() {
  return <ArrowRight size={15} className="subtle-arrow" />;
}
