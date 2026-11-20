import { useEffect, useState } from "react";
import { api } from "../api";
import { useT } from "../i18n";
import { navigate } from "../App";
import type { AgentFile } from "../types";
import { Badge, Banner, Button, Card, Field, Modal, Spinner, TextArea, TextInput } from "../ui";

const AGENTS = ["researcher", "author", "critic"] as const;

export function AgentEditor({ slug, agentId }: { slug: string; agentId: string }) {
  const { t } = useT();
  const [agent, setAgent] = useState<AgentFile | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [raw, setRaw] = useState(false);
  const [rawText, setRawText] = useState("");
  const [preview, setPreview] = useState<{ system: string; user_sample: string; system_tokens: number; user_tokens: number } | null>(null);
  const [newSection, setNewSection] = useState("");

  const valid = (AGENTS as readonly string[]).includes(agentId);

  useEffect(() => {
    if (!valid) return;
    api
      .agent(slug, agentId)
      .then((data) => {
        setAgent(data);
        setRawText(data.raw);
      })
      .catch((e: Error) => setError(e.message));
  }, [slug, agentId, valid]);

  if (!valid) return <Banner>unknown agent</Banner>;
  if (error) return <Banner>{error}</Banner>;
  if (!agent) {
    return (
      <div className="row">
        <Spinner /> {t("common.loading")}
      </div>
    );
  }

  const meta = agent.meta as { temperature?: number; max_output_tokens?: number; label?: string; model?: string };

  function updateSection(index: number, body: string) {
    if (!agent) return;
    const sections = agent.sections.map((s, i) => (i === index ? { ...s, body } : s));
    const next = { ...agent, sections };
    setAgent(next);
    setRawText(next.raw);
  }

  function updateMeta(patch: Record<string, unknown>) {
    if (!agent) return;
    setAgent({ ...agent, meta: { ...agent.meta, ...patch } });
  }

  async function save() {
    if (!agent) return;
    setSaving(true);
    setError("");
    try {
      const payload = raw
        ? { mode: "raw", raw: rawText }
        : { meta: agent.meta, preamble: agent.preamble, sections: agent.sections };
      const savedAgent = await api.saveAgent(slug, agentId, payload);
      setAgent(savedAgent);
      setRawText(savedAgent.raw);
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function reset() {
    if (!window.confirm(t("agents.resetConfirm"))) return;
    const fresh = await api.resetAgent(slug, agentId);
    setAgent(fresh);
    setRawText(fresh.raw);
  }

  async function showPreview() {
    const data = await api.previewAgent(slug, agentId);
    setPreview(data);
  }

  return (
    <>
      <div className="page-head">
        <div>
          <div className="row" style={{ marginBottom: 6 }}>
            <Button size="sm" variant="ghost" onClick={() => navigate(`/p/${slug}`)}>
              ← {t("nav.back")}
            </Button>
            <Badge>{String(agent.meta.label ?? agent.agent_id)}</Badge>
          </div>
          <h1>{t("agents.title")}</h1>
          <p>{t("agents.subtitle")}</p>
        </div>
        <div className="row">
          {saved ? <Badge tone="good">{t("agents.saved")}</Badge> : null}
          <Button onClick={() => void showPreview()}>{t("agents.preview")}</Button>
          <Button variant="ghost" onClick={() => void reset()}>
            {t("agents.reset")}
          </Button>
          <Button variant="primary" loading={saving} onClick={() => void save()}>
            {t("agents.save")}
          </Button>
        </div>
      </div>

      <div className="row" style={{ marginBottom: 16 }}>
        {AGENTS.map((id) => (
          <Button
            key={id}
            size="sm"
            variant={id === agentId ? "primary" : "subtle"}
            onClick={() => navigate(`/p/${slug}/agents/${id}`)}
          >
            {id}
          </Button>
        ))}
        <span style={{ flex: 1 }} />
        <Button size="sm" variant={raw ? "primary" : "subtle"} onClick={() => setRaw(!raw)}>
          {t("agents.raw")}
        </Button>
      </div>

      <div className="split">
        <Card
          title={raw ? t("agents.raw") : t("agents.fields")}
          actions={<span className="hint">{agent.sections.length} sections</span>}
        >
          {raw ? (
            <TextArea rows={26} value={rawText} onChange={(e) => setRawText(e.target.value)} />
          ) : (
            <>
              <div className="form-grid">
                <Field label={t("agents.temperature")}>
                  <TextInput
                    type="number"
                    step={0.1}
                    min={0}
                    max={1.5}
                    value={meta.temperature ?? 0.2}
                    onChange={(e) => updateMeta({ temperature: Number(e.target.value) })}
                  />
                </Field>
                <Field label={t("agents.maxTokens")}>
                  <TextInput
                    type="number"
                    step={100}
                    min={200}
                    value={meta.max_output_tokens ?? 2000}
                    onChange={(e) => updateMeta({ max_output_tokens: Number(e.target.value) })}
                  />
                </Field>
                <Field label={t("agents.model")} hint={t("common.optional")}>
                  <TextInput
                    placeholder="(default)"
                    value={String(meta.model ?? "")}
                    onChange={(e) => updateMeta({ model: e.target.value || null })}
                  />
                </Field>
              </div>

              {agent.sections.map((section, index) => (
                <div key={`${section.heading}-${index}`} className="agent-section">
                  <div className="agent-section-head">
                    <h4>{section.heading}</h4>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        const sections = agent.sections.filter((_, i) => i !== index);
                        setAgent({ ...agent, sections });
                      }}
                    >
                      {t("common.remove")}
                    </Button>
                  </div>
                  <TextArea rows={Math.min(14, Math.max(4, section.body.split("\n").length + 1))} value={section.body} onChange={(e) => updateSection(index, e.target.value)} />
                </div>
              ))}

              <div className="row" style={{ marginTop: 8 }}>
                <div style={{ flex: 1 }}>
                  <TextInput
                    placeholder={t("agents.sectionName")}
                    value={newSection}
                    onChange={(e) => setNewSection(e.target.value)}
                  />
                </div>
                <Button
                  onClick={() => {
                    if (!newSection.trim()) return;
                    setAgent({ ...agent, sections: [...agent.sections, { heading: newSection.trim(), body: "" }] });
                    setNewSection("");
                  }}
                >
                  {t("agents.custom")}
                </Button>
              </div>

              <div className="contract">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <strong style={{ fontSize: 13 }}>{t("agents.locked")}</strong>
                  <Badge tone="info">{agent.contract_title}</Badge>
                </div>
                <pre>{agent.contract}</pre>
              </div>
            </>
          )}
        </Card>

        <div className="stack">
          <Card title="provenance">
            <table className="table">
              <tbody>
                <tr>
                  <td className="hint">file</td>
                  <td className="mono">agents/{agent.agent_id}.md</td>
                </tr>
                <tr>
                  <td className="hint">version</td>
                  <td className="mono">{String(agent.meta.version ?? 1)}</td>
                </tr>
                <tr>
                  <td className="hint">{t("agents.revisions")}</td>
                  <td className="mono">{agent.revisions?.length ?? 0}</td>
                </tr>
              </tbody>
            </table>
          </Card>
          <Card title={t("agents.tokens")}>
            <p className="hint" style={{ margin: 0 }}>
              {t("agents.warning")}
            </p>
          </Card>
        </div>
      </div>

      <Modal
        open={preview != null}
        title={t("agents.preview")}
        onClose={() => setPreview(null)}
        wide
        footer={<Button onClick={() => setPreview(null)}>{t("common.close")}</Button>}
      >
        {preview ? (
          <div className="stack">
            <div className="stats">
              <div className="stat">
                <span className="stat-label">system</span>
                <span className="stat-value">{preview.system_tokens}</span>
              </div>
              <div className="stat">
                <span className="stat-label">user</span>
                <span className="stat-value">{preview.user_tokens}</span>
              </div>
            </div>
            <div>
              <div className="section-label">system</div>
              <pre className="md-code" style={{ whiteSpace: "pre-wrap" }}>{preview.system}</pre>
            </div>
            <div>
              <div className="section-label">user (sample)</div>
              <pre className="md-code" style={{ whiteSpace: "pre-wrap" }}>{preview.user_sample}</pre>
            </div>
          </div>
        ) : null}
      </Modal>
    </>
  );
}
