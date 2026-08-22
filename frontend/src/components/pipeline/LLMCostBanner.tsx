/* LLMCostBanner.tsx — 简要 LLM 调用提示（可关闭） */
import { X } from "lucide-react";
import { useState } from "react";

interface Props {
  llmConfigured: boolean;
  structurizeEstimate: string | null;
}

export function LLMCostBanner({ llmConfigured, structurizeEstimate }: Props) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  return (
    <div className="llm-banner">
      <span className="dot status-warn" />
      <span>
        {llmConfigured
          ? `②–⑤ 调用 LLM${structurizeEstimate ? `，${structurizeEstimate}` : ""}`
          : "未配置 OPENAI_API_KEY，LLM 不可用"}
      </span>
      <button className="btn btn-icon" onClick={() => setDismissed(true)} aria-label="关闭提示" title="关闭提示">
        <X size={14} />
      </button>
    </div>
  );
}
