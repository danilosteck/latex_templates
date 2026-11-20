/**
 * Browser smoke test for the built UI against a local server on :8799.
 * Creates a project through the real wizard, adds a source, opens the agent
 * editor and the compiled-prompt preview. Fails on any console error.
 */
import { chromium } from "playwright";

const BASE = "http://127.0.0.1:8799";
const errors = [];
const step = (n, msg) => console.log(`${n}. ${msg}`);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 950 } });
page.on("console", (msg) => {
  if (msg.type() === "error") errors.push(`console: ${msg.text()}`);
});
page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));

await page.goto(BASE, { waitUntil: "networkidle" });
await page.waitForSelector("h1:has-text('Projetos')", { timeout: 10000 });
step(1, "projects screen rendered");

await page.getByRole("button", { name: "Novo projeto" }).first().click();
await page.waitForSelector("h1:has-text('Novo projeto')", { timeout: 5000 });
step(2, "wizard opened");

await page.getByPlaceholder(/Telhados verdes/).fill("UI smoke: telhados verdes");
await page
  .getByPlaceholder(/O efeito de telhados verdes/)
  .fill("O efeito de telhados verdes na reducao de ilhas de calor urbanas.");
await page.getByRole("button", { name: "Continuar" }).click();

await page.getByPlaceholder(/Telhados verdes reduzem/).fill("Telhados verdes reduzem a temperatura?");
await page.getByRole("button", { name: "Continuar" }).click();
step(3, "object and question filled");

await page.getByPlaceholder("green infrastructure").fill("telhados verdes");
await page.getByPlaceholder(/green roof, urban heat island/).fill("green roof, urban heat island");
await page.getByRole("button", { name: "Continuar" }).click();

await page.getByRole("button", { name: "Continuar" }).click(); // viewpoints (optional)
await page.getByRole("button", { name: "Continuar" }).click(); // deliverable
await page.waitForSelector("text=Revisão", { timeout: 5000 });
step(4, "review step reached");

await page.getByRole("button", { name: "Criar projeto" }).click();
await page.waitForSelector("h1:has-text('UI smoke')", { timeout: 20000 });
const slug = page.url().split("/p/")[1].split("?")[0];
step(5, `project created: ${slug}`);

await page.getByRole("tab", { name: /Fontes/ }).click();
await page.waitForSelector("text=Adicionar fonte manualmente", { timeout: 5000 });
await page.getByPlaceholder(/10.1016/).fill("10.1000/ui-smoke");
await page.getByPlaceholder("Título do artigo").fill("Manual smoke source");
await page.getByRole("button", { name: "Adicionar", exact: true }).click();
await page.waitForSelector("td.mono:has-text('P-0001')", { timeout: 20000 });
step(6, "manual source registered");

// diagnostics: the button must explain a search instead of just failing
await page.getByRole("button", { name: "Testar fontes" }).first().click();
const diagCard = page.locator(".card", { hasText: "Testar fontes" }).first();
await diagCard.locator("tbody tr").first().waitFor({ timeout: 60000 });
const diagRows = await diagCard.locator("tbody tr").count();
const firstSource = await diagCard.locator("tbody tr td").first().innerText();
if (diagRows < 2) errors.push(`diagnostics table has only ${diagRows} rows`);
step(7, `source diagnostics rendered (${diagRows} rows, first=${firstSource})`);

// settings: local provider + model discovery must respond with a human message
await page.goto(`${BASE}/#/settings`, { waitUntil: "networkidle" });
await page.locator(".card select.input").first().selectOption("ollama");
await page.getByRole("button", { name: "Detectar modelos" }).click();
await page.waitForSelector("text=/não respondeu|não está rodando|modelo\\(s\\) local/i", {
  timeout: 20000,
});
step(8, "ollama model discovery answered with a human message");

await page.goto(`${BASE}/#/p/${slug}/agents/author`, { waitUntil: "networkidle" });
await page.waitForSelector("text=Garantido pelo aplicativo", { timeout: 10000 });
const fields = await page.locator("textarea").count();
step(9, `agent editor rendered (${fields} section fields)`);

await page.getByRole("button", { name: "Ver prompt compilado" }).click();
await page.waitForSelector("text=Engine contract", { timeout: 5000 });
step(10, "compiled prompt shows the locked contract");
await page.getByRole("button", { name: "Fechar" }).click();

await page.screenshot({ path: "/home/danilo/.hermes/cache/scratch/ui-agent.png" });

await page.goto(`${BASE}/#/p/${slug}`, { waitUntil: "networkidle" });
await page.waitForSelector("text=Próximo passo", { timeout: 10000 });
const stats = await page.locator(".stat").count();
step(11, `project overview rendered (${stats} stat cards)`);
await page.screenshot({ path: "/home/danilo/.hermes/cache/scratch/ui-project.png" });

await browser.close();

if (errors.length) {
  console.log("\nERRORS:\n" + errors.join("\n"));
  process.exit(1);
}
console.log("\nUI smoke OK — no console errors");
