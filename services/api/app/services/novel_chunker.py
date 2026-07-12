"""把一部（可能很长的）参考小说切成适合单次模型抽取的块。

策略：优先按章节标题切（中文「第N章/回/节」或 Markdown 标题），其次按段落，
最后按字符窗口硬切；块之间带少量重叠（overlap）防止跨块语义断裂。
token 估算复用 context_builder.estimate_tokens（中文 1 字≈1 token）。
"""
import re
from typing import List

from app.services.context_builder import estimate_tokens


CHAPTER_RE = re.compile(
    r"(?m)^(?:\s*)(?:第[0-9零一二三四五六七八九十百千两]+[章回节卷部]|#{1,3}\s+\S)",
)


def _split_units(text: str) -> List[str]:
    """按章节标题切成单元；无标题则按空行段落切。"""
    starts = [m.start() for m in CHAPTER_RE.finditer(text)]
    if not starts:
        return [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    units = []
    if starts[0] > 0:
        head = text[: starts[0]]
        if head.strip():
            units.append(head)
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        unit = text[start:end]
        if unit.strip():
            units.append(unit)
    return units


def _split_long_unit(unit: str, max_tokens: int) -> List[str]:
    """单元仍超长：按段落贪心，过长段落再按字符窗口硬切。"""
    out: List[str] = []
    for para in re.split(r"\n\s*\n", unit):
        para = para.strip()
        if not para:
            continue
        if estimate_tokens(para) <= max_tokens:
            out.append(para)
            continue
        step = max(200, max_tokens)  # 中文近似：1 字 ≈ 1 token
        for i in range(0, len(para), step):
            piece = para[i : i + step].strip()
            if piece:
                out.append(piece)
    return out


def chunk_text(text: str, max_tokens: int = 2000, overlap: int = 120) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    if estimate_tokens(text) <= max_tokens:
        return [text]

    atoms: List[str] = []
    for unit in _split_units(text):
        if estimate_tokens(unit) <= max_tokens:
            atoms.append(unit.strip())
        else:
            atoms.extend(_split_long_unit(unit, max_tokens))

    chunks: List[str] = []
    current = ""
    for atom in atoms:
        if not atom:
            continue
        if current and estimate_tokens(current) + estimate_tokens(atom) > max_tokens:
            chunks.append(current)
            tail = current[-overlap:] if overlap > 0 else ""
            current = (tail + "\n\n" + atom) if tail else atom
        else:
            current = (current + "\n\n" + atom) if current else atom
    if current.strip():
        chunks.append(current)
    return chunks
