import { useEffect, useState } from "react";
import { api } from "../api";
import { useT, setLang, type Lang } from "../i18n";
import type { ProviderPreset, Settings } from "../types";
import { Badge, Banner, Button, Card, Field, Select, TextInput } from "../ui";

export function SettingsScreen() {
  const { t, lang, setLang: changeLang } = useT();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [providers, setProviders] = useState<Record<string, ProviderPreset>>({});
  const [apiKey, setApiKey] = useState("");
  const [openalexKey, setOpenalexKey] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [testing, setTesting] = useState(false);
  const [saved, setSaved] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [modelMsg, setModelMsg] = useState("");
  const [detecting, setDetecting] = useState(false);

  useEffect(() => {
    api
      .settings()
      .then((data) => {
        setSettings(data.settings);
        setProviders(data.providers);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <Banner>{error}</Banner>;
  if (!settings) return <span className="hint">{t("common.loading")}</span>;

  const preset = providers[settings.provider];

  async function save(patch: Record<string, unknown> = {}) {
    const payload: Record<string, unknown> = {
      provider: settings!.provider,
      model: settings!.model,
      base_url: settings!.base_url,
      contact_email: settings!.contact_email,
      temperature: settings!.temperature,
      max_output_tokens: settings!.max_output_tokens,
      timeout_seconds: settings!.timeout_seconds,
      ...patch,
    };
    if (apiKey.trim()) payload.api_key = apiKey.trim();
    if (openalexKey.trim()) payload.openalex_api_key = openalexKey.trim();
    const next = await api.saveSettings(payload);
    setSettings(next);
    setApiKey("");
    setOpenalexKey("");
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  }

  async function test() {
    setTesting(true);
    setStatus("");
    try {
      const result = await api.testProvider();
      setStatus(result.detail);
    } catch (e) {
      setStatus((e as Error).message);
    } finally {
      setTesting(false);
    }
  }

  async function detectModels() {
    setDetecting(true);
    setModelMsg("");
    setModels([]);
    try {
      const result = await api.listModels(settings!.provider);
      setModels(result.models);
      setModelMsg(result.detail);
    } catch (e) {
      setModelMsg((e as Error).message);
    } finally {
      setDetecting(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{t("settings.title")}</h1>
          <p>{t("settings.providerHelp")}</p>
        </div>
        <div className="row">
          {saved ? <Badge tone="good">{t("settings.changesSaved")}</Badge> : null}
          <Button variant="primary" onClick={() => void save()}>
            {t("common.save")}
          </Button>
        </div>
      </div>

      <div className="split">
        <div className="stack">
          <Card title={t("settings.provider")}>
            <Field label={t("settings.provider")}>
              <Select
                value={settings.provider}
                onChange={(e) => {
                  const provider = e.target.value;
                  const chosen = providers[provider];
                  setSettings({
                    ...settings,
                    provider,
                    model: chosen?.default_model ?? settings.model,
                    base_url: chosen?.base_url ?? "",
                  });
                }}
              >
                {Object.entries(providers).map(([id, item]) => (
                  <option key={id} value={id}>
                    {item.label}
                  </option>
                ))}
              </Select>
            </Field>

            <Field label={t("settings.model")}>
              <TextInput
                value={settings.model}
                onChange={(e) => setSettings({ ...settings, model: e.target.value })}
                placeholder={preset?.default_model}
              />
            </Field>
            <div className="row" style={{ marginTop: -6, marginBottom: 14 }}>
              <Button size="sm" onClick={() => void detectModels()} loading={detecting}>
                {detecting ? t("settings.detecting") : t("settings.detect")}
              </Button>
              {modelMsg ? <span className="hint">{modelMsg}</span> : null}
            </div>
            {models.length > 0 ? (
              <div className="row" style={{ marginTop: -8, marginBottom: 14 }}>
                <span className="hint">{t("settings.modelsFound")}:</span>
                {models.slice(0, 8).map((name) => (
                  <Badge
                    key={name}
                    tone={settings.model === name ? "good" : "neutral"}
                    title={name}
                  >
                    <button
                      className="linklike"
                      onClick={() => setSettings({ ...settings, model: name })}
                    >
                      {name}
                    </button>
                  </Badge>
                ))}
              </div>
            ) : null}

            <Field label={t("settings.baseUrl")} hint="blank = provider default">
              <TextInput
                value={settings.base_url}
                onChange={(e) => setSettings({ ...settings, base_url: e.target.value })}
                placeholder={preset?.base_url}
              />
            </Field>

            <div className="form-grid">
              <Field label={t("settings.timeout")} hint={t("settings.timeoutHelp")}>
                <TextInput
                  type="number"
                  min={30}
                  step={30}
                  value={settings.timeout_seconds}
                  onChange={(e) =>
                    setSettings({ ...settings, timeout_seconds: Number(e.target.value) || 180 })
                  }
                />
              </Field>
              <Field label={t("agents.temperature")}>
                <TextInput
                  type="number"
                  min={0}
                  max={1.5}
                  step={0.1}
                  value={settings.temperature}
                  onChange={(e) =>
                    setSettings({ ...settings, temperature: Number(e.target.value) || 0.2 })
                  }
                />
              </Field>
              <Field label={t("agents.maxTokens")}>
                <TextInput
                  type="number"
                  min={256}
                  step={256}
                  value={settings.max_output_tokens}
                  onChange={(e) =>
                    setSettings({ ...settings, max_output_tokens: Number(e.target.value) || 2000 })
                  }
                />
              </Field>
            </div>

            {settings.provider === "ollama" ? (
              <Banner tone="info">{t("settings.ollamaHint")}</Banner>
            ) : null}

            {settings.provider !== "mock" && settings.provider !== "ollama" ? (
              <Field
                label={t("settings.apiKey")}
                hint={
                  settings.has_api_key
                    ? t("settings.keyStored").replace("{backend}", settings.secret_backend)
                    : t("settings.keyMissing")
                }
              >
                <TextInput
                  type="password"
                  value={apiKey}
                  placeholder={settings.has_api_key ? "••••••••" : "sk-…"}
                  onChange={(e) => setApiKey(e.target.value)}
                />
              </Field>
            ) : null}

            <div className="row">
              <Button onClick={() => void test()} loading={testing}>
                {testing ? t("settings.testing") : t("settings.test")}
              </Button>
              {status ? <span className="hint">{status}</span> : null}
            </div>
          </Card>

          <Card title={t("settings.openalex")}>
            <p className="hint" style={{ marginTop: 0 }}>
              {t("settings.openalexHelp")}
            </p>
            <Field label={t("settings.openalex")}>
              <TextInput
                value={openalexKey}
                placeholder={settings.openalex_key_set ? "••••••••" : "optional"}
                onChange={(e) => setOpenalexKey(e.target.value)}
              />
            </Field>
            <Field label={t("settings.contact")} hint="polite pool for Crossref/OpenAlex">
              <TextInput
                value={settings.contact_email}
                placeholder="you@university.edu"
                onChange={(e) => setSettings({ ...settings, contact_email: e.target.value })}
              />
            </Field>
          </Card>
        </div>

        <div className="stack">
          <Card title={t("settings.workspace")}>
            <p className="hint" style={{ marginTop: 0 }}>
              {t("settings.workspaceHelp")}
            </p>
            <div className="mono" style={{ wordBreak: "break-all" }}>
              {settings.workspace}
            </div>
            <div className="row" style={{ marginTop: 12 }}>
              <Badge tone="info">{settings.secret_backend}</Badge>
              <Badge tone={settings.has_api_key ? "good" : "neutral"}>
                {settings.has_api_key ? "key set" : "no key"}
              </Badge>
            </div>
          </Card>

          <Card title={t("settings.language")}>
            <Select
              value={lang}
              onChange={(e) => {
                changeLang(e.target.value as Lang);
                setLang(e.target.value as Lang);
              }}
            >
              <option value="pt-BR">Português (Brasil)</option>
              <option value="en">English</option>
            </Select>
            <p className="hint" style={{ marginBottom: 0 }}>
              {t("settings.security")}
            </p>
          </Card>
        </div>
      </div>
    </>
  );
}
