/* TextViewer.tsx — content.md 文本预览（无原始 PDF 的论文用） */
export function TextViewer({ text }: { text: string }) {
  return (
    <div className="text-viewer">
      <div className="text-viewer-paper">
        <pre>{text}</pre>
      </div>
    </div>
  );
}
