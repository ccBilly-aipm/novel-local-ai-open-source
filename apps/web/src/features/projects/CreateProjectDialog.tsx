import { FormEvent, useState } from "react";
import { api } from "../../services/api";
import type { Novel, Project } from "../../types";

interface Props {
  onClose: () => void;
  onCreated: (project: Project) => Promise<void>;
}

export default function CreateProjectDialog({ onClose, onCreated }: Props) {
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [synopsis, setSynopsis] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const project = await api<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({ name, description: synopsis }),
      });
      await api<Novel>("/novels", {
        method: "POST",
        body: JSON.stringify({
          project_id: project.id,
          title: title || name,
          synopsis,
          story_outline: "",
        }),
      });
      await onCreated(project);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/45 p-6" onMouseDown={onClose}>
      <form
        className="panel w-full max-w-xl p-7"
        onSubmit={submit}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="mb-6 flex items-start justify-between">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.22em] text-rust">New project</div>
            <h2 className="mt-1 font-serif text-3xl font-semibold">开始一本小说</h2>
            <p className="mt-2 text-sm text-black/50">先建一个轻量项目，故事总纲、人物和章节可以稍后逐步补齐。</p>
          </div>
          <button type="button" className="text-xl text-black/35 hover:text-black" onClick={onClose}>×</button>
        </div>
        {error && <div className="mb-4 rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</div>}
        <label className="label">项目名称</label>
        <input className="field mb-4" value={name} onChange={(event) => setName(event.target.value)} required autoFocus />
        <label className="label">小说标题</label>
        <input
          className="field mb-4"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="留空则使用项目名称"
        />
        <label className="label">一句话简介</label>
        <textarea className="field min-h-28" value={synopsis} onChange={(event) => setSynopsis(event.target.value)} />
        <div className="mt-6 flex justify-end gap-3">
          <button type="button" className="btn-soft" onClick={onClose}>取消</button>
          <button className="btn-primary" disabled={busy}>{busy ? "创建中..." : "创建并进入项目"}</button>
        </div>
      </form>
    </div>
  );
}
