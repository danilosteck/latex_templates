import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useT } from "../i18n";
import type { RunEvent, RunState } from "../types";
import { Badge, Banner, Button, Card, EmptyState, Spinner } from "../ui";

const PHASES = ["plan", "discover", "ingest", "outline", "draft", "critique", "freeze"];

const PHASE_LABEL: Record<string, string> = {
  plan: "plan",
  discover: "discover",
  ingest: "ingest",
  outline: "outline",
  draft: "draft",
  critique: "critique",
  freeze: "freeze",
  queued: "queued",
  ingested: "ingest",
};

function statusTone(status: RunState["status"]) {
  switch (status) {
    case "done":
      return "good" as const;
    case "failed":
      return "bad" as const;
    case "waiting":
      return "warn" as const;
    case "cancelled":
      return "neutral" as const;
    default:
      return "info" as const;
  }
}

interface CandidateRow {
  key: string;
  title: string;
  year: number | null;
  venue: string;
  doi: string | null;
  score: number;
  oa: boolean;
  theme: string;
}

export function RunPanel({ slug, runs, onRefresh }: { slug: string; runs: RunState[]; onRefresh: () => void }) {
  const { t } = useT();
  const [run, setRun] = useState<RunState | null>(runs[0] ?? null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [error, setError] = useState("");
  const [starting, setStarting] = useState(false);
  const offset = useRef(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [sections, setSections] = useState<Set<string>>(new Set());

  const isLive = run != null && (run.status === "running" || run.status === "waiting");

  const poll = useCallback(async () => {
    if (!run) return;
    try {
      const response = await api.runEvents(slug, run.run_id, offset.current);
      offset.current = response.offset;
      if (response.events.length) {
        setEvents((prev) => [...prev, ...response.events].slice(-500));
      }
      if (response.state) setRun(response.state);
    } catch {
      /* transient */
    }
  }, [slug, run?.run_id]);

  useEffect(() => {
    if (!isLive) return;
    const id = window.setInterval(() => void poll(), 900);
    void poll();
    return () => window.clearInterval(id);
  }, [isLive, poll]);

  // reset the log when switching runs
  useEffect(() => {
    offset.current = 0;
    setEvents([]);
    setSelected(new Set());
    setSections(new Set());
  }, [run?.run_id]);

  // default-select everything offered at a checkpoint
  useEffect(() => {
    if (!run?.checkpoint) return;
    const data = run.checkpoint.data as Record<string, unknown>;
    if (run.checkpoint.kind === "candidates" && Array.isArray(data.candidates)) {
      setSelected(new Set((data.candidates as CandidateRow[]).map((c) => c.key)));
    }
    if (run.checkpoint.kind === "outline" && Array.isArray(data.sections)) {
      setSections(new Set((data.sections as { heading: string }[]).map((s) => s.heading)));
    }
  }, [run?.checkpoint]);

  async function start() {
    setStarting(true);
    setError("");
    try {
      const state = await api.startRun(slug);
      setRun(state);
      offset.current = 0;
      setEvents([]);
      onRefresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  }

  async function decide(payload: Record<string, unknown>) {
    if (!run) return;
    try {
      await api.decide(slug, run.run_id, payload);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function cancel() {
    if (!run) return;
    await api.cancelRun(slug, run.run_id);
  }

  const phaseDone = (phase: string) => {
    if (!run) return false;
    const order = PHASES.indexOf(PHASE_LABEL[run.phase] ?? run.phase);
    const target = PHASES.indexOf(phase);
    return run.status === "done" ? true : target >= 0 && order > target;
  };
  const phaseActive = (phase: string) => run != null && (PHASE_LABEL[run.phase] ?? run.phase) === phase;

  return (
    <div className="stack">
      {error ? <Banner>{error}</Banner> : null}

      {!run ? (
        <EmptyState
          title={t("run.noRun")}
          action={
            <Button variant="primary" loading={starting} onClick={() => void start()}>
              {t("run.start")}
            </Button>
          }
        />
      ) : (
        <>
          <Card
            title={`${t("run.title")} · ${run.run_id}`}
            actions={
              <div className="row-tight">
                <Badge tone={statusTone(run.status)}>{t(`run.status.${run.status}`)}</Badge>
                {isLive ? (
                  <Button size="sm" variant="danger" onClick={() => void cancel()}>
                    {t("run.stop")}
                  </Button>
                ) : (
                  <Button size="sm" onClick={() => void start()} loading={starting}>
                    {t("run.start")}
                  </Button>
                )}
              </div>
            }
          >
            <div className="stats" style={{ marginBottom: 16 }}>
              <div className="stat">
                <span className="stat-label">{t("run.phase")}</span>
                <span className="stat-value" style={{ fontSize: 15 }}>
                  {run.phase}
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">{t("run.tokens")}</span>
                <span className="stat-value" style={{ fontSize: 15 }}>
                  {run.tokens_in.toLocaleString()} / {run.tokens_out.toLocaleString()}
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">{t("run.cost")}</span>
                <span className="stat-value" style={{ fontSize: 15 }}>
                  US$ {run.cost_usd.toFixed(3)}
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">{run.provider}</span>
                <span className="stat-value" style={{ fontSize: 15 }}>
                  {run.model}
                </span>
              </div>
            </div>

            <div className="phase-bar">
              {PHASES.map((phase) => (
                <span
                  key={phase}
                  className={`phase ${phaseActive(phase) ? "active" : ""} ${phaseDone(phase) ? "done" : ""}`}
                >
                  {phase}
                </span>
              ))}
            </div>

            {run.error ? <Banner>{run.error}</Banner> : null}

            {run.checkpoint ? (
              <CheckpointView
                run={run}
                selected={selected}
                setSelected={setSelected}
                sections={sections}
                setSections={setSections}
                decide={decide}
              />
            ) : null}
          </Card>

          <Card title={t("run.log")}>
            {events.length === 0 ? (
              <div className="row">
                <Spinner /> {t("common.loading")}
              </div>
            ) : (
              <div className="log">
                {events.map((event, index) => (
                  <div
                    key={index}
                    className={`log-line ${event.kind.includes("warning") ? "warn" : ""} ${
                      event.kind === "error" ? "error" : ""
                    }`}
                  >
                    <span className="when">{event.ts.slice(11, 19)}</span>
                    <span className="kind">{event.kind}</span>
                    <span className="msg">
                      {event.message}
                      {event.kind === "source.added" && (event.data as { paper_id?: string }).paper_id
                        ? ` · ${(event.data as { paper_id?: string }).paper_id}`
                        : ""}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}

function CheckpointView({
  run,
  selected,
  setSelected,
  sections,
  setSections,
  decide,
}: {
  run: RunState;
  selected: Set<string>;
  setSelected: (next: Set<string>) => void;
  sections: Set<string>;
  setSections: (next: Set<string>) => void;
  decide: (payload: Record<string, unknown>) => void;
}) {
  const { t } = useT();
  const checkpoint = run.checkpoint;
  if (!checkpoint) return null;
  const data = checkpoint.data as Record<string, unknown>;

  return (
    <div className="checkpoint">
      <h4>{t("run.waiting")}</h4>
      <p className="hint" style={{ marginTop: 2 }}>
        {checkpoint.summary}
      </p>

      {checkpoint.kind === "candidates" && Array.isArray(data.candidates) ? (
        <>
          <div className="row" style={{ marginTop: 10 }}>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setSelected(new Set((data.candidates as CandidateRow[]).map((c) => c.key)))}
            >
              {t("run.selectAll")}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
              {t("run.selectNone")}
            </Button>
            <span className="hint">{(data.candidates as CandidateRow[]).length} {t("run.candidates")}</span>
          </div>
          <div className="candidate-list">
            {(data.candidates as CandidateRow[]).map((candidate) => (
              <label key={candidate.key} className="candidate">
                <input
                  type="checkbox"
                  checked={selected.has(candidate.key)}
                  onChange={(e) => {
                    const next = new Set(selected);
                    if (e.target.checked) next.add(candidate.key);
                    else next.delete(candidate.key);
                    setSelected(next);
                  }}
                />
                <span>
                  <span className="t">{candidate.title}</span>
                  <div className="m">
                    {[candidate.year, candidate.venue, candidate.theme].filter(Boolean).join(" · ")}
                    {candidate.doi ? ` · ${candidate.doi}` : ""}
                  </div>
                </span>
                <span className="row-tight">
                  {candidate.oa ? <Badge tone="good">OA</Badge> : null}
                  <span className="mono">{candidate.score.toFixed(2)}</span>
                </span>
              </label>
            ))}
          </div>
          <div className="row">
            <Button
              variant="primary"
              onClick={() => decide({ action: "continue", keys: [...selected] })}
              disabled={selected.size === 0}
            >
              {t("run.approveSelected")}
            </Button>
            <Button variant="ghost" onClick={() => decide({ action: "continue", keys: [] })}>
              {t("run.approve")} ({t("common.none")})
            </Button>
            <Button variant="ghost" onClick={() => decide({ action: "stop" })}>
              {t("run.reject")}
            </Button>
          </div>
        </>
      ) : null}

      {checkpoint.kind === "outline" && Array.isArray(data.sections) ? (
        <>
          <div className="candidate-list" style={{ marginTop: 10 }}>
            {(data.sections as { heading: string; evidence: number }[]).map((section) => (
              <label key={section.heading} className="candidate">
                <input
                  type="checkbox"
                  checked={sections.has(section.heading)}
                  onChange={(e) => {
                    const next = new Set(sections);
                    if (e.target.checked) next.add(section.heading);
                    else next.delete(section.heading);
                    setSections(next);
                  }}
                />
                <span className="t">{section.heading}</span>
                <span className="mono">{section.evidence} ids</span>
              </label>
            ))}
          </div>
          <div className="row">
            <Button
              variant="primary"
              onClick={() => decide({ action: "continue", sections: [...sections] })}
              disabled={sections.size === 0}
            >
              {t("run.approve")}
            </Button>
            <Button variant="ghost" onClick={() => decide({ action: "stop" })}>
              {t("run.reject")}
            </Button>
          </div>
        </>
      ) : null}

      {checkpoint.kind === "review" ? (
        <>
          <div className="row" style={{ marginTop: 10 }}>
            <Button variant="primary" onClick={() => decide({ action: "accept" })}>
              {t("run.accept")}
            </Button>
            <Button onClick={() => decide({ action: "revise" })}>{t("run.revise")}</Button>
            <Button variant="ghost" onClick={() => decide({ action: "stop" })}>
              {t("run.reject")}
            </Button>
          </div>
        </>
      ) : null}
    </div>
  );
}
