/* PaperList.tsx — 论文列表（单行条目：状态点 + 标题 + 大小） */
import type { Paper } from "../../types";

interface Props {
  papers: Paper[];
  selectedId: string | null;
  onSelect: (paper: Paper) => void;
}

export function PaperList({ papers, selectedId, onSelect }: Props) {
  return (
    <div className="paper-list-body">
      {papers.length === 0 && (
        <div className="paper-empty">尚未上传论文。点击右上角上传图标开始。</div>
      )}
      {papers.map((p) => (
        <PaperItem key={p.id} paper={p} selected={p.id === selectedId} onSelect={onSelect} />
      ))}
    </div>
  );
}

function PaperItem({
  paper,
  selected,
  onSelect,
}: {
  paper: Paper;
  selected: boolean;
  onSelect: (p: Paper) => void;
}) {
  const sizeKb = Math.round(paper.text_size / 1024);
  const meta = [paper.year, paper.first_author].filter(Boolean).join(" · ");
  return (
    <button
      className={`paper-item${selected ? " selected" : ""}`}
      onClick={() => onSelect(paper)}
      title={`${paper.title || paper.id}\n${meta}${meta ? " · " : ""}${sizeKb} KB`}
    >
      <span className="paper-item-dot" />
      <span className="paper-item-title">{paper.title || paper.id}</span>
      <span className="paper-item-meta mono">{sizeKb} KB</span>
    </button>
  );
}
