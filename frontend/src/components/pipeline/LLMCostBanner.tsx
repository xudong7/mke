/* LLMCostBanner.tsx — LLM 消耗提示条（可关闭）；步骤⑤ 时长预估 */
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
        ②–⑤ 步将调用大模型（LLM），消耗 API token 并可能耗时较长。
        {llmConfigured ? "" : " 当前未配置 OPENAI_API_KEY，LLM 步骤不可用。"}
        {structurizeEstimate && ` ${structurizeEstimate}。`}
      </span>
      <button className="btn btn-icon" onClick={() => setDismissed(true)} aria-label="关闭提示" title="关闭提示">
        <X size={14} />
      </button>
    </div>
  );
}
