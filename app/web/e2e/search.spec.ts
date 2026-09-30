import { expect, hit, test } from "./fixtures"

test.beforeEach(async ({ page, api }) => {
  void api
  await page.goto("/")
  await expect(page.getByTestId("stat-image")).toHaveText("120")
})

test("search shows understood tokens and ranked results", async ({ page, api }) => {
  api.understood = { search_text: "struk bensin", date: "7 hari terakhir", channel: "whatsapp", type_hint: "image" }
  api.results = [
    hit({ file_id: "receipts/bensin.png", name: "struk_bensin.png", match: "ocr", snippet: "SPBU struk bensin PERTAMAX" }),
    hit({ file_id: "docs/inv.pdf", name: "invoice.pdf", mime_group: "document", match: "text", page: 2, confidence: "good" }),
    hit({ file_id: "photos/x.jpg", name: "x.jpg", confidence: "weak" }),
  ]
  await page.getByTestId("search-input").fill("foto struk bensin via wa minggu lalu")
  await page.getByTestId("search-button").click()

  await expect(page.getByTestId("u-date")).toContainText("7 hari terakhir")
  await expect(page.getByTestId("u-channel")).toContainText("WhatsApp")
  await expect(page.getByTestId("result-card")).toHaveCount(2)
  await expect(page.getByTestId("result-name").first()).toHaveText("struk_bensin.png")
  await expect(page.getByTestId("status")).toContainText("2 hasil cocok, 1 kemungkinan lain")
  await expect(page.locator("mark").first()).toHaveText(/struk|bensin/i)

  await page.getByText(/Hasil lain yang mungkin relevan/).click()
  await expect(page.getByTestId("result-card")).toHaveCount(3)
})

test("low confidence is shown honestly", async ({ page, api }) => {
  api.results = [hit({ confidence: "weak" })]
  await page.getByTestId("search-input").fill("zzqx unicorn")
  await page.keyboard.press("Enter")
  await expect(page.getByTestId("empty")).toContainText("Belum ada yang benar-benar cocok")
  await expect(page.getByTestId("result-card")).toHaveCount(1)
})

test("filters re-run the search with the right params", async ({ page, api }) => {
  await page.getByTestId("example-chip").first().click()
  await expect(page.getByTestId("result-card")).toHaveCount(1)
  await page.getByTestId("type-document").click()
  await expect.poll(() => api.searches.at(-1)?.body.type).toBe("document")
  await page.getByTestId("channel-select").click()
  await page.getByRole("option", { name: "Email" }).click()
  await expect.poll(() => api.searches.at(-1)?.body.channel).toBe("email")
})

test("switching tenant scopes every request", async ({ page, api }) => {
  await page.getByTestId("company-select").click()
  await page.getByRole("option", { name: "PT Lain Sejahtera" }).click()
  await expect(page.getByTestId("stat-image")).toHaveText("0")
  await page.getByTestId("search-input").fill("sepatu")
  await page.keyboard.press("Enter")
  await expect(page.getByTestId("empty")).toBeVisible()
  expect(api.searches.at(-1)?.tenant).toBe("tenant_other")
})

test("preview and delete", async ({ page, api }) => {
  await page.getByTestId("search-input").fill("anjing")
  await page.keyboard.press("Enter")
  await page.getByTestId("result-card").first().click()
  const dialog = page.getByTestId("preview")
  await expect(dialog.getByRole("img", { name: "dog.jpg" })).toBeVisible()
  await dialog.getByTestId("preview-delete").click()
  await dialog.getByTestId("preview-delete-confirm").click()
  await expect(dialog).toBeHidden()
  expect(api.deleted).toEqual(["photos/dog.jpg"])
  await expect(page.getByTestId("empty")).toBeVisible()
})

test("upload reports each file", async ({ page, api }) => {
  api.uploadStatus = { status: "duplicate", duplicate_of: "docs/Notulen.pdf" }
  await page.getByTestId("file-input").setInputFiles({ name: "notulen.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4") })
  await expect(page.getByTestId("upload-list")).toContainText("Sudah ada sebagai Notulen.pdf")
})

test("no horizontal scroll and '/' focuses search", async ({ page }) => {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow).toBeLessThanOrEqual(0)
  await page.getByRole("heading", { level: 1 }).click()
  await page.keyboard.press("/")
  await expect(page.getByTestId("search-input")).toBeFocused()
})
