import { useEffect, useState } from "react";
import type { Brief } from "../types";
import { useT } from "../i18n";
import { Checkbox, Field, Select, TextArea, TextInput } from "../ui";

export type BriefSection = "object" | "questions" | "search" | "viewpoints" | "deliverable" | "all";

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "pt", label: "Português" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
  { code: "de", label: "Deutsch" },
];

const OUTPUT_LANGUAGES = [
  { code: "pt-BR", label: "Português (Brasil)" },
  { code: "en", label: "English" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
];

const SOURCES = [
  { id: "openalex", label: "OpenAlex" },
  { id: "crossref", label: "Crossref" },
  { id: "europepmc", label: "Europe PMC" },
  { id: "scielo", label: "SciELO" },
];

export const SECTION_PRESETS: Record<string, string[]> = {
  article: [
    "Executive summary",
    "Scope & method",
    "Viewpoint map",
    "Main points of analysis",
    "Technical / methodological challenges",
    "Evidence gaps & open questions",
    "References",
  ],
  proposal: [
    "Problem statement",
    "State of the art",
    "Viewpoint map",
    "Objectives",
    "Method",
    "Risks and limitations",
    "References",
  ],
  thesis: [
    "Introduction",
    "Literature review",
    "Viewpoint map",
    "Theoretical framework",
    "Methodological challenges",
    "Evidence gaps",
    "References",
  ],
  report: [
    "Executive summary",
    "Findings by viewpoint",
    "Technical challenges",
    "Recommendations",
    "Evidence gaps",
    "References",
  ],
};

function splitList(text: string): string[] {
  return text
    .split(/[,;\n]/)
    .map((v) => v.trim())
    .filter(Boolean);
}

/** Comma/semicolon list input that only rewrites itself when the value changes elsewhere. */
function ListInput({
  value,
  onChange,
  placeholder,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  const [text, setText] = useState(value.join(", "));
  useEffect(() => {
    const parsed = splitList(text).join("\u0000");
    if (parsed !== value.join("\u0000")) setText(value.join(", "));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(value)]);
  return (
    <TextInput
      value={text}
      placeholder={placeholder}
      onChange={(e) => {
        setText(e.target.value);
        onChange(splitList(e.target.value));
      }}
    />
  );
}

function LinesInput({
  value,
  onChange,
  rows = 7,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  rows?: number;
}) {
  const [text, setText] = useState(value.join("\n"));
  useEffect(() => {
    const parsed = text
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .join("\u0000");
    if (parsed !== value.join("\u0000")) setText(value.join("\n"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(value)]);
  return (
    <TextArea
      rows={rows}
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        onChange(
          e.target.value
            .split("\n")
            .map((l) => l.trim())
            .filter(Boolean),
        );
      }}
    />
  );
}

export function BriefForm({
  brief,
  onChange,
  section = "all",
}: {
  brief: Brief;
  onChange: (next: Brief) => void;
  section?: BriefSection;
}) {
  const { t } = useT();
  const show = (id: BriefSection) => section === "all" || section === id;
  const set = (patch: Partial<Brief>) => onChange({ ...brief, ...patch });
  const setDeliverable = (patch: Partial<Brief["deliverable"]>) =>
    onChange({ ...brief, deliverable: { ...brief.deliverable, ...patch } });

  const yearValue = (v: number | null) => (v == null ? "" : String(v));
  const parseYear = (v: string): number | null => {
    const cleaned = v.replace(/[^0-9]/g, "").slice(0, 4);
    return cleaned ? Number(cleaned) : null;
  };

  return (
    <>
      {show("object") && (
        <>
          <Field label={t("f.title")} hint={t("f.titleHelp")} required>
            <TextInput
              value={brief.title}
              placeholder="Telhados verdes e ilhas de calor urbanas"
              onChange={(e) => set({ title: e.target.value })}
            />
          </Field>
          <Field label={t("f.topic")} hint={t("f.topicHelp")} required>
            <TextArea
              rows={4}
              value={brief.topic}
              placeholder="O efeito de telhados verdes na redução de ilhas de calor em centros urbanos."
              onChange={(e) => set({ topic: e.target.value })}
            />
          </Field>
          <div className="form-grid">
            <Field label={t("f.disciplines")} hint={t("f.disciplinesHelp")}>
              <ListInput
                value={brief.disciplines}
                onChange={(v) => set({ disciplines: v })}
                placeholder="urban climatology, public policy"
              />
            </Field>
            <Field label={t("f.geography")}>
              <TextInput
                value={brief.geography}
                placeholder="global"
                onChange={(e) => set({ geography: e.target.value })}
              />
            </Field>
            <Field label={t("f.yearFrom")}>
              <TextInput
                value={yearValue(brief.year_from)}
                inputMode="numeric"
                placeholder="2010"
                onChange={(e) => set({ year_from: parseYear(e.target.value) })}
              />
            </Field>
            <Field label={t("f.yearTo")}>
              <TextInput
                value={yearValue(brief.year_to)}
                inputMode="numeric"
                placeholder=""
                onChange={(e) => set({ year_to: parseYear(e.target.value) })}
              />
            </Field>
          </div>
          <Field label={t("f.litLanguages")} hint={t("f.litLanguagesHelp")}>
            <div className="row">
              {LANGUAGES.map((lang) => (
                <Checkbox
                  key={lang.code}
                  label={lang.label}
                  checked={brief.lit_languages.includes(lang.code)}
                  onChange={(on) =>
                    set({
                      lit_languages: on
                        ? [...brief.lit_languages, lang.code]
                        : brief.lit_languages.filter((l) => l !== lang.code),
                    })
                  }
                />
              ))}
            </div>
          </Field>
          <Field label={t("f.outputLanguage")} hint={t("f.outputLanguageHelp")}>
            <Select
              value={brief.output_language}
              onChange={(e) => set({ output_language: e.target.value })}
            >
              {OUTPUT_LANGUAGES.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.label}
                </option>
              ))}
            </Select>
          </Field>
        </>
      )}

      {show("questions") && (
        <>
          <p className="hint">{t("f.rqsHelp")}</p>
          {brief.rqs.map((rq, index) => (
            <div key={index} className="repeat-row two">
              <Field label={`${t("f.rq")} ${index + 1}`}>
                <TextInput
                  value={rq.question}
                  placeholder="Telhados verdes reduzem a temperatura de superfície?"
                  onChange={(e) => {
                    const next = [...brief.rqs];
                    next[index] = { ...rq, question: e.target.value };
                    set({ rqs: next });
                  }}
                />
              </Field>
              <Field label={t("f.rqWhy")}>
                <TextInput
                  value={rq.why}
                  placeholder="orienta o investimento público"
                  onChange={(e) => {
                    const next = [...brief.rqs];
                    next[index] = { ...rq, why: e.target.value };
                    set({ rqs: next });
                  }}
                />
              </Field>
              <button
                className="btn btn-ghost btn-sm"
                style={{ marginTop: 22 }}
                onClick={() => set({ rqs: brief.rqs.filter((_, i) => i !== index) })}
                disabled={brief.rqs.length <= 1}
              >
                {t("common.remove")}
              </button>
            </div>
          ))}
          <button
            className="btn btn-sm"
            onClick={() => set({ rqs: [...brief.rqs, { question: "", why: "" }] })}
          >
            + {t("f.addRq")}
          </button>
        </>
      )}

      {show("search") && (
        <>
          <p className="hint">{t("f.themesHelp")}</p>
          {brief.themes.map((theme, index) => (
            <div key={index} style={{ marginBottom: 14 }}>
              <div className="repeat-row">
                <Field label={t("f.themeName")}>
                  <TextInput
                    value={theme.name}
                    placeholder="green infrastructure"
                    onChange={(e) => {
                      const next = [...brief.themes];
                      next[index] = { ...theme, name: e.target.value };
                      set({ themes: next });
                    }}
                  />
                </Field>
                <Field label={t("f.keywordsEn")}>
                  <ListInput
                    value={theme.keywords_en}
                    placeholder="green roof, urban heat island"
                    onChange={(v) => {
                      const next = [...brief.themes];
                      next[index] = { ...theme, keywords_en: v };
                      set({ themes: next });
                    }}
                  />
                </Field>
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ marginTop: 22 }}
                  onClick={() => set({ themes: brief.themes.filter((_, i) => i !== index) })}
                >
                  {t("common.remove")}
                </button>
              </div>
              <Field label={t("f.keywordsOther")}>
                <ListInput
                  value={theme.keywords_other}
                  placeholder="telhado verde, ilha de calor"
                  onChange={(v) => {
                    const next = [...brief.themes];
                    next[index] = { ...theme, keywords_other: v };
                    set({ themes: next });
                  }}
                />
              </Field>
            </div>
          ))}
          <button
            className="btn btn-sm"
            onClick={() =>
              set({
                themes: [...brief.themes, { name: "", keywords_en: [], keywords_other: [], sources: [] }],
              })
            }
          >
            + {t("f.addTheme")}
          </button>

          <div className="section-label">{t("f.sourcesEnabled")}</div>
          <div className="row">
            {SOURCES.map((source) => (
              <Checkbox
                key={source.id}
                label={source.label}
                checked={brief.sources_enabled.includes(source.id)}
                onChange={(on) =>
                  set({
                    sources_enabled: on
                      ? [...brief.sources_enabled, source.id]
                      : brief.sources_enabled.filter((s) => s !== source.id),
                  })
                }
              />
            ))}
          </div>

          <div className="section-label">{t("f.includePeerReviewed")}</div>
          <div className="row">
            <Checkbox
              label={t("f.includePeerReviewed")}
              checked={brief.include_peer_reviewed}
              onChange={(v) => set({ include_peer_reviewed: v })}
            />
            <Checkbox
              label={t("f.includeGrey")}
              checked={brief.include_grey}
              onChange={(v) => set({ include_grey: v })}
            />
          </div>

          <div className="form-grid" style={{ marginTop: 14 }}>
            <Field label={t("f.excludeTerms")}>
              <ListInput value={brief.exclude_terms} onChange={(v) => set({ exclude_terms: v })} />
            </Field>
            <Field label={t("f.minSources")}>
              <TextInput
                type="number"
                min={1}
                value={brief.min_sources}
                onChange={(e) => set({ min_sources: Number(e.target.value) || 1 })}
              />
            </Field>
          </div>
        </>
      )}

      {show("viewpoints") && (
        <>
          <p className="hint">{t("f.viewpointsHelp")}</p>
          {brief.viewpoints.map((vp, index) => (
            <div key={index} className="repeat-row two">
              <Field label={t("f.viewpoint")}>
                <TextInput
                  value={vp.label}
                  placeholder="green infrastructure"
                  onChange={(e) => {
                    const next = [...brief.viewpoints];
                    next[index] = { ...vp, label: e.target.value };
                    set({ viewpoints: next });
                  }}
                />
              </Field>
              <Field label={t("f.viewpointDesc")}>
                <TextInput
                  value={vp.description}
                  placeholder="vegetation as primary mitigation"
                  onChange={(e) => {
                    const next = [...brief.viewpoints];
                    next[index] = { ...vp, description: e.target.value };
                    set({ viewpoints: next });
                  }}
                />
              </Field>
              <button
                className="btn btn-ghost btn-sm"
                style={{ marginTop: 22 }}
                onClick={() => set({ viewpoints: brief.viewpoints.filter((_, i) => i !== index) })}
              >
                {t("common.remove")}
              </button>
            </div>
          ))}
          <button
            className="btn btn-sm"
            onClick={() => set({ viewpoints: [...brief.viewpoints, { label: "", description: "", proponents: [] }] })}
          >
            + {t("f.addViewpoint")}
          </button>
        </>
      )}

      {show("deliverable") && (
        <>
          <div className="form-grid">
            <Field label={t("f.template")}>
              <Select
                value={brief.deliverable.template}
                onChange={(e) => {
                  const template = e.target.value;
                  onChange({
                    ...brief,
                    deliverable: {
                      ...brief.deliverable,
                      template,
                      sections: SECTION_PRESETS[template] ?? brief.deliverable.sections,
                    },
                  });
                }}
              >
                {Object.keys(SECTION_PRESETS).map((key) => (
                  <option key={key} value={key}>
                    {key}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t("f.lengthWords")}>
              <TextInput
                type="number"
                min={300}
                step={100}
                value={brief.deliverable.length_words}
                onChange={(e) => setDeliverable({ length_words: Number(e.target.value) || 2500 })}
              />
            </Field>
            <Field label={t("f.tone")}>
              <TextInput
                value={brief.deliverable.tone}
                placeholder="academic funding committee"
                onChange={(e) => setDeliverable({ tone: e.target.value })}
              />
            </Field>
            <Field label={t("f.costCap")}>
              <TextInput
                type="number"
                min={0}
                step={0.5}
                value={brief.deliverable.cost_cap_usd}
                onChange={(e) => setDeliverable({ cost_cap_usd: Number(e.target.value) || 0 })}
              />
            </Field>
            <Field label={t("f.maxRounds")}>
              <TextInput
                type="number"
                min={1}
                max={4}
                value={brief.deliverable.max_rounds}
                onChange={(e) => setDeliverable({ max_rounds: Number(e.target.value) || 1 })}
              />
            </Field>
            <Field label={t("f.citationStyle")}>
              <Select
                value={brief.deliverable.citation_style}
                onChange={(e) =>
                  setDeliverable({ citation_style: e.target.value as "numeric" | "author-year" })
                }
              >
                <option value="numeric">numeric [P-0001]</option>
                <option value="author-year">author-year + BibTeX</option>
              </Select>
            </Field>
          </div>
          <Field label={t("f.sections")} hint={t("f.sectionsHelp")}>
            <LinesInput value={brief.deliverable.sections} onChange={(v) => setDeliverable({ sections: v })} />
          </Field>
          <div className="row" style={{ marginBottom: 14 }}>
            <Checkbox
              label={t("f.bibtex")}
              checked={brief.deliverable.bibtex}
              onChange={(v) => setDeliverable({ bibtex: v })}
            />
          </div>
          <div className="section-label">{t("f.checkpoints")}</div>
          <div className="row">
            <Checkbox
              label={t("f.cpCandidates")}
              checked={brief.checkpoints.candidates}
              onChange={(v) => set({ checkpoints: { ...brief.checkpoints, candidates: v } })}
            />
            <Checkbox
              label={t("f.cpOutline")}
              checked={brief.checkpoints.outline}
              onChange={(v) => set({ checkpoints: { ...brief.checkpoints, outline: v } })}
            />
            <Checkbox
              label={t("f.cpReview")}
              checked={brief.checkpoints.review}
              onChange={(v) => set({ checkpoints: { ...brief.checkpoints, review: v } })}
            />
          </div>
        </>
      )}
    </>
  );
}

export function emptyBrief(): Brief {
  return {
    title: "",
    topic: "",
    disciplines: [],
    year_from: null,
    year_to: null,
    geography: "global",
    lit_languages: ["en", "pt"],
    output_language: "pt-BR",
    rqs: [{ question: "", why: "" }],
    themes: [{ name: "", keywords_en: [], keywords_other: [], sources: [] }],
    include_peer_reviewed: true,
    include_grey: false,
    exclude_terms: [],
    min_sources: 20,
    max_candidates: 40,
    max_fetches: 40,
    viewpoints: [],
    deliverable: {
      template: "article",
      sections: [...SECTION_PRESETS.article],
      length_words: 2500,
      tone: "academic funding committee",
      citation_style: "numeric",
      bibtex: true,
      max_rounds: 1,
      cost_cap_usd: 2,
    },
    checkpoints: { candidates: true, outline: true, review: true },
    sources_enabled: ["openalex", "crossref"],
  };
}
