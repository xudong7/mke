/* PaperList.tsx — 左侧论文列表（只显示已上传的 PDF）+ 上传按钮 */
import { useRef } from "react";
import type { Paper } from "../../types";
import { uploadPdf } from "../../api/client";

interface Props {
  papers: Paper[];
  selectedId: string | null;
  onSelect: (paper: Paper) => void;
  onUploaded: () => void;
}

export function PaperList({ papers, selectedId, onSelect, onUploaded }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);

  const handleUpload = async (file: File) => {
    try {
      await uploadPdf(file);
      onUploaded();
    } catch (e) {
      alert(`上传失败：${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <div className="paper-list">
      <div className="paper-list-header">
        <span className="paper-list-title">已上传论文</span>
        <button className="btn btn-sm" onClick={() => fileRef.current?.click()}>
          上传 PDF
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf"
          style={{ display: "none" }}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void handleUpload(f);
            e.target.value = "";
          }}
        />
      </div>
      <div className="paper-list-body">
        {papers.length === 0 && (
          <div className="paper-empty">尚未上传论文。点击「上传 PDF」开始。</div>
        )}
        {papers.map((p) => (
          <PaperItem key={p.id} paper={p} selected={p.id === selectedId} onSelect={onSelect} />
        ))}
      </div>
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
  return (
    <button
      className={`paper-item${selected ? " selected" : ""}`}
      onClick={() => onSelect(paper)}
      title={paper.id}
    >
      <div className="paper-item-meta mono">
        {paper.year || "—"} · 上传
      </div>
      <div className="paper-item-title">{paper.title || paper.id}</div>
      <div className="paper-item-sub mono">
        {paper.first_author} · {sizeKb} KB
      </div>
    </button>
  );
}
