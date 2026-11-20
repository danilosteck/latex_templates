import { useEffect, useState, type ReactElement } from "react";
import { api } from "./api";
import { useT, setLang, type Lang } from "./i18n";
import { ProjectsScreen } from "./screens/Projects";
import { Wizard } from "./screens/Wizard";
import { ProjectView } from "./screens/ProjectView";
import { AgentEditor } from "./screens/AgentEditor";
import { SettingsScreen } from "./screens/Settings";

function useHashRoute(): string {
  const [route, setRoute] = useState(() => window.location.hash.slice(1) || "/");
  useEffect(() => {
    const onChange = () => setRoute(window.location.hash.slice(1) || "/");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export function navigate(path: string) {
  window.location.hash = path;
}

export function App() {
  const { t, lang, setLang: changeLang } = useT();
  const route = useHashRoute();
  const [health, setHealth] = useState<{ version: string; workspace: string } | null>(null);
  const [provider, setProvider] = useState<string>("");

  useEffect(() => {
    api
      .health()
      .then((h) => setHealth(h))
      .catch(() => setHealth(null));
    api
      .settings()
      .then((s) => setProvider(`${s.settings.provider} · ${s.settings.model}`))
      .catch(() => setProvider(""));
  }, [route]);

  const parts = route.split("/").filter(Boolean);
  let screen: ReactElement;
  let active = "";

  if (parts[0] === "new") {
    active = "projects";
    screen = <Wizard />;
  } else if (parts[0] === "settings") {
    active = "settings";
    screen = <SettingsScreen />;
  } else if (parts[0] === "p" && parts[1]) {
    active = "projects";
    if (parts[2] === "agents" && parts[3]) {
      screen = <AgentEditor slug={parts[1]} agentId={parts[3]} />;
    } else {
      screen = <ProjectView slug={parts[1]} initialTab={parts[2]} />;
    }
  } else {
    active = "projects";
    screen = <ProjectsScreen />;
  }

  function onLang(value: string) {
    changeLang(value as Lang);
    setLang(value as Lang);
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand" onClick={() => navigate("/")} role="button" tabIndex={0}>
          <span className="brand-mark">B</span>
          Bibliometric Studio
        </div>
        <nav className="nav">
          <button className={`nav-link ${active === "projects" ? "active" : ""}`} onClick={() => navigate("/")}>
            {t("nav.projects")}
          </button>
          <button
            className={`nav-link ${active === "settings" ? "active" : ""}`}
            onClick={() => navigate("/settings")}
          >
            {t("nav.settings")}
          </button>
        </nav>
        <div className="topbar-right">
          {provider ? (
            <span className="provider-pill" title={health?.workspace ?? ""}>
              <span className={`dot ${provider.startsWith("mock") ? "" : "live"}`} />
              {provider}
            </span>
          ) : null}
          <select className="input select" style={{ width: 96 }} value={lang} onChange={(e) => onLang(e.target.value)}>
            <option value="pt-BR">PT-BR</option>
            <option value="en">EN</option>
          </select>
        </div>
      </header>
      <main className="content">{screen}</main>
    </div>
  );
}
