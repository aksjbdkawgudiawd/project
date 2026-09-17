import { useCallback, useEffect, useState } from "react";
import {
  ArrowUpRight,
  Boxes,
  ChevronLeft,
  ChevronRight,
  CreditCard,
  Edit3,
  FileText,
  KeyRound,
  Plus,
  Send,
  Settings2,
  Shield,
  ShieldCheck,
  Upload,
} from "lucide-react";
import type { PageProps } from "./App";
import {
  count,
  date,
  human,
  money,
  post,
  put,
  rows,
  time,
  type RecordData,
} from "./api";
import { useData } from "./hooks";
import {
  Badge,
  Empty,
  ErrorBox,
  Loading,
  Modal,
  PageHeader,
  SearchBox,
  Submit,
} from "./ui";
import { SkuForm } from "./forms";

function Pagination({
  total,
  page,
  setPage,
}: {
  total: number;
  page: number;
  setPage: (n: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / 10));
  return (
    <div className="table-footer">
      <span>
        {total
          ? `${(page - 1) * 10 + 1}–${Math.min(page * 10, total)} of ${count(total)} results`
          : "0 results"}
      </span>
      <div>
        <button
          className="icon-button"
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
          aria-label="Previous page"
        >
          <ChevronLeft size={16} />
        </button>
        <span>
          Page {page} of {pages}
        </span>
        <button
          className="icon-button"
          disabled={page >= pages}
          onClick={() => setPage(page + 1)}
          aria-label="Next page"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}
function useFilter(
  data: any,
  query: string,
  filter: (row: RecordData) => boolean = () => true,
) {
  const [page, setPage] = useState(1);
  const filtered = rows(data).filter(
    (row) =>
      filter(row) &&
      Object.entries(row)
        .filter(([key]) => !["payload", "payload_encrypted"].includes(key))
        .some(([, value]) =>
          String(value ?? "")
            .toLowerCase()
            .includes(query.toLowerCase()),
        ),
  );
  useEffect(() => setPage(1), [query, filtered.length]);
  return {
    filtered,
    visible: filtered.slice((page - 1) * 10, page * 10),
    page,
    setPage,
  };
}

export function Inventory({
  refresh,
  openStock,
  openImport,
  changed,
  notify,
}: PageProps) {
  const { data, loading, error } = useData("/admin/inventory", refresh);
  const [query, setQuery] = useState(""),
    [status, setStatus] = useState("ALL");
  const [selected, setSelected] = useState<RecordData | null>(null),
    [actionError, setActionError] = useState(""),
    [busy, setBusy] = useState(false);
  const close = useCallback(() => {
    setSelected(null);
    setActionError("");
  }, []);
  const { filtered, visible, page, setPage } = useFilter(
    data,
    query,
    (row) => status === "ALL" || row.status === status,
  );
  const all = rows(data);
  async function changeStatus(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setActionError("");
    const form = new FormData(event.currentTarget);
    try {
      await post(`/admin/inventory/${selected!.id}/status`, {
        status: String(form.get("status")).toLowerCase(),
        reason: form.get("reason"),
      });
      close();
      changed();
      notify("Stock status updated and recorded in the audit log.");
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="EVERY UNIT ACCOUNTED FOR"
        title="Inventory"
        description="Keep your shelves stocked and your deliveries ready."
        actions={
          <>
            <button className="button secondary" onClick={openImport}>
              <Upload size={15} />
              Import stock
            </button>
            <button className="button primary" onClick={openStock}>
              <Plus size={16} />
              Add inventory
            </button>
          </>
        }
      />
      <div className="summary-strip">
        <div>
          <span>Available to sell</span>
          <strong>
            {count(all.filter((s) => s.status === "AVAILABLE").length)}
          </strong>
          <small>Individual, traceable stock units</small>
        </div>
        <div>
          <span>Reserved & sold</span>
          <strong>
            {count(
              all.filter((s) => ["SOLD", "RESERVED"].includes(s.status)).length,
            )}
          </strong>
          <small>Allocated to a customer order</small>
        </div>
        <div>
          <span>Quarantined</span>
          <strong>
            {count(all.filter((s) => s.status === "QUARANTINED").length)}
          </strong>
          <small>Held back from the storefront</small>
        </div>
      </div>
      <ErrorBox message={error} />
      <section className="panel">
        <div className="tabs">
          {["ALL", "AVAILABLE", "RESERVED", "SOLD", "QUARANTINED"].map((s) => (
            <button
              key={s}
              className={status === s ? "active" : ""}
              onClick={() => setStatus(s)}
            >
              {s === "ALL" ? "All inventory" : human(s)}
              <span>
                {s === "ALL"
                  ? all.length
                  : all.filter((r) => r.status === s).length}
              </span>
            </button>
          ))}
        </div>
        <div className="toolbar">
          <SearchBox
            value={query}
            onChange={setQuery}
            placeholder="Search by SKU, country, or external ID…"
          />
          <span className="toolbar-count">
            <ShieldCheck
              size={13}
              style={{ verticalAlign: "middle", marginRight: 5 }}
            />
            Sensitive payloads are encrypted
          </span>
        </div>
        {loading && !data ? (
          <Loading />
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Stock unit</th>
                    <th>Product</th>
                    <th>Country</th>
                    <th>Source</th>
                    <th>Status</th>
                    <th>Added</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((unit) => (
                    <tr key={unit.id}>
                      <td>
                        <span className="code">
                          {unit.external_item_id ??
                            String(unit.id).slice(0, 12)}
                        </span>
                        <small
                          className="muted"
                          style={{ display: "block", marginTop: 4 }}
                        >
                          {unit.phone_masked ?? "Encrypted delivery"}
                        </small>
                      </td>
                      <td>
                        <div className="sku-name">
                          {unit.sku_title}
                          <small>{human(unit.delivery_mode)}</small>
                        </div>
                      </td>
                      <td>
                        {unit.flag}{" "}
                        <span className="muted">
                          {unit.country_name ?? unit.country_iso2}
                        </span>
                      </td>
                      <td>
                        <span className="muted">
                          {human(unit.source ?? "manual")}
                        </span>
                      </td>
                      <td>
                        <Badge status={unit.status} />
                      </td>
                      <td className="muted">{date(unit.created_at)}</td>
                      <td>
                        <button
                          className="icon-button"
                          disabled={["SOLD", "RESERVED"].includes(unit.status)}
                          aria-label={`Manage stock ${unit.external_item_id ?? unit.id}`}
                          onClick={() => setSelected(unit)}
                        >
                          <Edit3 size={15} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visible.length && (
                <Empty
                  title="No matching stock"
                  text="Try a different search or add inventory to get started."
                />
              )}
            </div>
            <Pagination total={filtered.length} page={page} setPage={setPage} />
          </>
        )}
      </section>
      {selected && (
        <Modal
          title="Manage stock unit"
          subtitle={selected.external_item_id ?? selected.id}
          close={close}
        >
          <form onSubmit={changeStatus}>
            <div className="modal-body">
              <ErrorBox message={actionError} />
              <div className="form-grid">
                <label className="full">
                  Stock status
                  <select name="status" defaultValue={selected.status}>
                    {["AVAILABLE", "QUARANTINED", "INVALID"].map((s) => (
                      <option key={s} value={s}>
                        {human(s)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="full">
                  Reason
                  <textarea
                    name="reason"
                    placeholder="Why are you changing this unit’s status?"
                    required
                    minLength={3}
                  />
                </label>
              </div>
              <p>
                Sold or reserved inventory cannot be manually restored. Every
                change is recorded in the audit log.
              </p>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                className="button secondary"
                onClick={close}
              >
                Cancel
              </button>
              <Submit busy={busy}>Update status</Submit>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}

export function Catalog({ refresh, changed, notify }: PageProps) {
  const { data, loading, error } = useData("/admin/skus", refresh);
  const [query, setQuery] = useState(""),
    [section, setSection] = useState("ALL"),
    [editing, setEditing] = useState<RecordData | null | false>(false);
  const close = useCallback(() => setEditing(false), []);
  const { filtered, visible, page, setPage } = useFilter(
    data,
    query,
    (row) =>
      section === "ALL" || (section === "active" ? row.active : !row.active),
  );
  return (
    <>
      <PageHeader
        eyebrow="THE STOREFRONT STARTS HERE"
        title="Product catalog"
        description="Your product types, pricing, and availability. All in one place."
        actions={
          <button className="button primary" onClick={() => setEditing(null)}>
            <Plus size={16} />
            Create product
          </button>
        }
      />
      <ErrorBox message={error} />
      <section className="panel">
        <div className="toolbar">
          <div className="toolbar-left">
            <SearchBox
              value={query}
              onChange={setQuery}
              placeholder="Search products or countries…"
            />
            <select
              aria-label="Product visibility"
              value={section}
              onChange={(e) => setSection(e.target.value)}
            >
              <option value="ALL">All products</option>
              <option value="active">Active</option>
              <option value="disabled">Disabled</option>
            </select>
          </div>
          <span className="toolbar-count">{rows(data).length} products</span>
        </div>
        {loading && !data ? (
          <Loading />
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Country</th>
                    <th>Price</th>
                    <th>Stock</th>
                    <th>Wholesale price</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((sku) => (
                    <tr key={sku.id}>
                      <td>
                        <div className="product-cell">
                          <span className="country-icon">
                            {sku.flag ?? "🌐"}
                          </span>
                          <div className="sku-name">
                            {sku.title}
                            <small>{sku.code ?? sku.slug}</small>
                          </div>
                        </div>
                      </td>
                      <td>{sku.country_name ?? sku.country_iso2}</td>
                      <td className="amount">
                        {money(sku.price_cents)}
                        <small
                          className="muted"
                          style={{ display: "block", marginTop: 4 }}
                        >
                          per unit
                        </small>
                      </td>
                      <td>
                        <span
                          style={{
                            color: sku.available < 5 ? "#c59265" : "#738979",
                          }}
                        >
                          {sku.available ?? sku.available_stock ?? 0} units
                        </span>
                      </td>
                      <td>{money(sku.wholesale_price_cents)}</td>
                      <td>
                        <Badge status={sku.enabled ? "ACTIVE" : "DISABLED"} />
                      </td>
                      <td>
                        <button
                          className="icon-button"
                          aria-label={`Edit ${sku.title}`}
                          onClick={() => setEditing(sku)}
                        >
                          <Edit3 size={15} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visible.length && (
                <Empty
                  title="No matching products"
                  text="Create your first product type or try another search."
                />
              )}
            </div>
            <Pagination total={filtered.length} page={page} setPage={setPage} />
          </>
        )}
      </section>
      {editing !== false && (
        <SkuForm
          sku={editing}
          close={close}
          onSuccess={() => {
            close();
            changed();
            notify(
              editing
                ? "Product updated."
                : "Product created. You can now add stock.",
            );
          }}
        />
      )}
    </>
  );
}

export function Orders({ refresh }: PageProps) {
  const { data, loading, error } = useData("/admin/orders", refresh);
  const [query, setQuery] = useState(""),
    [status, setStatus] = useState("ALL"),
    [selected, setSelected] = useState<string | null>(null);
  const close = useCallback(() => setSelected(null), []);
  const { filtered, visible, page, setPage } = useFilter(
    data,
    query,
    (row) => status === "ALL" || row.status === status,
  );
  return (
    <>
      <PageHeader
        eyebrow="FROM CHECKOUT TO DELIVERY"
        title="Orders"
        description="Every purchase, every unit, and the story behind it."
      />
      <ErrorBox message={error} />
      <section className="panel">
        <div className="tabs">
          {["ALL", "COMPLETED", "PAID", "DELIVERING", "FAILED"].map((s) => (
            <button
              key={s}
              className={s === status ? "active" : ""}
              onClick={() => setStatus(s)}
            >
              {s === "ALL" ? "All orders" : human(s)}
            </button>
          ))}
        </div>
        <div className="toolbar">
          <SearchBox
            value={query}
            onChange={setQuery}
            placeholder="Search order number or customer…"
          />
          <span className="toolbar-count">{rows(data).length} orders</span>
        </div>
        {loading && !data ? (
          <Loading />
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Order</th>
                    <th>Customer</th>
                    <th>Product</th>
                    <th>Units</th>
                    <th>Total</th>
                    <th>Status</th>
                    <th>Created</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((order) => (
                    <tr
                      key={order.id}
                      className="clickable"
                      onClick={() => setSelected(order.id)}
                    >
                      <td className="order-number">
                        #
                        {order.number ??
                          order.order_number ??
                          String(order.id).slice(0, 8)}
                      </td>
                      <td>
                        <div className="customer-cell">
                          <div className="mini-avatar">
                            {(order.customer ?? "U")
                              .replace("@", "")
                              .slice(0, 2)
                              .toUpperCase()}
                          </div>
                          {order.customer}
                        </div>
                      </td>
                      <td>
                        {order.flag}{" "}
                        {order.product ??
                          order.sku_title ??
                          "Multiple products"}
                      </td>
                      <td>{order.quantity ?? order.item_count}</td>
                      <td className="amount">{money(order.total_cents)}</td>
                      <td>
                        <Badge status={order.status} />
                      </td>
                      <td className="muted">{date(order.created_at)}</td>
                      <td>
                        <button
                          className="icon-button"
                          aria-label={`View order ${order.number ?? order.id}`}
                          onClick={() => setSelected(order.id)}
                        >
                          <ArrowUpRight size={16} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visible.length && (
                <Empty
                  title="No matching orders"
                  text="Customer purchases will appear here."
                />
              )}
            </div>
            <Pagination total={filtered.length} page={page} setPage={setPage} />
          </>
        )}
      </section>
      {selected && <OrderDetail id={selected} close={close} />}
    </>
  );
}

function OrderDetail({ id, close }: { id: string; close: () => void }) {
  const { data, error, loading } = useData(`/admin/orders/${id}`);
  return (
    <Modal
      title={
        data
          ? `Order #${data.number ?? data.order_number ?? id.slice(0, 8)}`
          : "Order details"
      }
      subtitle="An exact record of this purchase"
      close={close}
    >
      <div className="modal-body">
        <ErrorBox message={error} />
        {loading ? (
          <Loading />
        ) : (
          data && (
            <>
              <dl className="detail-grid">
                <div>
                  <dt>Customer</dt>
                  <dd>{data.customer}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>
                    <Badge status={data.status} />
                  </dd>
                </div>
                <div>
                  <dt>Created</dt>
                  <dd>
                    {date(data.created_at)} · {time(data.created_at)}
                  </dd>
                </div>
                <div>
                  <dt>Payment</dt>
                  <dd>Internal USD balance</dd>
                </div>
              </dl>
              <h3 className="section-label">Purchased products</h3>
              {rows(data.items).map((item, i) => (
                <div className="detail-line" key={item.id ?? i}>
                  <div>
                    {item.sku_title ?? item.title}
                    <small>
                      {item.quantity} ×{" "}
                      {money(item.unit_price_cents ?? item.price_cents)}
                    </small>
                  </div>
                  <strong>
                    {money(
                      item.line_total_cents ??
                        item.quantity *
                          (item.unit_price_cents ?? item.price_cents),
                    )}
                  </strong>
                </div>
              ))}
              <div className="detail-total">
                <span>Order total</span>
                <span>{money(data.total_cents)}</span>
              </div>
              <h3 className="section-label">Allocated inventory</h3>
              {rows(data.inventory ?? data.inventory_units).map((unit) => (
                <div className="detail-line" key={unit.id}>
                  <span className="code">
                    {unit.external_item_id ?? unit.id}
                  </span>
                  <Badge status={unit.delivery_status ?? unit.status} />
                </div>
              ))}
              <div className="info-banner blue" style={{ marginTop: 22 }}>
                <ShieldCheck size={18} />
                Sensitive deliverables are not exposed in the admin order view.
                Wallet debits and inventory allocations are committed together.
              </div>
            </>
          )
        )}
      </div>
    </Modal>
  );
}

export function Payments({ refresh, changed, notify }: PageProps) {
  const { data, error, loading } = useData("/admin/topups", refresh);
  const [query, setQuery] = useState(""),
    [status, setStatus] = useState("ALL"),
    [selected, setSelected] = useState<RecordData | null>(null);
  const close = useCallback(() => setSelected(null), []);
  const { filtered, visible, page, setPage } = useFilter(
    data,
    query,
    (row) => status === "ALL" || row.status === status,
  );
  const all = rows(data);
  return (
    <>
      <PageHeader
        eyebrow="BALANCES BEGIN HERE"
        title="Payments & top-ups"
        description="Verify payments with confidence. Credit customer balances exactly once."
      />
      <div className="summary-strip">
        <div>
          <span>Awaiting review</span>
          <strong>
            {all.filter((r) => r.status === "UNDER_REVIEW").length}
          </strong>
          <small>Manual top-ups needing verification</small>
        </div>
        <div>
          <span>Approved credit</span>
          <strong>
            {money(
              all
                .filter((r) => r.status === "APPROVED")
                .reduce((a, r) => a + r.requested_credit_cents, 0),
            )}
          </strong>
          <small>Net amount credited to customer wallets</small>
        </div>
        <div>
          <span>Payment requests</span>
          <strong>{all.length}</strong>
          <small>All providers, all statuses</small>
        </div>
      </div>
      <ErrorBox message={error} />
      <section className="panel">
        <div className="tabs">
          {["ALL", "UNDER_REVIEW", "APPROVED", "REJECTED", "EXPIRED"].map(
            (s) => (
              <button
                key={s}
                onClick={() => setStatus(s)}
                className={s === status ? "active" : ""}
              >
                {s === "ALL" ? "All top-ups" : human(s)}
                {s === "UNDER_REVIEW" && (
                  <span>{all.filter((r) => r.status === s).length}</span>
                )}
              </button>
            ),
          )}
        </div>
        <div className="toolbar">
          <SearchBox
            value={query}
            onChange={setQuery}
            placeholder="Search customer or payment ID…"
          />
          <span className="toolbar-count">USD base currency</span>
        </div>
        {loading && !data ? (
          <Loading />
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Payment</th>
                    <th>Customer</th>
                    <th>Provider</th>
                    <th>Credit</th>
                    <th>Fee</th>
                    <th>Status</th>
                    <th>Date</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((topup) => (
                    <tr key={topup.id}>
                      <td className="code">
                        {topup.number ?? String(topup.id).slice(0, 10)}
                      </td>
                      <td>{topup.customer ?? topup.username}</td>
                      <td>
                        <div className="customer-cell">
                          <CreditCard size={14} />
                          {human(topup.provider)}
                        </div>
                      </td>
                      <td className="amount">
                        {money(topup.requested_credit_cents)}
                      </td>
                      <td className="muted">
                        {money(topup.fee_cents ?? topup.provider_fee_cents)}
                      </td>
                      <td>
                        <Badge status={topup.status} />
                      </td>
                      <td className="muted">{date(topup.created_at)}</td>
                      <td>
                        <button
                          className={`button small ${topup.status === "UNDER_REVIEW" ? "secondary" : "text"}`}
                          onClick={() => setSelected(topup)}
                        >
                          {topup.status === "UNDER_REVIEW"
                            ? "Review"
                            : "Details"}
                          <ArrowUpRight size={13} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visible.length && (
                <Empty
                  title="No matching payments"
                  text="Top-up requests will appear here for verification."
                />
              )}
            </div>
            <Pagination total={filtered.length} page={page} setPage={setPage} />
          </>
        )}
      </section>
      {selected && (
        <PaymentReview
          topup={selected}
          close={close}
          onSuccess={() => {
            close();
            changed();
            notify("Payment review saved. The wallet ledger is up to date.");
          }}
        />
      )}
    </>
  );
}

function PaymentReview({
  topup,
  close,
  onSuccess,
}: {
  topup: RecordData;
  close: () => void;
  onSuccess: () => void;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [decision, setDecision] = useState("approve");
  const reviewable = topup.status === "UNDER_REVIEW";
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(e.currentTarget);
    try {
      await post(`/admin/topups/${topup.id}/review`, {
        decision,
        note: form.get("note"),
      });
      onSuccess();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={reviewable ? "Review manual payment" : "Payment details"}
      subtitle={topup.number ?? topup.id}
      close={close}
    >
      <form onSubmit={submit}>
        <div className="modal-body">
          <ErrorBox message={error} />
          <dl className="detail-grid">
            <div>
              <dt>Customer</dt>
              <dd>{topup.customer ?? topup.username}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                <Badge status={topup.status} />
              </dd>
            </div>
            <div>
              <dt>Wallet credit</dt>
              <dd>{money(topup.requested_credit_cents)}</dd>
            </div>
            <div>
              <dt>Total to pay</dt>
              <dd>
                {money(
                  topup.amount_to_pay_cents ??
                    topup.requested_credit_cents + (topup.fee_cents ?? 0),
                )}
              </dd>
            </div>
          </dl>
          <div className="receipt-preview">
            <FileText size={28} />
            <p>
              {topup.receipt_reference ??
                topup.receipt_note ??
                "No receipt reference attached"}
            </p>
            <small>Verify against your bank records before approving.</small>
          </div>
          {reviewable ? (
            <div className="form-grid">
              <label className="full">
                Review decision
                <select
                  value={decision}
                  onChange={(e) => setDecision(e.target.value)}
                >
                  <option value="approve">Approve & credit wallet</option>
                  <option value="reject">Reject payment</option>
                </select>
              </label>
              <label className="full">
                Operator note
                <textarea
                  name="note"
                  required
                  minLength={3}
                  placeholder="Record how you verified this payment, or why it was rejected."
                />
              </label>
              <div className="info-banner full">
                <ShieldCheck size={18} />
                Approving creates one ledger credit. Repeated approval cannot
                credit the wallet twice.
              </div>
            </div>
          ) : (
            <p>
              {topup.review_note ??
                "This payment is not awaiting operator review."}
            </p>
          )}
        </div>
        <div className="modal-footer">
          <button type="button" className="button secondary" onClick={close}>
            {reviewable ? "Cancel" : "Close"}
          </button>
          {reviewable && (
            <Submit busy={busy}>
              {decision === "approve" ? "Approve payment" : "Reject payment"}
            </Submit>
          )}
        </div>
      </form>
    </Modal>
  );
}

export function Customers({ refresh, changed, notify }: PageProps) {
  const { data, error, loading } = useData("/admin/users", refresh);
  const [query, setQuery] = useState(""),
    [selected, setSelected] = useState<RecordData | null>(null),
    [actionError, setActionError] = useState(""),
    [busy, setBusy] = useState(false);
  const close = useCallback(() => {
    setSelected(null);
    setActionError("");
  }, []);
  const { filtered, visible, page, setPage } = useFilter(data, query);
  async function updateAccess() {
    setBusy(true);
    setActionError("");
    try {
      await post(`/admin/users/${selected!.id}/wholesale`, {
        wholesale_access: !selected!.wholesale_access,
      });
      close();
      changed();
      notify("Wholesale access updated.");
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="THE PEOPLE BEHIND THE PURCHASES"
        title="Customers"
        description="Manage customer access and keep a clear view of their balances."
      />
      <ErrorBox message={error} />
      <section className="panel">
        <div className="toolbar">
          <SearchBox
            value={query}
            onChange={setQuery}
            placeholder="Search username or Telegram ID…"
          />
          <span className="toolbar-count">{rows(data).length} customers</span>
        </div>
        {loading && !data ? (
          <Loading />
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Customer</th>
                    <th>Telegram ID</th>
                    <th>Balance</th>
                    <th>Orders</th>
                    <th>Access</th>
                    <th>Status</th>
                    <th>Joined</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((user) => (
                    <tr key={user.id}>
                      <td>
                        <div className="customer-cell">
                          <div className="mini-avatar">
                            {(user.first_name ?? user.username ?? "U")
                              .slice(0, 2)
                              .toUpperCase()}
                          </div>
                          <div className="sku-name">
                            {user.first_name ?? user.username}
                            <small>
                              @{String(user.username ?? "").replace("@", "")}
                            </small>
                          </div>
                        </div>
                      </td>
                      <td className="code">{user.telegram_user_id}</td>
                      <td className="amount">{money(user.balance_cents)}</td>
                      <td>{user.order_count ?? user.orders_count ?? 0}</td>
                      <td>
                        <Badge
                          status={
                            user.wholesale_access ? "WHOLESALE" : "RETAIL"
                          }
                        />
                      </td>
                      <td>
                        <Badge
                          status={user.is_blocked ? "BLOCKED" : "ACTIVE"}
                        />
                      </td>
                      <td className="muted">{date(user.created_at)}</td>
                      <td>
                        <button
                          className="icon-button"
                          onClick={() => setSelected(user)}
                          aria-label={`Manage ${user.username}`}
                        >
                          <ArrowUpRight size={16} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visible.length && (
                <Empty
                  title="No matching customers"
                  text="Customers will appear after starting your Telegram bot."
                />
              )}
            </div>
            <Pagination total={filtered.length} page={page} setPage={setPage} />
          </>
        )}
      </section>
      {selected && (
        <Modal
          title={selected.first_name ?? selected.username}
          subtitle={`Telegram ID ${selected.telegram_user_id}`}
          close={close}
        >
          <div className="modal-body">
            <ErrorBox message={actionError} />
            <dl className="detail-grid">
              <div>
                <dt>Wallet balance</dt>
                <dd>{money(selected.balance_cents)}</dd>
              </div>
              <div>
                <dt>Catalog access</dt>
                <dd>
                  {selected.wholesale_access
                    ? "Retail & wholesale"
                    : "Retail only"}
                </dd>
              </div>
            </dl>
            <div className="info-banner blue">
              <Shield size={20} />
              Wholesale access is verified server-side. This change will be
              recorded in your audit log.
            </div>
          </div>
          <div className="modal-footer">
            <button className="button secondary" onClick={close}>
              Close
            </button>
            <button
              className="button primary"
              disabled={busy}
              onClick={updateAccess}
            >
              <KeyRound size={15} />
              {selected.wholesale_access
                ? "Revoke wholesale"
                : "Grant wholesale"}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}

export function Integrations({ refresh }: PageProps) {
  const { data, error, loading } = useData("/admin/providers", refresh);
  const [selected, setSelected] = useState<RecordData | null>(null);
  const close = useCallback(() => setSelected(null), []);
  return (
    <>
      <PageHeader
        eyebrow="A CONNECTED MARKETPLACE"
        title="Integrations"
        description="Connect your inventory, payment methods, and Telegram storefront."
      />
      <div className="info-banner blue" style={{ marginBottom: 24 }}>
        <ShieldCheck size={21} />
        <span>
          Live integrations are disabled until their credentials and provider
          contracts are verified. No real payment is taken in the demo
          workspace.
        </span>
      </div>
      <ErrorBox message={error} />
      {loading ? (
        <Loading />
      ) : (
        <div className="provider-grid">
          {rows(data).map((provider) => (
            <section
              className="provider-card"
              key={provider.id ?? provider.code}
            >
              <div className="provider-card-top">
                <div className="provider-logo">
                  {provider.code === "telegram" ? (
                    <Send size={24} />
                  ) : provider.type === "inventory" ||
                    provider.code?.includes("inventory") ? (
                    <Boxes size={24} />
                  ) : (
                    <CreditCard size={24} />
                  )}
                </div>
                <Badge
                  status={
                    provider.health_status ??
                    (provider.enabled ? "ENABLED" : "NOT_CONFIGURED")
                  }
                />
              </div>
              <h2>{provider.name}</h2>
              <p>
                {provider.description ??
                  (provider.type === "inventory"
                    ? "Connect authorized stock through a replaceable provider adapter."
                    : "Top up internal balances through a verified payment flow.")}
              </p>
              <div className="provider-meta">
                <span>
                  {human(provider.type ?? provider.adapter_type ?? "payment")}
                </span>
                <span>
                  {provider.fee_bps != null
                    ? `${provider.fee_bps / 100}% provider fee`
                    : "Service integration"}
                </span>
              </div>
              <button
                className="button secondary"
                onClick={() => setSelected(provider)}
              >
                View configuration
                <ArrowUpRight size={14} />
              </button>
            </section>
          ))}
        </div>
      )}
      {selected && (
        <Modal
          title={selected.name}
          subtitle="Integration readiness"
          close={close}
        >
          <div className="modal-body">
            <Badge status={selected.health_status ?? "NOT_CONFIGURED"} />
            <p>
              {selected.description ??
                "This provider is not connected to a live upstream service."}
            </p>
            <h3 className="section-label">Required before activation</h3>
            <div className="detail-line">
              <span>Environment-injected credentials</span>
              <KeyRound size={15} />
            </div>
            <div className="detail-line">
              <span>Signed webhook and replay verification</span>
              <ShieldCheck size={15} />
            </div>
            <div className="detail-line">
              <span>Sandbox contract and reconciliation tests</span>
              <FileText size={15} />
            </div>
            <div className="detail-line">
              <span>Approved fee and delivery policy</span>
              <Settings2 size={15} />
            </div>
            <div className="info-banner" style={{ marginTop: 22 }}>
              Never paste production secrets into demo settings. Follow
              docs/PROVIDER_INTEGRATION.md to configure and validate the
              adapter.
            </div>
          </div>
          <div className="modal-footer">
            <button className="button secondary" onClick={close}>
              Close
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}

export function Settings({ refresh, changed, notify }: PageProps) {
  const { data, error, loading } = useData("/admin/settings", refresh);
  const [tab, setTab] = useState("general"),
    [busy, setBusy] = useState(false),
    [saveError, setSaveError] = useState("");
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setSaveError("");
    const f = new FormData(event.currentTarget),
      values: RecordData = {};
    f.forEach((v, k) => {
      values[k] = v;
    });
    if (tab === "general") {
      values.maintenance_mode = f.has("maintenance_mode");
    }
    if (tab === "telegram")
      values.subscription_required = f.has("subscription_required");
    for (const key of ["low_stock_threshold"])
      if (key in values) values[key] = Number(values[key]);
    try {
      await put("/admin/settings", { ...data, ...values });
      changed();
      notify("Store settings saved.");
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="MAKE IT YOURS"
        title="Store settings"
        description="The details that make your storefront work for you."
      />
      <ErrorBox message={error || saveError} />
      {loading && !data ? (
        <Loading />
      ) : (
        data && (
          <div className="settings-layout">
            <div>
              <div className="settings-nav">
                {[
                  { id: "general", label: "General" },
                  { id: "links", label: "Links & support" },
                  { id: "payments", label: "Currency" },
                  { id: "telegram", label: "Telegram & access" },
                ].map((t) => (
                  <button
                    className={tab === t.id ? "active" : ""}
                    onClick={() => setTab(t.id)}
                    key={t.id}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
              <div className="settings-help">
                Settings are stored in the database. Every saved change is
                recorded in the immutable audit log.
              </div>
            </div>
            <form
              key={`${tab}-${refresh}`}
              className="panel settings-panel"
              onSubmit={save}
            >
              <h2>
                {
                  (
                    {
                      general: "General settings",
                      links: "Links & support",
                      payments: "Display currency",
                      telegram: "Telegram storefront",
                    } as Record<string, string>
                  )[tab]
                }
              </h2>
              <p>Keep business details configurable, not hard-coded.</p>
              <div className="form-grid">
                {tab === "general" && (
                  <>
                    <label className="full">
                      Brand name
                      <input
                        name="store_name"
                        defaultValue={data.store_name}
                        required
                        maxLength={80}
                      />
                    </label>
                    <label>
                      Store language
                      <select
                        name="default_language"
                        defaultValue={data.default_language}
                      >
                        <option value="en">English</option>
                        <option value="ru">Русский</option>
                        <option value="uk">Українська</option>
                      </select>
                    </label>
                    <label>
                      Low-stock alert threshold
                      <input
                        name="low_stock_threshold"
                        type="number"
                        min="0"
                        max="1000"
                        defaultValue={data.low_stock_threshold}
                        required
                      />
                    </label>
                    <label className="checkbox-label full">
                      <input
                        name="maintenance_mode"
                        type="checkbox"
                        defaultChecked={data.maintenance_mode}
                      />
                      Enable maintenance mode
                    </label>
                    <div className="info-banner full">
                      Maintenance mode stops purchases without deleting customer
                      carts or history.
                    </div>
                  </>
                )}
                {tab === "links" && (
                  <>
                    {[
                      { key: "support_url", label: "Support URL" },
                      { key: "reviews_url", label: "Reviews channel URL" },
                      {
                        key: "stock_channel_url",
                        label: "Stock notification URL",
                      },
                      { key: "terms_url", label: "Terms of service URL" },
                    ].map((field) => (
                      <label className="full" key={field.key}>
                        {field.label}
                        <input
                          type="url"
                          name={field.key}
                          defaultValue={data[field.key] ?? ""}
                          placeholder="https://…"
                        />
                      </label>
                    ))}
                  </>
                )}
                {tab === "payments" && (
                  <>
                    <label>
                      Display exchange rate
                      <input
                        name="usd_uah_rate"
                        type="number"
                        min="0.01"
                        step="0.01"
                        defaultValue={data.usd_uah_rate}
                        required
                      />
                      <small>UAH per USD. Display only.</small>
                    </label>
                    <label>
                      Base currency
                      <input value="USD" disabled />
                      <small>All accounting uses integer USD cents.</small>
                    </label>
                    <label>
                      Display currency
                      <select
                        name="display_currency"
                        defaultValue={data.display_currency}
                      >
                        <option value="USD">USD</option>
                        <option value="UAH">UAH</option>
                      </select>
                    </label>
                    <div className="info-banner full">
                      Provider fees are added to the amount paid, never deducted
                      from the requested wallet credit. Live provider activation
                      requires a verified adapter.
                    </div>
                  </>
                )}
                {tab === "telegram" && (
                  <>
                    <label className="checkbox-label full">
                      <input
                        type="checkbox"
                        name="subscription_required"
                        defaultChecked={data.subscription_required}
                      />
                      Require verified channel subscription
                    </label>
                    <label className="full">
                      Welcome message
                      <textarea
                        name="welcome_message"
                        defaultValue={data.welcome_message}
                        maxLength={2000}
                      />
                      <small>Available placeholder: {"{store_name}"}</small>
                    </label>
                    <div className="info-banner blue full">
                      <Send size={20} />
                      The bot token and subscription channel are configured
                      through the environment. Enabling the gate without a
                      configured channel blocks access safely. See bot/README.md
                      for setup. Custom welcome templates are stored for future
                      bot integration.
                    </div>
                  </>
                )}
              </div>
              <Submit busy={busy}>Save changes</Submit>
            </form>
          </div>
        )
      )}
    </>
  );
}

export function Audit({ refresh }: PageProps) {
  const { data, error, loading } = useData("/admin/audit", refresh);
  const [query, setQuery] = useState(""),
    [selected, setSelected] = useState<RecordData | null>(null);
  const close = useCallback(() => setSelected(null), []);
  const { filtered, visible, page, setPage } = useFilter(data, query);
  return (
    <>
      <PageHeader
        eyebrow="A CLEAR TRAIL, ALWAYS"
        title="Audit log"
        description="An append-only record of changes across your marketplace."
      />
      <ErrorBox message={error} />
      <section className="panel">
        <div className="toolbar">
          <SearchBox
            value={query}
            onChange={setQuery}
            placeholder="Search actor, action, or object…"
          />
          <span className="toolbar-count">
            <ShieldCheck
              size={13}
              style={{ verticalAlign: "middle", marginRight: 5 }}
            />
            Immutable history
          </span>
        </div>
        {loading && !data ? (
          <Loading />
        ) : (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Event</th>
                    <th>Actor</th>
                    <th>Object</th>
                    <th>Reference</th>
                    <th>Time</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((event) => (
                    <tr key={event.id}>
                      <td>
                        <div className="customer-cell">
                          <ShieldCheck size={15} />
                          <span>
                            {human(String(event.action).replaceAll(".", "_"))}
                          </span>
                        </div>
                      </td>
                      <td>{event.actor ?? event.actor_id}</td>
                      <td>{human(event.object_type)}</td>
                      <td className="code">
                        {String(event.object_id ?? "").slice(0, 18)}
                      </td>
                      <td className="muted">
                        {date(event.created_at)} · {time(event.created_at)}
                      </td>
                      <td>
                        <button
                          className="icon-button"
                          aria-label={`Inspect audit event ${event.id}`}
                          onClick={() => setSelected(event)}
                        >
                          <ArrowUpRight size={16} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visible.length && (
                <Empty
                  title="No matching events"
                  text="Privileged actions and balance changes are recorded here."
                />
              )}
            </div>
            <Pagination total={filtered.length} page={page} setPage={setPage} />
          </>
        )}
      </section>
      {selected && (
        <Modal title="Audit event" subtitle={selected.id} close={close}>
          <div className="modal-body">
            <dl className="detail-grid">
              <div>
                <dt>Action</dt>
                <dd>{selected.action}</dd>
              </div>
              <div>
                <dt>Actor</dt>
                <dd>{selected.actor ?? selected.actor_id}</dd>
              </div>
              <div>
                <dt>Object</dt>
                <dd>{selected.object_type}</dd>
              </div>
              <div>
                <dt>Time</dt>
                <dd>
                  {date(selected.created_at)} · {time(selected.created_at)}
                </dd>
              </div>
            </dl>
            <h3 className="section-label">Change details</h3>
            <pre
              style={{
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                background: "#f6f8fa",
                padding: 16,
                borderRadius: 7,
                fontSize: 11,
                lineHeight: 1.7,
                color: "#718092",
              }}
            >
              {JSON.stringify(
                selected.details ?? selected.after_json ?? selected.after ?? {},
                null,
                2,
              )}
            </pre>
          </div>
        </Modal>
      )}
    </>
  );
}
