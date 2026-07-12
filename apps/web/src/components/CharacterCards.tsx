import { FormEvent, useEffect, useState } from "react";
import { api, parseJson } from "../services/api";
import type { Character } from "../types";

interface Props {
  novelId: string;
}

const emptyForm = {
  name: "",
  role: "",
  description: "",
  personality: "",
  goals: "",
  arc: "",
  currentState: "{}",
  relationships: "{}",
  notes: "",
};

export default function CharacterCards({ novelId }: Props) {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [message, setMessage] = useState("");

  async function load() {
    const data = await api<Character[]>(`/novels/${novelId}/characters`);
    setCharacters(data);
  }

  useEffect(() => {
    void load();
  }, [novelId]);

  function select(character: Character) {
    setSelectedId(character.id);
    setForm({
      name: character.name,
      role: character.role,
      description: character.description,
      personality: character.personality,
      goals: character.goals,
      arc: character.arc,
      currentState: character.current_state_json,
      relationships: character.relationships_json,
      notes: character.notes,
    });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    const body = {
      novel_id: novelId,
      name: form.name,
      role: form.role,
      description: form.description,
      personality: form.personality,
      goals: form.goals,
      arc: form.arc,
      current_state: parseJson(form.currentState, {}),
      relationships: parseJson(form.relationships, {}),
      notes: form.notes,
    };
    if (selectedId) {
      await api<Character>(`/characters/${selectedId}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
    } else {
      await api<Character>("/characters", { method: "POST", body: JSON.stringify(body) });
    }
    setMessage("已保存");
    setSelectedId(null);
    setForm(emptyForm);
    await load();
  }

  async function remove() {
    if (!selectedId || !window.confirm("删除这张角色卡？")) return;
    await api<void>(`/characters/${selectedId}`, { method: "DELETE" });
    setSelectedId(null);
    setForm(emptyForm);
    await load();
  }

  return (
    <main className="mx-auto grid max-w-7xl grid-cols-[0.75fr_1.25fr] gap-6 p-7">
      <section className="panel p-5">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="font-serif text-2xl font-semibold">角色卡</h2>
          <button
            className="btn-soft"
            onClick={() => {
              setSelectedId(null);
              setForm(emptyForm);
            }}
          >
            + 新角色
          </button>
        </div>
        <div className="space-y-2">
          {characters.map((character) => (
            <button
              key={character.id}
              className={`w-full rounded-xl border p-3 text-left ${
                selectedId === character.id ? "border-moss bg-moss/5" : "border-black/10 bg-white/50"
              }`}
              onClick={() => select(character)}
            >
              <div className="font-semibold">{character.name}</div>
              <div className="text-xs text-black/45">{character.role || "未标注角色"}</div>
            </button>
          ))}
        </div>
      </section>

      <form className="panel p-6" onSubmit={save}>
        <div className="mb-5 flex items-center justify-between">
          <h2 className="font-serif text-2xl font-semibold">{selectedId ? "编辑角色" : "新建角色"}</h2>
          {message && <span className="text-sm text-moss">{message}</span>}
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div><label className="label">姓名</label><input className="field" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
          <div><label className="label">角色定位</label><input className="field" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} /></div>
          <div className="col-span-2"><label className="label">人物描述</label><textarea className="field min-h-24" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
          <div><label className="label">性格</label><textarea className="field min-h-24" value={form.personality} onChange={(e) => setForm({ ...form, personality: e.target.value })} /></div>
          <div><label className="label">目标</label><textarea className="field min-h-24" value={form.goals} onChange={(e) => setForm({ ...form, goals: e.target.value })} /></div>
          <div className="col-span-2"><label className="label">人物弧光</label><textarea className="field min-h-20" value={form.arc} onChange={(e) => setForm({ ...form, arc: e.target.value })} /></div>
          <div><label className="label">当前状态 JSON</label><textarea className="field min-h-32 font-mono text-xs" value={form.currentState} onChange={(e) => setForm({ ...form, currentState: e.target.value })} /></div>
          <div><label className="label">关系备注 JSON</label><textarea className="field min-h-32 font-mono text-xs" value={form.relationships} onChange={(e) => setForm({ ...form, relationships: e.target.value })} /></div>
          <div className="col-span-2"><label className="label">备注</label><textarea className="field min-h-20" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
        </div>
        <div className="mt-5 flex justify-between">
          <button type="button" className="btn-soft text-red-700" disabled={!selectedId} onClick={() => void remove()}>删除</button>
          <button className="btn-primary">保存角色卡</button>
        </div>
      </form>
    </main>
  );
}
