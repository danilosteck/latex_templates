import { useState } from "react";
import { api } from "../api";
import { useT } from "../i18n";
import { navigate } from "../App";
import type { Brief } from "../types";
import { Banner, Button, Card } from "../ui";
import { BriefForm, emptyBrief } from "../components/BriefForm";

const STEPS = ["object", "questions", "search", "viewpoints", "deliverable"] as const;
type Step = (typeof STEPS)[number] | "review";

export function Wizard() {
  const { t } = useT();
  const [brief, setBrief] = useState<Brief>(emptyBrief);
  const [step, setStep] = useState<Step>("object");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const stepIndex = step === "review" ? STEPS.length : STEPS.indexOf(step as (typeof STEPS)[number]);

  const stepLabel: Record<string, string> = {
    object: t("wizard.step1"),
    questions: t("wizard.step2"),
    search: t("wizard.step3"),
    viewpoints: t("wizard.step4"),
    deliverable: t("wizard.step5"),
    review: t("wizard.review"),
  };

  const canContinue =
    step !== "object" || (brief.title.trim().length > 2 && brief.topic.trim().length > 10);

  async function create() {
    setSaving(true);
    setError("");
    try {
      const { slug } = await api.createProject(brief);
      navigate(`/p/${slug}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{t("wizard.title")}</h1>
          <p>{t("wizard.help")}</p>
        </div>
        <Button variant="ghost" onClick={() => navigate("/")}>
          {t("common.cancel")}
        </Button>
      </div>

      <div className="steps">
        {STEPS.map((id, index) => (
          <div
            key={id}
            className={`step ${step === id ? "active" : ""} ${index < stepIndex ? "done" : ""}`}
          >
            <span className="step-index">{index + 1}</span>
            {stepLabel[id]}
          </div>
        ))}
        <div className={`step ${step === "review" ? "active" : ""}`}>
          <span className="step-index">{STEPS.length + 1}</span>
          {stepLabel.review}
        </div>
      </div>

      {error ? <Banner>{error}</Banner> : null}

      <Card>
        {step === "review" ? (
          <div className="stack">
            <div className="stats">
              <div className="stat">
                <span className="stat-label">{t("f.title")}</span>
                <span className="stat-value" style={{ fontSize: 15 }}>
                  {brief.title || "—"}
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">{t("f.rqs")}</span>
                <span className="stat-value">{brief.rqs.filter((r) => r.question.trim()).length}</span>
              </div>
              <div className="stat">
                <span className="stat-label">{t("f.themes")}</span>
                <span className="stat-value">{brief.themes.filter((x) => x.name.trim()).length}</span>
              </div>
              <div className="stat">
                <span className="stat-label">{t("f.sections")}</span>
                <span className="stat-value">{brief.deliverable.sections.length}</span>
              </div>
            </div>
            <div>
              <p className="hint">{brief.topic}</p>
            </div>
            <div className="stats">
              <div className="stat">
                <span className="stat-label">{t("f.outputLanguage")}</span>
                <span className="stat-value" style={{ fontSize: 15 }}>
                  {brief.output_language}
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">{t("f.costCap")}</span>
                <span className="stat-value" style={{ fontSize: 15 }}>
                  US$ {brief.deliverable.cost_cap_usd.toFixed(2)}
                </span>
              </div>
              <div className="stat">
                <span className="stat-label">{t("f.sourcesEnabled")}</span>
                <span className="stat-value" style={{ fontSize: 15 }}>
                  {brief.sources_enabled.join(", ")}
                </span>
              </div>
            </div>
            {brief.themes.every((x) => !x.name.trim()) ? (
              <Banner tone="warn">
                Nenhum tema com palavra-chave: a busca usará apenas o título. / No themed keywords:
                the search will fall back to the title.
              </Banner>
            ) : null}
          </div>
        ) : (
          <BriefForm brief={brief} onChange={setBrief} section={step} />
        )}

        <div className="wizard-foot">
          <Button
            variant="ghost"
            onClick={() => {
              const index = STEPS.indexOf(step as (typeof STEPS)[number]);
              if (step === "review") setStep(STEPS[STEPS.length - 1]);
              else if (index > 0) setStep(STEPS[index - 1]);
              else navigate("/");
            }}
          >
            {t("common.back")}
          </Button>
          <div className="row">
            {step === "review" ? (
              <Button variant="primary" loading={saving} onClick={() => void create()}>
                {t("wizard.create")}
              </Button>
            ) : (
              <Button
                variant="primary"
                disabled={!canContinue}
                onClick={() => {
                  const index = STEPS.indexOf(step as (typeof STEPS)[number]);
                  setStep(index < STEPS.length - 1 ? STEPS[index + 1] : "review");
                }}
              >
                {t("common.next")}
              </Button>
            )}
          </div>
        </div>
      </Card>
    </>
  );
}
