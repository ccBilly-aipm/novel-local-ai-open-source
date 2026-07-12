import { useEffect, useMemo, useState } from "react";
import AppShell from "./components/AppShell";
import Dashboard from "./components/Dashboard";
import type { GlobalPage } from "./components/GlobalNav";
import ProjectWorkspaceShell, { type ProjectView } from "./components/ProjectWorkspaceShell";
import SettingsPage from "./components/SettingsPage";
import ActivityListPage from "./features/runs/ActivityListPage";
import { api } from "./services/api";
import type { ActivityItem, ChapterLoopRunSummary, ModelProvider, Novel, Project } from "./types";

interface RouteState {
  page: GlobalPage;
  projectId: string | null;
  projectView: ProjectView;
  runId: string | null;
}

const globalPages = new Set<GlobalPage>(["projects", "runs", "models", "prompts", "settings"]);
const projectViews = new Set<ProjectView>(["overview", "chapters", "creative", "characters", "world", "runs", "advanced"]);

function parseRoute(): RouteState {
  const parts = window.location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "projects" && parts[1]) {
    const view = projectViews.has(parts[2] as ProjectView) ? parts[2] as ProjectView : "overview";
    return {
      page: "projects",
      projectId: parts[1],
      projectView: view,
      runId: view === "runs" && parts[3] ? parts[3] : null,
    };
  }
  const page = globalPages.has(parts[0] as GlobalPage) ? parts[0] as GlobalPage : "projects";
  return { page, projectId: null, projectView: "overview", runId: null };
}

function navigate(path: string) {
  window.location.hash = path;
}

export default function App() {
  const [route, setRoute] = useState<RouteState>(() => parseRoute());
  const [projects, setProjects] = useState<Project[]>([]);
  const [runs, setRuns] = useState<ChapterLoopRunSummary[]>([]);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [providers, setProviders] = useState<ModelProvider[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [activeNovel, setActiveNovel] = useState<Novel | null>(null);
  const [error, setError] = useState("");

  async function loadGlobal() {
    try {
      await api<ModelProvider[]>("/model-providers/sync-local", { method: "POST" });
      const [projectData, runData, providerData, activityData] = await Promise.all([
        api<Project[]>("/projects"),
        api<ChapterLoopRunSummary[]>("/loop-runs?limit=200"),
        api<ModelProvider[]>("/model-providers"),
        api<ActivityItem[]>("/activity?limit=300"),
      ]);
      setProjects(projectData);
      setRuns(runData);
      setProviders(providerData);
      setActivity(activityData);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法连接后端");
    }
  }

  async function loadProject(projectId: string) {
    try {
      const [project, projectRuns] = await Promise.all([
        api<Project>(`/projects/${projectId}`),
        api<ChapterLoopRunSummary[]>(`/projects/${projectId}/runs?limit=200`),
      ]);
      setActiveProject(project);
      setActiveNovel(project.novels?.[0] || null);
      setRuns((current) => [
        ...projectRuns,
        ...current.filter((run) => run.project_id !== projectId),
      ].sort((a, b) => b.updated_at.localeCompare(a.updated_at)));
      setError("");
    } catch (reason) {
      setActiveProject(null);
      setActiveNovel(null);
      setError(reason instanceof Error ? reason.message : "打开项目失败");
    }
  }

  async function refreshAll() {
    await loadGlobal();
    if (route.projectId) await loadProject(route.projectId);
  }

  async function startAnalysis(text: string, name: string) {
    try {
      const project = await api<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      await api<Novel>("/novels", {
        method: "POST",
        body: JSON.stringify({ project_id: project.id, title: name }),
      });
      window.localStorage.setItem("pending_deconstruct_text", text);
      await loadGlobal();
      navigate(`/projects/${project.id}/creative`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建分析项目失败");
    }
  }

  useEffect(() => {
    if (!window.location.hash) navigate("/projects");
    const onHashChange = () => setRoute(parseRoute());
    window.addEventListener("hashchange", onHashChange);
    void loadGlobal();
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    if (route.projectId) {
      void loadProject(route.projectId);
    } else {
      setActiveProject(null);
      setActiveNovel(null);
    }
  }, [route.projectId]);

  const projectRuns = useMemo(
    () => route.projectId ? runs.filter((run) => run.project_id === route.projectId) : [],
    [runs, route.projectId],
  );
  const waitingCount = runs.filter((run) => run.status === "waiting").length;

  function openGlobal(page: GlobalPage) {
    navigate(`/${page}`);
  }

  return (
    <AppShell active={route.projectId ? "projects" : (route.page === "models" || route.page === "prompts" ? "settings" : route.page)} waitingCount={waitingCount} onNavigate={openGlobal}>
      {route.projectId ? (
        activeProject && activeNovel ? (
          <ProjectWorkspaceShell
            project={activeProject}
            novel={activeNovel}
            view={route.projectView}
            runId={route.runId}
            providers={providers}
            runs={projectRuns}
            onNovelChange={setActiveNovel}
            onNavigate={(view) => navigate(`/projects/${activeProject.id}/${view}`)}
            onOpenRun={(runId) => navigate(`/projects/${activeProject.id}/runs/${runId}`)}
            onRefresh={refreshAll}
          />
        ) : (
          <main className="mx-auto max-w-7xl p-8">
            <div className="panel p-8 text-center text-sm text-black/45">{error || "正在加载项目..."}</div>
          </main>
        )
      ) : route.page === "runs" ? (
        <ActivityListPage
          activity={activity}
          onOpen={(item) => {
            if (!item.project_id) return;
            if (item.kind === "loop") navigate(`/projects/${item.project_id}/runs/${item.id}`);
            else if (item.kind === "creative" || item.kind === "deconstruction") navigate(`/projects/${item.project_id}/creative`);
            else navigate(`/projects/${item.project_id}/runs`);
          }}
        />
      ) : route.page === "models" || route.page === "prompts" || route.page === "settings" ? (
        <SettingsPage initialTab={route.page === "prompts" ? "prompts" : "models"} />
      ) : (
        <Dashboard
          projects={projects}
          runs={runs}
          providers={providers}
          error={error}
          onRefresh={loadGlobal}
          onOpen={(projectId) => navigate(`/projects/${projectId}/overview`)}
          onOpenRun={(run) => navigate(`/projects/${run.project_id}/runs/${run.id}`)}
          onOpenModels={() => navigate("/models")}
          onAnalyze={startAnalysis}
        />
      )}
    </AppShell>
  );
}
