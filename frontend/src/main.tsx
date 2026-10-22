import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type User = { id: string; org_id: string; email: string; role: string };
type Product = {
  id: string;
  name: string;
  sku: string;
  price_cents: number;
  available: number;
  reserved: number;
  sold: number;
  active: boolean;
};
type Order = {
  id: string;
  status: string;
  subtotal_cents: number;
  discount_cents: number;
  tax_cents: number;
  total_cents: number;
  created_at: string;
  lines: {
    product_id: string;
    name: string;
    quantity: number;
    unit_price_cents: number;
  }[];
  events: { id: string; kind: string; actor: string; created_at: string }[];
};
type Session = { access_token: string; user: User };
const money = (value: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    value / 100,
  );
const label = (value: string) => value.toLowerCase().replaceAll("_", " ");
const date = (value: string) => new Date(value).toLocaleString();

function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [email, setEmail] = useState("admin.a@orderflow.test");
  const [password, setPassword] = useState("");
  const [view, setView] = useState("products");
  const [products, setProducts] = useState<Product[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [selected, setSelected] = useState<Order | null>(null);
  const [cart, setCart] = useState<Record<string, number>>({});
  const [checkoutKey, setCheckoutKey] = useState<string | null>(null);
  const [editing, setEditing] = useState<Product | "new" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [productPage, setProductPage] = useState(0);
  const [orderPage, setOrderPage] = useState(0);
  const merchant = session?.user.role !== "customer";
  const admin = session?.user.role === "admin";

  async function api<T>(
    path: string,
    method = "GET",
    body?: unknown,
    extra: Record<string, string> = {},
  ): Promise<T> {
    const response = await fetch(`/api${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(session ? { Authorization: `Bearer ${session.access_token}` } : {}),
        ...extra,
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 401 && session) setSession(null);
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "Please check the values and try again.",
      );
    }
    return data;
  }
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }
  async function refresh() {
    const [nextProducts, nextOrders] = await Promise.all([
      api<Product[]>(
        `/products?limit=12&offset=${productPage * 12}&q=${encodeURIComponent(search)}`,
      ),
      api<Order[]>(
        `/orders?limit=12&offset=${orderPage * 12}${status ? `&status=${status}` : ""}`,
      ),
    ]);
    setProducts(nextProducts);
    setOrders(nextOrders);
  }
  useEffect(() => {
    if (session) void run(refresh);
  }, [session, search, status, productPage, orderPage]);

  async function openOrder(id: string) {
    const order = await api<Order>(`/orders/${id}`);
    setSelected(order);
    setView("orders");
  }
  function logout() {
    setSession(null);
    setProducts([]);
    setOrders([]);
    setCart({});
    setSelected(null);
    setCheckoutKey(null);
    setError("");
    setNotice("");
    setPassword("");
    setSearch("");
    setStatus("");
    setEditing(null);
  }
  async function orderAction(action: string, body?: unknown) {
    if (!selected) return;
    await api(
      action === "simulate"
        ? `/dev/orders/${selected.id}/simulate`
        : `/orders/${selected.id}/${action}`,
      "POST",
      body,
    );
    await openOrder(selected.id);
    await refresh();
    setNotice(
      action === "simulate"
        ? "Payment simulator result recorded."
        : `Order ${action} completed.`,
    );
  }
  async function checkout() {
    const key = checkoutKey || crypto.randomUUID();
    setCheckoutKey(key);
    const order = await api<Order>(
      "/orders",
      "POST",
      {
        items: Object.entries(cart)
          .filter(([, quantity]) => quantity > 0)
          .map(([product_id, quantity]) => ({ product_id, quantity })),
      },
      { "Idempotency-Key": key },
    );
    setCart({});
    setCheckoutKey(null);
    await openOrder(order.id);
    await refresh();
  }
  async function saveProduct(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    await run(async () => {
      const body = {
        name: String(data.get("name")),
        sku: String(data.get("sku")),
        price_cents: Math.round(Number(data.get("price")) * 100),
        active: data.get("active") === "on",
      };
      const available = Number(data.get("available"));
      if (editing === "new")
        await api("/products", "POST", {
          ...body,
          available: admin ? available : 0,
        });
      else if (editing) {
        await api(`/products/${editing.id}`, "PATCH", {
          ...body,
          ...(admin ? { available } : {}),
        });
      }
      setEditing(null);
      await refresh();
      setNotice("Product saved.");
    });
  }

  if (!session)
    return (
      <main className="login-page">
        <div className="login-story">
          <a className="brand" href="/">
            ◈ <span>OrderFlow</span>
          </a>
          <span className="eyebrow">A little more order.</span>
          <h1>
            Good things.
            <br />
            Moving forward.
          </h1>
          <p>
            A considered workspace for your products, inventory, and every order
            in between.
          </p>
          <div className="login-foot">
            LOCAL PAYMENT SIMULATION <span>● No real charges</span>
          </div>
        </div>
        <div className="login-wrap shell">
          <form
            className="login-panel core"
            onSubmit={(event) => {
              event.preventDefault();
              void run(async () => {
                const next = await api<Session>("/auth/login", "POST", {
                  email,
                  password,
                });
                setSession(next);
                setPassword("");
                setView("products");
              });
            }}
          >
            <span className="eyebrow">Your workspace awaits</span>
            <h2>Welcome back.</h2>
            <p className="muted">Sign in to pick up where you left off.</p>
            <label>
              Email
              <input
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label>
              Password
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            {error && (
              <p role="alert" className="error">
                {error}
              </p>
            )}
            <button disabled={busy} className="primary">
              {busy ? "Signing in…" : "Enter workspace"}{" "}
              <span className="arrow">↗</span>
            </button>
            <div className="demo">
              <strong>Development demo</strong>
              <p>
                Use admin.a, staff.a, customer.a, or customer2.a
                <br />
                @orderflow.test · Password: Orderflow123!
              </p>
              <small>Use the .b accounts for the second merchant.</small>
            </div>
          </form>
        </div>
      </main>
    );

  const cartCount = Object.values(cart).reduce((sum, qty) => sum + qty, 0);
  const edit = editing && editing !== "new" ? editing : null;
  return (
    <div className="app">
      <aside className="sidebar">
        <a className="brand" href="/">
          ◈ <span>OrderFlow</span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">
            {session.user.org_id === "org-a" ? "N" : "J"}
          </span>
          <div>
            <strong>
              {session.user.org_id === "org-a"
                ? "Northstar Supply"
                : "Juniper Trading"}
            </strong>
            <small>{session.user.role} workspace</small>
          </div>
        </div>
        <nav aria-label="Main navigation">
          <button
            className={view === "products" ? "nav active" : "nav"}
            onClick={() => {
              setView("products");
              setSelected(null);
            }}
          >
            ▦{" "}
            <span>
              {merchant ? "Products & inventory" : "Shop the collection"}
            </span>
          </button>
          <button
            aria-label="Orders"
            className={view === "orders" ? "nav active" : "nav"}
            onClick={() => {
              setView("orders");
              setSelected(null);
            }}
          >
            ▤ <span>Orders</span>
          </button>
        </nav>
        <div className="sidebar-bottom">
          <div className="sim-label">● Simulator connected</div>
          <small>
            Development environment
            <br />
            USD · 8.25% demo tax
          </small>
          <p className="email">{session.user.email}</p>
          <button className="text-button" onClick={logout}>
            Sign out ↗
          </button>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <span>
            Workspace{" "}
            <span className="muted">
              / {view === "products" ? "Collection" : "Orders"}
            </span>
          </span>
          <span className="environment">Development · Simulated payments</span>
        </header>
        {error && (
          <div role="alert" className="error banner">
            {error}
          </div>
        )}
        {notice && (
          <div role="status" className="notice banner">
            {notice}
          </div>
        )}
        {view === "products" ? (
          <>
            <section className="page-heading">
              <div>
                <span className="eyebrow">
                  {merchant ? "The merchant edit" : "Made for the everyday"}
                </span>
                <h1>
                  {merchant ? "Your collection." : "Find your next essential."}
                </h1>
                <p className="muted">
                  {merchant
                    ? "Keep your catalog considered. Keep your inventory in balance."
                    : "Thoughtful goods, ready for their next chapter."}
                </p>
              </div>
              {merchant && (
                <button className="primary" onClick={() => setEditing("new")}>
                  Add product <span className="arrow">＋</span>
                </button>
              )}
            </section>
            <div className="stats">
              <div>
                <span>Catalog on this page</span>
                <strong>{products.length.toString().padStart(2, "0")}</strong>
              </div>
              <div>
                <span>Available units</span>
                <strong>
                  {products.reduce((sum, p) => sum + p.available, 0)}
                </strong>
              </div>
              <div>
                <span>{merchant ? "Reserved for orders" : "In your bag"}</span>
                <strong>
                  {merchant
                    ? products.reduce((sum, p) => sum + p.reserved, 0)
                    : cartCount}
                </strong>
              </div>
            </div>
            <div className="section-toolbar">
              <h2>{merchant ? "All products" : "The collection"}</h2>
              <input
                aria-label="Search products"
                placeholder="Search the collection…"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setProductPage(0);
                }}
              />
            </div>
            <div className="product-grid">
              {products.map((product, index) => (
                <article className="product shell" key={product.id}>
                  <div className="core">
                    <div
                      className={`product-art art-${index % 3}`}
                      aria-hidden="true"
                    >
                      <span>
                        {product.name.toLowerCase().includes("tote")
                          ? "◡"
                          : product.name.toLowerCase().includes("cup")
                            ? "◒"
                            : "▱"}
                      </span>
                      <small>{product.sku}</small>
                    </div>
                    <div className="product-body">
                      <div className="product-title">
                        <h3>{product.name}</h3>
                        <strong>{money(product.price_cents)}</strong>
                      </div>
                      <p className="muted">
                        {product.available} available{" "}
                        {merchant &&
                          `· ${product.reserved} reserved · ${product.sold} sold`}
                      </p>
                      <div className="product-bottom">
                        <span
                          className={`badge ${product.active && product.available > 0 ? "good" : ""}`}
                        >
                          {!product.active
                            ? "Inactive"
                            : product.available > 0
                              ? "In stock"
                              : "Sold out"}
                        </span>
                        {merchant ? (
                          <button
                            className="secondary"
                            onClick={() => setEditing(product)}
                          >
                            Edit product ↗
                          </button>
                        ) : (
                          <label className="quantity">
                            Quantity
                            <input
                              aria-label={`Quantity for ${product.name}`}
                              type="number"
                              min="0"
                              max={product.available}
                              value={cart[product.id] || 0}
                              onChange={(e) => {
                                setCart({
                                  ...cart,
                                  [product.id]: Number(e.target.value),
                                });
                                setCheckoutKey(null);
                              }}
                            />
                          </label>
                        )}
                      </div>
                    </div>
                  </div>
                </article>
              ))}
            </div>
            {!products.length && (
              <div className="empty">
                No products found.{" "}
                {merchant
                  ? "Add your first product to get started."
                  : "Try another search."}
              </div>
            )}
            <div className="pagination">
              <button
                disabled={productPage === 0 || busy}
                onClick={() => setProductPage(productPage - 1)}
              >
                Previous
              </button>
              <span>Page {productPage + 1}</span>
              <button
                disabled={products.length < 12 || busy}
                onClick={() => setProductPage(productPage + 1)}
              >
                Next
              </button>
            </div>
            {!merchant && cartCount > 0 && (
              <div className="checkout-bar">
                <div>
                  <strong>
                    {cartCount} {cartCount === 1 ? "item" : "items"} in your bag
                  </strong>
                  <small>
                    Final prices and tax calculated securely at checkout.
                  </small>
                </div>
                <button
                  className="primary"
                  disabled={busy}
                  onClick={() => void run(checkout)}
                >
                  Create order <span className="arrow">↗</span>
                </button>
              </div>
            )}
          </>
        ) : selected ? (
          <>
            <button
              className="text-button back"
              onClick={() => setSelected(null)}
            >
              ← All orders
            </button>
            <section className="page-heading">
              <div>
                <span className="eyebrow">Order details</span>
                <h1>Order {selected.id.slice(0, 8)}.</h1>
                <p className="muted">{date(selected.created_at)}</p>
              </div>
              <span className={`badge status ${selected.status.toLowerCase()}`}>
                {label(selected.status)}
              </span>
            </section>
            <div className="detail-grid">
              <section className="shell">
                <div className="core detail-panel">
                  <h2>The order</h2>
                  <p className="muted order-reference">{selected.id}</p>
                  {selected.lines.map((line) => (
                    <div className="line-item" key={line.product_id}>
                      <div>
                        <strong>{line.name}</strong>
                        <small>
                          {line.quantity} × {money(line.unit_price_cents)}
                        </small>
                      </div>
                      <strong>
                        {money(line.quantity * line.unit_price_cents)}
                      </strong>
                    </div>
                  ))}
                  <div className="totals">
                    <p>
                      <span>Subtotal</span>
                      {money(selected.subtotal_cents)}
                    </p>
                    <p>
                      <span>Discount</span>−{money(selected.discount_cents)}
                    </p>
                    <p>
                      <span>Tax · 8.25%</span>
                      {money(selected.tax_cents)}
                    </p>
                    <p className="total">
                      <strong>Total · USD</strong>
                      <strong>{money(selected.total_cents)}</strong>
                    </p>
                  </div>
                  <div className="actions">
                    {selected.status === "PENDING_PAYMENT" && (
                      <>
                        <button
                          disabled={busy}
                          className="primary"
                          onClick={() =>
                            void run(() =>
                              orderAction("simulate", { outcome: "success" }),
                            )
                          }
                        >
                          Simulate successful payment
                        </button>
                        <button
                          disabled={busy}
                          onClick={() =>
                            void run(() =>
                              orderAction("simulate", { outcome: "failure" }),
                            )
                          }
                        >
                          Simulate failed payment
                        </button>
                        <button
                          disabled={busy}
                          onClick={() => void run(() => orderAction("cancel"))}
                        >
                          Cancel order
                        </button>
                      </>
                    )}
                    {merchant && selected.status === "PAID" && (
                      <button
                        disabled={busy}
                        className="primary"
                        onClick={() => void run(() => orderAction("fulfill"))}
                      >
                        Fulfill order
                      </button>
                    )}
                    {merchant &&
                      ["PAID", "FULFILLED"].includes(selected.status) && (
                        <button
                          disabled={busy}
                          onClick={() => void run(() => orderAction("refund"))}
                        >
                          Issue full simulated refund
                        </button>
                      )}
                  </div>
                  {selected.status === "PAYMENT_FAILED" && (
                    <p className="error">
                      Payment failed. Reserved stock has been released. Create a
                      new order to try again.
                    </p>
                  )}
                  {selected.status === "REFUNDED" && (
                    <p className="muted">
                      Full refund recorded. Goods are not automatically
                      restocked.
                    </p>
                  )}
                </div>
              </section>
              <section className="shell">
                <div className="core detail-panel">
                  <span className="eyebrow">Every step, accounted for</span>
                  <h2>Order history</h2>
                  <ol className="timeline">
                    {selected.events.map((event) => (
                      <li key={event.id}>
                        <span className="timeline-dot" />
                        <strong>{label(event.kind)}</strong>
                        <small>{date(event.created_at)}</small>
                        <small>By {event.actor}</small>
                      </li>
                    ))}
                  </ol>
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => void run(() => openOrder(selected.id))}
                  >
                    Refresh status ↻
                  </button>
                </div>
              </section>
            </div>
          </>
        ) : (
          <>
            <section className="page-heading">
              <div>
                <span className="eyebrow">From placed to delivered</span>
                <h1>{merchant ? "Every order. In order." : "Your orders."}</h1>
                <p className="muted">
                  A clear view of what’s moving, and what comes next.
                </p>
              </div>
            </section>
            <div className="section-toolbar">
              <h2>Order history</h2>
              <select
                aria-label="Filter order status"
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setOrderPage(0);
                }}
              >
                <option value="">All statuses</option>
                {[
                  "PENDING_PAYMENT",
                  "PAID",
                  "FULFILLED",
                  "CANCELED",
                  "PAYMENT_FAILED",
                  "REFUNDED",
                ].map((s) => (
                  <option key={s} value={s}>
                    {label(s)}
                  </option>
                ))}
              </select>
            </div>
            <section className="shell">
              <div className="core order-list">
                {orders.map((order) => (
                  <button
                    className="order-row"
                    key={order.id}
                    onClick={() => void run(() => openOrder(order.id))}
                  >
                    <span>
                      <strong>#{order.id.slice(0, 8)}</strong>
                      <small>{date(order.created_at)}</small>
                    </span>
                    <span className={`badge ${order.status.toLowerCase()}`}>
                      {label(order.status)}
                    </span>
                    <strong>{money(order.total_cents)}</strong>
                    <span>↗</span>
                  </button>
                ))}
                {!orders.length && (
                  <div className="empty">
                    Your next chapter starts with an order.
                  </div>
                )}
              </div>
            </section>
            <div className="pagination">
              <button
                disabled={orderPage === 0 || busy}
                onClick={() => setOrderPage(orderPage - 1)}
              >
                Previous
              </button>
              <span>Page {orderPage + 1}</span>
              <button
                disabled={orders.length < 12 || busy}
                onClick={() => setOrderPage(orderPage + 1)}
              >
                Next
              </button>
            </div>
          </>
        )}
        <footer>
          Thoughtful commerce. Every step accounted for.
          <span>OrderFlow / 01</span>
        </footer>
      </main>
      {editing && (
        <div className="modal-backdrop">
          <section
            className="modal shell"
            role="dialog"
            aria-modal="true"
            aria-labelledby="product-form-title"
          >
            <form className="core detail-panel" onSubmit={saveProduct}>
              <span className="eyebrow">Catalog studio</span>
              <h2 id="product-form-title">
                {editing === "new" ? "Add a product" : "Edit product"}
              </h2>
              <label>
                Product name
                <input
                  name="name"
                  required
                  maxLength={160}
                  defaultValue={edit?.name}
                />
              </label>
              <label>
                SKU
                <input
                  name="sku"
                  required
                  maxLength={64}
                  defaultValue={edit?.sku}
                />
              </label>
              <div className="form-pair">
                <label>
                  Price · USD
                  <input
                    name="price"
                    type="number"
                    min="0"
                    max="1000000"
                    step="0.01"
                    required
                    defaultValue={
                      edit ? (edit.price_cents / 100).toFixed(2) : ""
                    }
                  />
                </label>
                {admin && (
                  <label>
                    Available units
                    <input
                      name="available"
                      type="number"
                      min="0"
                      max="1000000"
                      required
                      defaultValue={edit?.available ?? 0}
                    />
                  </label>
                )}
              </div>
              <label className="checkbox">
                <input
                  name="active"
                  type="checkbox"
                  defaultChecked={edit?.active ?? true}
                />
                Active in catalog
              </label>
              {error && (
                <p role="alert" className="error">
                  {error}
                </p>
              )}
              <div className="actions">
                <button disabled={busy} className="primary">
                  Save product <span className="arrow">↗</span>
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setEditing(null)}
                >
                  Close
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
