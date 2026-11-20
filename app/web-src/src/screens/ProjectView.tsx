import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useT } from "../i18n";
import { navigate } from "../App";
import type { Diagnosis, ProjectDetail, Report, RunState } from "../types";
import { Badge, Banner, Button, Card, EmptyState, Field, Spinner, Stat, Tabs, TextInput } from "../ui";
import { BriefForm } from "../components/BriefForm";
import { Markdown } from "../md";
import { RunPanel } from "./RunPanel";

const TABS = ["overview", "brief", "sources", "run", "document", "review", "agents"] as const;
type Tab = (typeof TABS)[number];

function downloadText(filename: string, text: string, type = "text/markdown") {
  const blob = new Blob([text], { type: `${type};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function ProjectView({ slug, initialTab }: { slug: string; initialTab?: string }) {
  const { t } = useT();
  const [detail, setDetail] = useState<ProjectDetail | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>((TABS as readonly string[]).includes(initialTab ?? "") ? (initialTab as Tab) : "overview");
  const [document, setDocument] = useState<{ name: string; text: string } | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [draftBrief, setDraftBrief] = useState<ProjectDetail["brief"] | null>(null);
  const [saved, setSaved] = useState(false);

  const load = useCallback(() => {
    api
      .project(slug)
      .then((data) => {
        setDetail(data);
        setDraftBrief(data.brief);
      })
      .catch((e: Error) => setError(e.message));
  }, [slug]);

  useEffect(load, [load]);

  const latestRun: RunState | null = detail?.runs?.[0] ?? null;

  useEffect(() => {
    if (!latestRun) return;
    if (tab !== "document") return;
    let cancelled = false;
    (async () => {
      for (const name of ["outputs/document-final.md", "outputs/document-v1.md"]) {
        try {
          const text = await api.artifact(slug, latestRun.run_id, name);
          if (!cancelled) setDocument({ name, text });
          return;
        } catch {
          /* try the next artifact */
        }
      }
      if (!cancelled) setDocument(null);
    })();
    return () => {
      cancelled = true;
    };
  }, [slug, tab, latestRun?.run_id]);

  useEffect(() => {
    if (!latestRun || tab !== "review") return;
    let cancelled = false;
    api
      .report(slug, latestRun.run_id)
      .then((data) => {
        if (!cancelled) setReport(data);
      })
      .catch(() => {
        if (!cancelled) setReport(null);
      });
    return () => {
      cancelled = true;
    };
  }, [slug, tab, latestRun?.run_id]);

  if (error) return <Banner>{error}</Banner>;
  if (!detail || !draftBrief) {
    return (
      <div className="row">
        <Spinner /> {t("common.loading")}
      </div>
    );
  }

  const papers = detail.papers;
  const words = document ? document.text.split(/\s+/).filter(Boolean).length : 0;
  const citations = document ? (document.text.match(/\[P-\d{4}/g) ?? []).length : 0;

  async function saveBrief() {
    if (!draftBrief) return;
    await api.updateBrief(slug, draftBrief);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
    load();
  }

  return (
    <>
      <div className="page-head">
        <div>
          <div className="row" style={{ marginBottom: 6 }}>
            <Badge>{detail.meta.slug}</Badge>
            <span className="hint">
              {t("proj.created")} {detail.meta.created_at.slice(0, 10)}
            </span>
          </div>
          <h1>{detail.meta.title}</h1>
          <p>{detail.brief.topic}</p>
        </div>
        <div className="row">
          <Button onClick={() => (window.location.href = `/api/projects/${slug}/export.zip`)}>
            {t("proj.export")}
          </Button>
          <Button onClick={() => (window.location.href = `/api/projects/${slug}/bibliography.bib`)}>
            {t("proj.bib")}
          </Button>
          <Button variant="primary" onClick={() => setTab("run")}>
            {t("proj.run")}
          </Button>
        </div>
      </div>

      <Tabs
        value={tab}
        onChange={(id) => setTab(id as Tab)}
        items={TABS.map((id) => ({
          id,
          label: t(`proj.tabs.${id}` as never),
          badge:
            id === "sources"
              ? papers.length
              : id === "run" && latestRun
                ? latestRun.status
                : undefined,
        }))}
      />

      {tab === "overview" && (
        <div className="stack">
          <div className="stats">
            <Stat label={t("proj.papers")} value={papers.length} />
            <Stat label={t("proj.evidence")} value={detail.evidence_count} />
            <Stat
              label={t("projects.lastRun")}
              value={latestRun ? t(`run.status.${latestRun.status}` as never) : "—"}
              hint={latestRun ? `US$ ${latestRun.cost_usd.toFixed(3)}` : undefined}
            />
            <Stat label={t("f.minSources")} value={detail.brief.min_sources} />
          </div>

          <Card title={t("proj.nextStep")}>
            <p style={{ margin: 0 }}>
              {detail.runs.some((r) => r.status === "waiting")
                ? t("proj.next.checkpoint")
                : papers.length === 0
                  ? t("proj.next.run")
                  : latestRun?.status === "done"
                    ? t("proj.next.document")
                    : t("proj.next.brief")}
            </p>
            <div className="row" style={{ marginTop: 14 }}>
              <Button variant="primary" onClick={() => setTab("run")}>
                {t("proj.run")}
              </Button>
              <Button onClick={() => setTab("sources")}>{t("proj.tabs.sources")}</Button>
              <Button variant="ghost" onClick={() => setTab("brief")}>
                {t("proj.brief")}
              </Button>
            </div>
          </Card>

          <div className="split">
            <Card title="brief.md">
              <Markdown text={detail.brief_md} />
            </Card>
            <Card title="workplan.md">
              <Markdown text={detail.workplan_md} />
            </Card>
          </div>
        </div>
      )}

      {tab === "brief" && (
        <Card
          title={t("proj.brief")}
          actions={
            <div className="row-tight">
              {saved ? <Badge tone="good">{t("common.saved")}</Badge> : null}
              <Button size="sm" variant="primary" onClick={() => void saveBrief()}>
                {t("proj.saveBrief")}
              </Button>
            </div>
          }
        >
          <BriefForm brief={draftBrief} onChange={setDraftBrief} section="all" />
        </Card>
      )}

      {tab === "sources" && <SourcesTab slug={slug} detail={detail} onChanged={load} />}

      {tab === "run" && <RunPanel slug={slug} runs={detail.runs} onRefresh={load} />}

      {tab === "document" && (
        <Card
          title={t("doc.title")}
          actions={
            document ? (
              <div className="row-tight">
                <span className="hint">
                  {words} {t("doc.wordCount")} · {citations} {t("doc.citations")}
                </span>
                <Button size="sm" onClick={() => downloadText(`${slug}.md`, document.text)}>
                  {t("doc.download")}
                </Button>
              </div>
            ) : null
          }
        >
          {document ? (
            <div className="doc">
              <Markdown text={document.text} />
            </div>
          ) : (
            <EmptyState title={t("doc.empty")} />
          )}
        </Card>
      )}

      {tab === "review" && (
        <ReviewTab report={report} />
      )}

      {tab === "agents" && (
        <div className="stack">
          <p className="hint" style={{ margin: 0 }}>
            {t("agents.subtitle")}
          </p>
          <div className="grid-2">
            {(["researcher", "author", "critic"] as const).map((agent) => (
              <Card key={agent} title={agent} actions={<Button size="sm" onClick={() => navigate(`/p/${slug}/agents/${agent}`)}>{t("common.overview")}</Button>}>
                <p className="hint" style={{ margin: 0 }}>
                  {agent === "researcher" && t("agents.subtitle")}
                  {agent === "author" && t("agents.warning")}
                  {agent === "critic" && t("agents.locked")}
                </p>
              </Card>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function SourcesTab({
  slug,
  detail,
  onChanged,
}: {
  slug: string;
  detail: ProjectDetail;
  onChanged: () => void;
}) {
  const { t } = useT();
  const [doi, setDoi] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [diag, setDiag] = useState<Diagnosis | null>(null);
  const [diagLoading, setDiagLoading] = useState(false);

  async function add() {
    setAdding(true);
    setError("");
    try {
      await api.addSource(slug, { doi: doi.trim(), title: title.trim() });
      setDoi("");
      setTitle("");
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAdding(false);
    }
  }

  async function runDiagnose() {
    setDiagLoading(true);
    setError("");
    try {
      setDiag(await api.diagnose(slug));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDiagLoading(false);
    }
  }

  return (
    <div className="stack">
      {error ? <Banner>{error}</Banner> : null}

      <Card
        title={t("sources.test")}
        actions={<span className="hint">{t("sources.testHint")}</span>}
      >
        <div className="row">
          <Button loading={diagLoading} onClick={() => void runDiagnose()}>
            {diagLoading ? t("sources.testing") : t("sources.test")}
          </Button>
          {diag ? (
            <Badge tone={diag.hits > 0 ? "good" : "bad"}>
              {diag.hits > 0 ? t("sources.testOk") : t("sources.testFail")} · {diag.hits}
            </Badge>
          ) : null}
          {diag ? <span className="hint">{diag.filters}</span> : null}
        </div>

        {diag ? (
          <div style={{ marginTop: 14 }}>
            {diag.explanation ? (
              <pre className="md-code" style={{ whiteSpace: "pre-wrap", marginBottom: 12 }}>
                {diag.explanation}
              </pre>
            ) : null}

            <table className="table">
              <thead>
                <tr>
                  <th>source</th>
                  <th>calls</th>
                  <th>hits</th>
                  <th>HTTP</th>
                  <th>time</th>
                  <th>errors</th>
                </tr>
              </thead>
              <tbody>
                {diag.sources.map((source) => (
                  <tr key={source.name}>
                    <td>{source.name}</td>
                    <td className="mono">{source.calls}</td>
                    <td className="mono">{source.hits}</td>
                    <td className="mono">{source.status ?? "—"}</td>
                    <td className="mono">{source.seconds.toFixed(1)}s</td>
                    <td className="hint">{source.errors.join(", ") || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {diag.examples.length > 0 ? (
              <>
                <div className="section-label">{t("sources.testExamples")}</div>
                <ul className="md-list">
                  {diag.examples.slice(0, 6).map((example, index) => (
                    <li key={index}>
                      {example.title}{" "}
                      <span className="hint">
                        {[example.year, example.venue, example.doi].filter(Boolean).join(" · ")}
                      </span>
                    </li>
                  ))}
                </ul>
              </>
            ) : null}

            <div className="section-label">{t("sources.testQueries")}</div>
            <div className="hint">
              {diag.queries.map((query) => query.query).join(" | ")}
            </div>

            {diag.warnings.length > 0 ? (
              <>
                <div className="section-label">{t("sources.testDetail")}</div>
                <ul className="md-list">
                  {diag.warnings.map((warning, index) => (
                    <li key={index}>{warning}</li>
                  ))}
                </ul>
              </>
            ) : null}
          </div>
        ) : null}
      </Card>

      <Card title={t("sources.add")}>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <div style={{ flex: 1, minWidth: 240 }}>
            <Field label={t("sources.doi")}>
              <TextInput value={doi} placeholder="10.1016/j.uclim.2020.100600" onChange={(e) => setDoi(e.target.value)} />
            </Field>
          </div>
          <div style={{ flex: 1, minWidth: 200 }}>
            <Field label={t("sources.titleField")}>
              <TextInput value={title} placeholder="Título do artigo" onChange={(e) => setTitle(e.target.value)} />
            </Field>
          </div>
          <div style={{ marginBottom: 14 }}>
            <Button variant="primary" loading={adding} onClick={() => void add()} disabled={!doi.trim() && !title.trim()}>
              {t("common.add")}
            </Button>
          </div>
        </div>
      </Card>

      <Card title={t("sources.title")} actions={<span className="hint">{t("sources.subtitle")}</span>}>
        {detail.papers.length === 0 ? (
          <EmptyState title={t("sources.empty")} />
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>{t("sources.id")}</th>
                <th>{t("sources.title")}</th>
                <th>{t("sources.year")}</th>
                <th>{t("sources.venue")}</th>
                <th>{t("sources.type")}</th>
                <th>{t("sources.status")}</th>
                <th>{t("sources.evidence")}</th>
              </tr>
            </thead>
            <tbody>
              {detail.papers.map((paper) => (
                <tr key={paper.id} onClick={() => setExpanded(expanded === paper.id ? null : paper.id)} style={{ cursor: "pointer" }}>
                  <td className="mono">{paper.id}</td>
                  <td>
                    <div>{paper.title}</div>
                    {expanded === paper.id ? (
                      <div className="hint" style={{ marginTop: 6 }}>
                        {paper.abstract || "—"}
                        {paper.verification_note ? <div style={{ marginTop: 6 }}>{paper.verification_note}</div> : null}
                      </div>
                    ) : null}
                  </td>
                  <td>{paper.year ?? "—"}</td>
                  <td>{paper.venue || "—"}</td>
                  <td>
                    <Badge tone={paper.source_type === "peer_reviewed" ? "good" : "warn"}>
                      {paper.source_type}
                    </Badge>
                  </td>
                  <td>
                    <div className="row-tight">
                      <Badge tone={paper.verified === "yes" ? "good" : paper.verified === "mismatch" ? "bad" : "neutral"}>
                        {paper.verified}
                      </Badge>
                      {paper.full_text === "oa" ? <Badge tone="info">OA</Badge> : null}
                      {paper.full_text === "paywalled" ? <Badge tone="warn">{t("sources.paywalled")}</Badge> : null}
                      {paper.full_text === "abstract_only" ? <Badge>{t("sources.abstractOnly")}</Badge> : null}
                    </div>
                  </td>
                  <td className="mono">{paper.evidence_count ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}

function ReviewTab({ report }: { report: Report | null }) {
  const { t } = useT();
  if (!report) return <EmptyState title={t("review.empty")} />;
  const ledger = report.ledger;

  return (
    <div className="stack">
      <div className="stats">
        <Stat
          label={t("review.verdict")}
          value={
            <Badge tone={ledger.verdict === "pass" ? "good" : ledger.verdict === "fail" ? "bad" : "warn"}>
              {t(`review.${ledger.verdict}` as never)}
            </Badge>
          }
        />
        <Stat label={t("review.citations")} value={`${ledger.citations_resolved}/${ledger.citations_total}`} />
        <Stat label={t("review.uncited")} value={ledger.paragraphs_without_citation.length} />
        <Stat label={t("review.sourceMix")} value={`${ledger.sources_peer_reviewed}/${ledger.sources_total}`} hint={`DOI: ${ledger.sources_doi_verified}`} />
      </div>

      {ledger.missing.length > 0 ? (
        <Banner>
          {t("review.missing")}: {ledger.missing.join(", ")}
        </Banner>
      ) : null}
      {ledger.sections_missing.length > 0 ? (
        <Banner tone="warn">
          {t("review.sectionsMissing")}: {ledger.sections_missing.join(", ")}
        </Banner>
      ) : null}
      {ledger.quote_mismatches.length > 0 ? (
        <Banner>
          {t("review.quotes")}: {ledger.quote_mismatches.slice(0, 4).join(" · ")}
        </Banner>
      ) : null}
      {ledger.page_mismatches.length > 0 ? (
        <Banner>{ledger.page_mismatches.slice(0, 4).join(" · ")}</Banner>
      ) : null}

      <Card title={t("review.findings")}>
        {report.findings.length === 0 ? (
          <p className="hint">{t("review.noFindings")}</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>{t("review.target")}</th>
                <th>local</th>
                <th>issue</th>
                <th>fix</th>
              </tr>
            </thead>
            <tbody>
              {report.findings.map((finding, index) => (
                <tr key={index}>
                  <td>
                    <Badge
                      tone={
                        finding.severity === "blocker"
                          ? "bad"
                          : finding.severity === "major"
                            ? "warn"
                            : finding.severity === "minor"
                              ? "neutral"
                              : "info"
                      }
                    >
                      {t(`review.${finding.severity}` as never)}
                    </Badge>
                    <div className="hint" style={{ marginTop: 4 }}>→ {finding.target}</div>
                  </td>
                  <td className="hint">{finding.location}</td>
                  <td>{finding.issue}</td>
                  <td className="hint">{finding.suggestion}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card title={t("review.validation")} actions={<span className="hint">{report.provider} · {report.model} · US$ {report.cost_usd.toFixed(4)}</span>}>
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>DOI</th>
              <th>{t("sources.status")}</th>
              <th>note</th>
            </tr>
          </thead>
          <tbody>
            {report.validation.map((row) => (
              <tr key={row.id}>
                <td className="mono">{row.id}</td>
                <td className="mono">{row.doi || "—"}</td>
                <td>
                  <Badge tone={row.status === "yes" ? "good" : row.status === "mismatch" ? "bad" : "neutral"}>
                    {row.status}
                  </Badge>
                </td>
                <td className="hint">{row.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {report.warnings.length > 0 ? (
        <Card title="warnings">
          <ul className="md-list">
            {report.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
