import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useT } from "../i18n";
import type { ProjectMeta } from "../types";
import { Badge, Banner, Button, EmptyState, Spinner } from "../ui";
import { navigate } from "../App";

function statusTone(status: ProjectMeta["status"]) {
  if (status === "done") return "good" as const;
  if (status === "running") return "info" as const;
  return "neutral" as const;
}

export function ProjectsScreen() {
  const { t } = useT();
  const [items, setItems] = useState<ProjectMeta[] | null>(null);
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const load = () => {
    api
      .projects()
      .then(setItems)
      .catch((e: Error) => setError(e.message));
  };

  useEffect(load, []);

  async function importZip(file: File) {
    try {
      const { slug } = await api.importProject(file);
      navigate(`/p/${slug}`);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove(slug: string) {
    if (!window.confirm(t("projects.deleteConfirm"))) return;
    await api.deleteProject(slug);
    load();
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{t("projects.title")}</h1>
          <p>{t("projects.subtitle")}</p>
        </div>
        <div className="row">
          <input
            ref={fileInput}
            type="file"
            accept=".zip"
            style={{ display: "none" }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void importZip(file);
            }}
          />
          <Button onClick={() => fileInput.current?.click()}>{t("projects.import")}</Button>
          <Button variant="primary" onClick={() => navigate("/new")}>
            {t("projects.new")}
          </Button>
        </div>
      </div>

      {error ? <Banner>{error}</Banner> : null}

      {items === null ? (
        <div className="row">
          <Spinner /> {t("common.loading")}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          title={t("projects.empty")}
          hint={t("projects.emptyHint")}
          action={
            <Button variant="primary" onClick={() => navigate("/new")}>
              {t("projects.new")}
            </Button>
          }
        />
      ) : (
        <div className="grid-2">
          {items.map((project) => (
            <article key={project.slug} className="card project-card">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span className="project-title">{project.title}</span>
                <Badge tone={statusTone(project.status)}>{project.status}</Badge>
              </div>
              <div className="project-meta">
                <span>
                  {project.sources ?? 0} {t("projects.sources")}
                </span>
                <span>
                  {project.last_run
                    ? `${t("projects.lastRun")}: ${project.last_run.status} · $${project.last_run.cost_usd.toFixed(2)}`
                    : t("projects.noRuns")}
                </span>
              </div>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div className="row-tight">
                  <Button size="sm" variant="primary" onClick={() => navigate(`/p/${project.slug}`)}>
                    {t("common.overview")}
                  </Button>
                  <Button
                    size="sm"
                    onClick={async () => {
                      const { slug } = await api.duplicateProject(project.slug);
                      navigate(`/p/${slug}`);
                    }}
                  >
                    {t("projects.duplicate")}
                  </Button>
                </div>
                <div className="row-tight">
                  <Button size="sm" variant="ghost" onClick={() => (window.location.href = `/api/projects/${project.slug}/export.zip`)}>
                    {t("projects.export")}
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void remove(project.slug)}>
                    {t("common.delete")}
                  </Button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}
