import { FormEvent, useState } from "react";
import { api } from "../../services/api";
import type { StoryMapChapter } from "../../types";

export type EntityFormKind = "event" | "thread" | "foreshadow";

interface Props {
  kind: EntityFormKind;
  novelId: string;
  chapters: StoryMapChapter[];
  // 编辑模式：传入初值 + id 走 PATCH；否则 POST 新建。
  initial?: Record<string, unknown>;
  editId?: string;
  onDone: () => void;
  onCancel: () => void;
}

const KIND_LABEL: Record<EntityFormKind, string> = {
  event: "时间线事件",
  thread: "情节线",
  foreshadow: "伏笔",
};

const KIND_PATH: Record<EntityFormKind, string> = {
  event: "/timeline-events",
  thread: "/plot-threads",
  foreshadow: "/foreshadowing",
};

// 通用实体表单：新建走 POST /timeline-events|/plot-threads|/foreshadowing，
// 编辑走 PATCH /{path}/{id}。保存成功后 onDone（由调用方 refetch）。
export default function EntityForm({ kind, novelId, chapters, initial, editId, onDone, onCancel }: Props) {
  const [form, setForm] = useState<Record<string, string>>(() => ({
    title: String(initial?.title ?? ""),
    story_time: String(initial?.story_time ?? ""),
    story_order: initial?.story_order != null ? String(initial.story_order) : "",
    description: String(initial?.description ?? ""),
    chapter_id: String(initial?.chapter_id ?? ""),
    name: String(initial?.name ?? ""),
    status: String(initial?.status ?? "open"),
    resolution: String(initial?.resolution ?? ""),
    planted_chapter_id: String(initial?.planted_chapter_id ?? ""),
    resolved_chapter_id: String(initial?.resolved_chapter_id ?? ""),
    notes: String(initial?.notes ?? ""),
  }));
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  function set(key: string, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function buildBody(): Record<string, unknown> {
    if (kind === "event") {
      return {
        novel_id: novelId,
        title: form.title,
        story_time: form.story_time,
        story_order: form.story_order.trim() === "" ? null : Number(form.story_order),
        description: form.description,
        chapter_id: form.chapter_id || null,
      };
    }
    if (kind === "thread") {
      return {
        novel_id: novelId,
        name: form.name,
        description: form.description,
        status: form.status,
        resolution: form.resolution,
      };
    }
    return {
      novel_id: novelId,
      description: form.description,
      status: form.status,
      planted_chapter_id: form.planted_chapter_id || null,
      resolved_chapter_id: form.resolved_chapter_id || null,
      notes: form.notes,
    };
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      const body = buildBody();
      if (editId) {
        // PATCH：不带 novel_id
        const { novel_id: _omit, ...patch } = body;
        void _omit;
        await api(`${KIND_PATH[kind]}/${editId}`, { method: "PATCH", body: JSON.stringify(patch) });
      } else {
        await api(KIND_PATH[kind], { method: "POST", body: JSON.stringify(body) });
      }
      onDone();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "保存失败");
      setSaving(false);
    }
  }

  return (
    <form className="space-y-3" onSubmit={submit}>
      <h4 className="font-serif text-lg font-semibold">
        {editId ? "编辑" : "新建"}
        {KIND_LABEL[kind]}
      </h4>

      {kind === "event" && (
        <>
          <Field label="标题">
            <input className="field" value={form.title} onChange={(e) => set("title", e.target.value)} required />
          </Field>
          <Field label="故事内时间（自由文本）">
            <input className="field" value={form.story_time} onChange={(e) => set("story_time", e.target.value)} />
          </Field>
          <Field label="故事顺序（整数，可空）">
            <input className="field" type="number" value={form.story_order} onChange={(e) => set("story_order", e.target.value)} />
          </Field>
          <ChapterSelect label="锚定章节" chapters={chapters} value={form.chapter_id} onChange={(v) => set("chapter_id", v)} />
        </>
      )}

      {kind === "thread" && (
        <>
          <Field label="名称">
            <input className="field" value={form.name} onChange={(e) => set("name", e.target.value)} required />
          </Field>
          <StatusSelect value={form.status} onChange={(v) => set("status", v)} options={["open", "resolved"]} />
          <Field label="收束/解决说明">
            <input className="field" value={form.resolution} onChange={(e) => set("resolution", e.target.value)} />
          </Field>
        </>
      )}

      {kind === "foreshadow" && (
        <>
          <StatusSelect value={form.status} onChange={(v) => set("status", v)} options={["open", "resolved"]} />
          <ChapterSelect label="埋设章节" chapters={chapters} value={form.planted_chapter_id} onChange={(v) => set("planted_chapter_id", v)} />
          <ChapterSelect label="回收章节" chapters={chapters} value={form.resolved_chapter_id} onChange={(v) => set("resolved_chapter_id", v)} />
          <Field label="备注">
            <input className="field" value={form.notes} onChange={(e) => set("notes", e.target.value)} />
          </Field>
        </>
      )}

      <Field label="描述">
        <textarea className="field min-h-20" value={form.description} onChange={(e) => set("description", e.target.value)} />
      </Field>

      {message && <p className="text-xs text-rust">{message}</p>}
      <div className="flex justify-end gap-2 pt-1">
        <button type="button" className="btn-soft" onClick={onCancel}>
          取消
        </button>
        <button className="btn-primary" disabled={saving}>
          {saving ? "保存中…" : "保存"}
        </button>
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="label">{label}</label>
      {children}
    </div>
  );
}

function ChapterSelect({
  label,
  chapters,
  value,
  onChange,
}: {
  label: string;
  chapters: StoryMapChapter[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Field label={label}>
      <select className="field" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">（未锚定）</option>
        {chapters.map((c) => (
          <option key={c.id} value={c.id}>
            第{c.order_index}章 · {c.title}
          </option>
        ))}
      </select>
    </Field>
  );
}

function StatusSelect({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: string[] }) {
  const labels: Record<string, string> = { open: "开放/进行中", resolved: "已回收/已收束" };
  return (
    <Field label="状态">
      <select className="field" value={value} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o} value={o}>
            {labels[o] || o}
          </option>
        ))}
      </select>
    </Field>
  );
}
