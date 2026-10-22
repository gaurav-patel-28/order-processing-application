import { expect, test, Page } from "@playwright/test";

async function login(page: Page, user: string) {
  await page.goto("/");
  await page
    .getByLabel("Email", { exact: true })
    .fill(`${user}@orderflow.test`);
  await page.getByLabel("Password", { exact: true }).fill("Orderflow123!");
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await expect(
    page.getByRole("navigation", { name: "Main navigation" }),
  ).toBeVisible();
}

test("merchant creates product, customer pays, merchant fulfills and refunds", async ({
  page,
}) => {
  const name = `Journey journal ${Date.now()}`;
  await login(page, "admin.a");
  await page.getByRole("button", { name: "Add product" }).click();
  await page.getByLabel("Product name").fill(name);
  await page.getByLabel("SKU", { exact: true }).fill(`J-${Date.now()}`);
  await page.getByLabel("Price · USD").fill("19.99");
  await page.getByLabel("Available units", { exact: true }).fill("3");
  await page.getByRole("button", { name: "Save product" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await login(page, "customer.a");
  await page.getByLabel("Search products").fill(name);
  await page.getByLabel(`Quantity for ${name}`).fill("1");
  await page.getByRole("button", { name: "Create order" }).click();
  await expect(
    page.getByText("pending payment", { exact: true }).first(),
  ).toBeVisible();
  const reference = await page.locator(".order-reference").innerText();
  await page
    .getByRole("button", { name: "Simulate successful payment" })
    .click();
  await expect(page.locator(".status")).toHaveText("paid");
  await expect(
    page.getByRole("button", { name: "Fulfill order" }),
  ).not.toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await login(page, "staff.a");
  await page.getByRole("button", { name: "Orders", exact: true }).click();
  await page
    .getByRole("button")
    .filter({ hasText: `#${reference.slice(0, 8)}` })
    .click();
  await page.getByRole("button", { name: "Fulfill order" }).click();
  await expect(page.locator(".status")).toHaveText("fulfilled");
  await page
    .getByRole("button", { name: "Issue full simulated refund" })
    .click();
  await expect(page.locator(".status")).toHaveText("refunded");
});

test("failed payment informs customer and releases stock", async ({ page }) => {
  await login(page, "customer.a");
  await page
    .getByLabel("Quantity for Field notebook", { exact: true })
    .fill("1");
  await page.getByRole("button", { name: "Create order" }).click();
  await page.getByRole("button", { name: "Simulate failed payment" }).click();
  await expect(page.locator(".status")).toHaveText("payment failed");
  await expect(
    page.getByText("Payment failed. Reserved stock has been released."),
  ).toBeVisible();
  await page.getByRole("button", { name: "All orders" }).click();
  await expect(page.locator(".order-row").first()).toContainText(
    "payment failed",
  );
});

test("another customer cannot see or request someone else’s order", async ({
  page,
}) => {
  await login(page, "customer.a");
  await page
    .getByLabel("Quantity for Field notebook", { exact: true })
    .fill("1");
  await page.getByRole("button", { name: "Create order" }).click();
  const orderId = await page.locator(".order-reference").innerText();
  await page.getByRole("button", { name: "Cancel order" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await login(page, "customer2.a");
  await page.getByRole("button", { name: "Orders", exact: true }).click();
  await expect(page.getByText(`#${orderId.slice(0, 8)}`)).not.toBeVisible();
  // A fresh credential for this second user also cannot bypass the UI boundary.
  const auth = await page.request.post("/api/auth/login", {
    data: { email: "customer2.a@orderflow.test", password: "Orderflow123!" },
  });
  const token = (await auth.json()).access_token;
  const response = await page.request.get(`/api/orders/${orderId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.status()).toBe(404);
});
