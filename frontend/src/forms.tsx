import { useRef, useState } from "react";
import {
  ArrowDownToLine,
  Check,
  CheckCircle2,
  Minus,
  Plus,
  Send,
  ShieldCheck,
  ShoppingBag,
  Upload,
  Wallet,
} from "lucide-react";
import { money, post, put, rows, type RecordData } from "./api";
import { useData } from "./hooks";
import { Empty, ErrorBox, Loading, Modal, Submit } from "./ui";

export function StockForm({
  close,
  onSuccess,
}: {
  close: () => void;
  onSuccess: () => void;
}) {
  const { data, error: loadError } = useData("/admin/skus");
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    try {
      await post("/admin/inventory", {
        sku_id: f.get("sku_id"),
        reference: f.get("reference"),
        payload: f.get("payload"),
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
      title="Add inventory"
      subtitle="One stock unit. One traceable delivery."
      close={close}
    >
      <form onSubmit={submit}>
        <div className="modal-body">
          <ErrorBox message={error || loadError} />
          <div className="form-grid">
            <label className="full">
              Product
              <select name="sku_id" required defaultValue="">
                <option value="" disabled>
                  Select a product
                </option>
                {rows(data)
                  .filter((s) => s.enabled)
                  .map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.flag} {s.title} — {money(s.price_cents)}
                    </option>
                  ))}
              </select>
            </label>
            <label className="full">
              External reference
              <input
                name="reference"
                required
                maxLength={160}
                placeholder="e.g. STOCK-UA-0001"
              />
              <small>
                A unique reference from your source or inventory system.
              </small>
            </label>
            <label className="full">
              Delivery payload
              <textarea
                name="payload"
                required
                maxLength={20000}
                placeholder="The authorized digital content for this stock unit…"
                rows={5}
                autoComplete="off"
              />
              <small>
                Encrypted at rest. Never shown in ordinary inventory listings.
              </small>
            </label>
            <label className="checkbox-label full">
              <input type="checkbox" required />I am authorized to distribute
              this inventory.
            </label>
            <div className="info-banner blue full">
              <ShieldCheck size={19} />
              Only add goods you lawfully control. External provider delivery
              and authentication-code retrieval are not active in this release.
            </div>
          </div>
        </div>
        <div className="modal-footer">
          <button type="button" className="button secondary" onClick={close}>
            Cancel
          </button>
          <Submit busy={busy}>Add stock unit</Submit>
        </div>
      </form>
    </Modal>
  );
}

