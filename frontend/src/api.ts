export type RecordData = Record<string, any>;
let csrf = "";

export async function api<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(csrf ? { "X-CSRF-Token": csrf } : {}),
      ...(method !== "GET" ? { "Idempotency-Key": crypto.randomUUID() } : {}),
      ...options.headers,
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      body.detail ?? body.error ?? "The request could not be completed.";
    throw new Error(
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: any) => d.msg).join(", ")
          : (detail.message ?? JSON.stringify(detail)),
    );
  }
  if (body.csrf_token) csrf = body.csrf_token;
  return normalize(path, body) as T;
}

function normalize(path: string, body: any): any {
  if (
    path === "/admin/settings" ||
    path.includes("/auth/") ||
    path === "/health"
  )
    return body;
  const sku = (r: RecordData) => ({
    ...r,
    title: r.name,
    country_name: r.country,
    country_iso2: r.country_code,
    price_cents: r.retail_price_cents,
    available: r.stock_count,
    enabled: r.active,
    code: r.id,
    section: "retail",
  });
  const order = (r: RecordData) => ({
    ...r,
    status: r.status.toUpperCase(),
    number: String(r.id).slice(0, 8).toUpperCase(),
    customer: r.username ? `@${r.username.replace("@", "")}` : r.user_name,
    product: r.items?.[0]?.sku_name ?? "Digital goods",
    items: (r.items ?? []).map((item: RecordData) => ({
      ...item,
      sku_title: item.sku_name,
      quantity: 1,
      line_total_cents: item.unit_price_cents,
    })),
    inventory_units: (r.items ?? []).map((item: RecordData) => ({
      id: item.inventory_id,
      status: "SOLD",
      delivery_status: "SOLD",
    })),
  });
  if (path === "/admin/skus")
    return Array.isArray(body) ? body.map(sku) : sku(body);
  if (path === "/admin/inventory")
    return Array.isArray(body)
      ? body.map((r) => ({
          ...r,
          status: r.status.toUpperCase(),
          external_item_id: r.reference,
          sku_title: r.sku_name,
          country_name: r.country,
          country_iso2: r.country_code,
          source: r.provider,
          delivery_mode: r.category,
        }))
      : body;
  if (path === "/admin/orders") return body.map(order);
  if (/^\/admin\/orders\/[^/]+$/.test(path) || path === "/admin/demo/checkout")
    return order(body);
  if (path === "/admin/topups")
    return body.map((r: RecordData) => ({
      ...r,
      status: r.status === "pending" ? "UNDER_REVIEW" : r.status.toUpperCase(),
      customer: `@${r.username.replace("@", "")}`,
      provider: r.method,
      requested_credit_cents: r.amount_cents,
      fee_cents: 0,
      amount_to_pay_cents: r.amount_cents,
      receipt_reference: `${r.reference} — ${r.note}`,
    }));
  if (path === "/admin/users")
    return body.map((r: RecordData) => ({
      ...r,
      first_name: r.name,
      telegram_user_id: r.telegram_user_id ?? "Not linked",
    }));
  if (path === "/admin/providers")
    return body.map((r: RecordData) => ({
      ...r,
      code: r.id,
      health_status: r.status.toUpperCase(),
    }));
  if (path === "/admin/audit")
    return body.map((r: RecordData) => ({
      ...r,
      object_type: r.entity_type,
      object_id: r.entity_id,
      details: r.detail,
    }));
  if (path === "/admin/dashboard")
    return {
      ...body,
      stats: {
        ...body.stats,
        revenue_7d_cents: body.revenue_chart
          .slice(-7)
          .reduce((sum: number, d: RecordData) => sum + d.revenue_cents, 0),
        total_orders: body.orders_count,
        available_stock: body.stock_count,
        active_users: body.users_count,
        reserved_stock: body.reserved_stock ?? body.stats?.reserved_stock ?? 0,
        pending_manual_payments: body.pending_topups,
        wallet_liability_cents:
          body.wallet_liability_cents ??
          body.stats?.wallet_liability_cents ??
          0,
        failed_deliveries: body.failed_deliveries ?? null,
      },
      recent_orders: body.recent_orders.map(order),
      low_stock: (body.low_stock ?? []).map(sku),
      revenue_series: body.revenue_chart,
    };
  return body;
}

export const post = <T = any>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const put = <T = any>(path: string, body: unknown) =>
  api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const rows = (data: any): RecordData[] =>
  Array.isArray(data) ? data : (data?.items ?? []);
export const money = (cents: number = 0) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    cents / 100,
  );
export const count = (n: number = 0) =>
  new Intl.NumberFormat("en-US").format(n);
export const date = (value: string) =>
  value
    ? new Date(value).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
      })
    : "—";
export const time = (value: string) =>
  value
    ? new Date(value).toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
export const human = (value: string = "") =>
  value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/^./, (x) => x.toUpperCase());