export function ImportForm({
  close,
  onSuccess,
}: {
  close: () => void;
  onSuccess: () => void;
}) {
  const { data } = useData("/admin/skus");
  const [format, setFormat] = useState("csv"),
    [content, setContent] = useState(""),
    [sku, setSku] = useState(""),
    [preview, setPreview] = useState<RecordData | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  async function readFile(file?: File) {
    if (!file) return;
    setPreview(null);
    setError("");
    if (file.size > 1000000) {
      setError("The file must be smaller than 1 MB.");
      return;
    }
    if (!/\.(csv|json)$/i.test(file.name)) {
      setError("Choose a CSV or JSON file.");
      return;
    }
    setFormat(file.name.toLowerCase().endsWith(".json") ? "json" : "csv");
    setContent(await file.text());
  }
  async function validate() {
    setBusy(true);
    setError("");
    try {
      setPreview(
        await post("/admin/inventory/import/preview", {
          format,
          content,
          ...(sku ? { sku_id: sku } : {}),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function confirm() {
    setBusy(true);
    setError("");
    try {
      await post("/admin/inventory/import/confirm", {
        batch_id: preview!.batch_id,
      });
      onSuccess();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function downloadTemplate() {
    const text =
      "sku_id,reference,payload\n,YOUR-UNIQUE-REF,Your authorized deliverable\n";
    const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "inventory-template.csv";
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <Modal
      title="Import inventory"
      subtitle="Upload, validate, then confirm. No silent row drops."
      close={close}
      wide
    >
      <div className="modal-body">
        <ErrorBox message={error} />
        {!preview ? (
          <>
            <label
              className="file-drop"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                void readFile(e.dataTransfer.files[0]);
              }}
            >
              <Upload size={29} />
              <strong>Drop your inventory file here</strong>
              <small>CSV or JSON · up to 1 MB</small>
              <input
                ref={input}
                type="file"
                accept=".csv,.json"
                aria-label="Choose inventory file"
                onChange={(e) => void readFile(e.target.files?.[0])}
              />
            </label>
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                margin: "12px 0 20px",
              }}
            >
              <button className="text-button" onClick={downloadTemplate}>
                <ArrowDownToLine size={13} />
                Download CSV template
              </button>
            </div>
            <div className="form-grid">
              <label>
                File format
                <select
                  value={format}
                  onChange={(e) => setFormat(e.target.value)}
                >
                  <option value="csv">CSV</option>
                  <option value="json">JSON</option>
                </select>
              </label>
              <label>
                Default product (optional)
                <select value={sku} onChange={(e) => setSku(e.target.value)}>
                  <option value="">Use each row’s sku_id</option>
                  {rows(data).map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.title}
                    </option>
                  ))}
                </select>
              </label>
              <label className="full">
                Or paste inventory data
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  rows={6}
                  placeholder={
                    format === "csv"
                      ? "sku_id,reference,payload\nus-license,YOUR-REF,Your authorized deliverable"
                      : '[{"sku_id":"us-license","reference":"YOUR-REF","payload":"Your authorized deliverable"}]'
                  }
                />
                <small>
                  Required fields: sku_id (or default product), reference,
                  payload.
                </small>
              </label>
            </div>
          </>
        ) : (
          <>
            <div
              className={
                preview.errors?.length ? "info-banner" : "check-summary"
              }
            >
              <CheckCircle2 size={18} />
              {preview.valid_count} of {preview.total_count} rows are valid.
              {preview.errors?.length
                ? " Correct the errors before importing."
                : " Ready to import."}
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Row</th>
                    <th>Product ID</th>
                    <th>Reference</th>
                    <th>Validation</th>
                  </tr>
                </thead>
                <tbody>
                  {rows(preview.rows)
                    .slice(0, 15)
                    .map((row, i) => (
                      <tr key={i}>
                        <td>{i + 1}</td>
                        <td className="code">{row.sku_id}</td>
                        <td>{row.reference}</td>
                        <td>
                          <span style={{ color: "#72a184" }}>
                            {row.status ?? "Valid"}
                          </span>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
            {preview.total_count > 15 && (
              <p className="muted" style={{ margin: "15px 0" }}>
                Showing the first 15 rows of {preview.total_count}.
              </p>
            )}
            {preview.errors?.length > 0 && (
              <div className="import-errors">
                {preview.errors.map((e: RecordData, i: number) => (
                  <div key={i}>
                    Row {e.row}: {e.message}
                  </div>
                ))}
              </div>
            )}
            <div className="info-banner blue" style={{ marginTop: 20 }}>
              <ShieldCheck size={18} />
              Payloads are encrypted. The entire import is validated again
              before committing; duplicate references are never added twice.
            </div>
          </>
        )}
      </div>
      <div className="modal-footer">
        <button
          className="button secondary"
          onClick={preview ? () => setPreview(null) : close}
        >
          {preview ? "Back to file" : "Cancel"}
        </button>
        {preview ? (
          <button
            className="button primary"
            disabled={
              busy || !preview.valid_count || preview.errors?.length > 0
            }
            onClick={confirm}
          >
            <Check size={15} />
            {busy ? "Importing…" : `Import ${preview.valid_count} units`}
          </button>
        ) : (
          <button
            className="button primary"
            disabled={busy || !content.trim()}
            onClick={validate}
          >
            <ShieldCheck size={15} />
            {busy ? "Validating…" : "Validate inventory"}
          </button>
        )}
      </div>
    </Modal>
  );
}

export function SkuForm({
  sku,
  close,
  onSuccess,
}: {
  sku: RecordData | null;
  close: () => void;
  onSuccess: () => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const f = new FormData(e.currentTarget);
    const code = String(f.get("country_code")).toUpperCase();
    const toCents = (input: string) => {
      if (!/^\d+(\.\d{1,2})?$/.test(input))
        throw new Error("Prices must have no more than two decimal places.");
      const [d, c = ""] = input.split(".");
      return Number(d) * 100 + Number(c.padEnd(2, "0"));
    };
    try {
      const body = {
        name: f.get("name"),
        country: f.get("country"),
        country_code: code,
        flag: String.fromCodePoint(
          ...[...code].map((c) => 127397 + c.charCodeAt(0)),
        ),
        category: f.get("category"),
        retail_price_cents: toCents(String(f.get("retail_price"))),
        wholesale_price_cents: toCents(String(f.get("wholesale_price"))),
        description: f.get("description"),
        active: f.has("active"),
      };
      if (sku) await put(`/admin/skus/${sku.id}`, body);
      else await post("/admin/skus", body);
      onSuccess();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={sku ? "Edit product" : "Create a product"}
      subtitle="A product type groups individually tracked stock units."
      close={close}
    >
      <form onSubmit={submit}>
        <div className="modal-body">
          <ErrorBox message={error} />
          <div className="form-grid">
            <label className="full">
              Product name
              <input
                name="name"
                required
                maxLength={160}
                defaultValue={sku?.name}
                placeholder="e.g. Creator Pack · Ukraine"
              />
            </label>
            <label>
              Country name
              <input
                name="country"
                required
                maxLength={80}
                defaultValue={sku?.country}
                placeholder="Ukraine"
              />
            </label>
            <label>
              ISO country code
              <input
                name="country_code"
                required
                pattern="[A-Za-z]{2}"
                maxLength={2}
                defaultValue={sku?.country_code}
                placeholder="UA"
              />
            </label>
            <label>
              Retail price (USD)
              <input
                name="retail_price"
                type="number"
                min="0.01"
                max="1000000"
                step="0.01"
                defaultValue={
                  sku ? (sku.retail_price_cents / 100).toFixed(2) : ""
                }
                required
                placeholder="0.00"
              />
            </label>
            <label>
              Wholesale price (USD)
              <input
                name="wholesale_price"
                type="number"
                min="0.01"
                max="1000000"
                step="0.01"
                defaultValue={
                  sku ? (sku.wholesale_price_cents / 100).toFixed(2) : ""
                }
                required
                placeholder="0.00"
              />
            </label>
            <label className="full">
              Product category
              <input
                name="category"
                required
                maxLength={80}
                defaultValue={sku?.category ?? "Digital goods"}
              />
            </label>
            <label className="full">
              Description
              <textarea
                name="description"
                maxLength={2000}
                defaultValue={sku?.description}
                placeholder="What should your customers know?"
              />
            </label>
            <label className="checkbox-label full">
              <input
                type="checkbox"
                name="active"
                defaultChecked={sku?.active ?? true}
              />
              Visible and available for sale
            </label>
            <div className="info-banner full">
              This release supports encrypted local payloads. Provider-backed
              delivery modes require a separately verified adapter.
            </div>
          </div>
        </div>
        <div className="modal-footer">
          <button className="button secondary" type="button" onClick={close}>
            Cancel
          </button>
          <Submit busy={busy}>{sku ? "Save product" : "Create product"}</Submit>
        </div>
      </form>
    </Modal>
  );
}

export function Storefront({
  close,
  onChange,
  demo,
}: {
  close: () => void;
  onChange: () => void;
  demo: boolean;
}) {
  const [refresh, setRefresh] = useState(0),
    [tab, setTab] = useState("catalog"),
    [cart, setCart] = useState<Record<string, number>>({}),
    [userId, setUserId] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [order, setOrder] = useState<RecordData | null>(null);
  const skus = useData("/admin/skus", refresh),
    users = useData("/admin/users", refresh);
  const products = rows(skus.data).filter((s) => s.enabled);
  const user =
    rows(users.data).find((u) => u.id === userId) ?? rows(users.data)[0];
  const total = products.reduce(
    (sum, p) => sum + p.price_cents * (cart[p.id] ?? 0),
    0,
  );
  const quantity = Object.values(cart).reduce((a, b) => a + b, 0);
  const checkoutKey = useRef(crypto.randomUUID());
  function add(id: string, amount = 1) {
    setCart((old) => {
      const next = { ...old, [id]: Math.max(0, (old[id] ?? 0) + amount) };
      if (!next[id]) delete next[id];
      return next;
    });
    checkoutKey.current = crypto.randomUUID();
    setOrder(null);
    setError("");
  }
  async function checkout() {
    setBusy(true);
    setError("");
    try {
      const result = await post("/admin/demo/checkout", {
        user_id: user.id,
        items: Object.entries(cart).map(([sku_id, quantity]) => ({
          sku_id,
          quantity,
        })),
        idempotency_key: checkoutKey.current,
        expected_total_cents: total,
      });
      setOrder(result);
      setCart({});
      setRefresh((n) => n + 1);
      onChange();
      checkoutKey.current = crypto.randomUUID();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title="Storefront test bench"
      subtitle="Exercise the real checkout service with synthetic inventory."
      close={close}
    >
      <div className="storefront">
        <div className="storefront-banner">
          <Send size={30} />
          <h3>Arshisney Store</h3>
          <p>Your digital goods, one tap away.</p>
        </div>
        {!demo ? (
          <div className="info-banner">
            The test bench is only enabled in an isolated demo environment.
          </div>
        ) : (
          <>
            <div className="info-banner">
              Demo only · no real payment, account, or license. This is a
              service simulator, not a live Telegram session.
            </div>
            <ErrorBox message={error || skus.error || users.error} />
            {skus.loading || users.loading ? (
              <Loading />
            ) : (
              <>
                <label style={{ marginBottom: 15 }}>
                  Test customer
                  <select
                    value={user?.id ?? ""}
                    disabled={busy}
                    onChange={(e) => {
                      setUserId(e.target.value);
                      checkoutKey.current = crypto.randomUUID();
                      setOrder(null);
                    }}
                  >
                    {rows(users.data).map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.name} · {money(u.balance_cents)}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="storefront-balance">
                  <span>
                    <Wallet
                      size={15}
                      style={{ verticalAlign: "middle", marginRight: 6 }}
                    />
                    Available balance
                  </span>
                  <strong>{money(user?.balance_cents)}</strong>
                </div>
                <div className="storefront-tabs">
                  <button
                    className={tab === "catalog" ? "active" : ""}
                    onClick={() => setTab("catalog")}
                  >
                    Catalog
                  </button>
                  <button
                    className={tab === "cart" ? "active" : ""}
                    onClick={() => setTab("cart")}
                  >
                    Cart ({quantity})
                  </button>
                </div>
                {order && (
                  <div className="check-summary">
                    <CheckCircle2 size={20} />
                    <span>
                      Order #{order.number} created. {money(order.total_cents)}{" "}
                      debited exactly once. Local payloads are available through
                      the owning customer’s purchase history.
                    </span>
                  </div>
                )}
                {tab === "catalog" ? (
                  products.map((product) => (
                    <div className="storefront-product" key={product.id}>
                      <span className="country-icon">{product.flag}</span>
                      <div>
                        <strong>{product.title}</strong>
                        <p>
                          {money(product.price_cents)} · {product.available}{" "}
                          available
                        </p>
                      </div>
                      <button
                        className="button secondary small"
                        aria-label={`Add ${product.title} to test cart`}
                        disabled={
                          busy || (cart[product.id] ?? 0) >= product.available
                        }
                        onClick={() => add(product.id)}
                      >
                        <Plus size={15} />
                        {cart[product.id] || "Add"}
                      </button>
                    </div>
                  ))
                ) : (
                  <>
                    {products
                      .filter((p) => cart[p.id])
                      .map((product) => (
                        <div className="storefront-product" key={product.id}>
                          <div>
                            <strong>{product.title}</strong>
                            <p>
                              {cart[product.id]} × {money(product.price_cents)}
                            </p>
                          </div>
                          <button
                            className="icon-button"
                            aria-label={`Remove one ${product.title}`}
                            disabled={busy}
                            onClick={() => add(product.id, -1)}
                          >
                            <Minus size={16} />
                          </button>
                          <span>{cart[product.id]}</span>
                          <button
                            className="icon-button"
                            aria-label={`Add one ${product.title}`}
                            disabled={
                              busy || cart[product.id] >= product.available
                            }
                            onClick={() => add(product.id)}
                          >
                            <Plus size={16} />
                          </button>
                        </div>
                      ))}
                    {!quantity && !order && (
                      <Empty
                        title="Your cart is empty"
                        text="Add a product from the catalog to test checkout."
                      />
                    )}
                    {quantity > 0 && (
                      <>
                        <div className="storefront-cart-total">
                          <strong>Total</strong>
                          <strong>{money(total)}</strong>
                        </div>
                        <button
                          style={{ width: "100%" }}
                          className="button primary"
                          disabled={busy || !user}
                          onClick={checkout}
                        >
                          <ShoppingBag size={16} />
                          {busy
                            ? "Checking out…"
                            : `Pay ${money(total)} from balance`}
                        </button>
                        <p
                          style={{
                            fontSize: 10,
                            textAlign: "center",
                            marginTop: 10,
                          }}
                        >
                          Server-side prices, exact stock allocation, atomic
                          debit.
                        </p>
                      </>
                    )}
                  </>
                )}
              </>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
