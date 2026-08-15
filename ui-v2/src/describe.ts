import type { SseEvent } from "./api/types";
import { STAGE_NAMES } from "./constants";

/** Human-readable Chinese log line for an SSE event (copy migrated from the
 * legacy novel/ui/static/app.js handler). Returns null for silent types —
 * callers skip pushing those lines. */
export function describe(ev: SseEvent): string | null {
  const s = (k: string): string => (ev[k] == null ? "" : String(ev[k]));
  const stageName = (x: string): string => STAGE_NAMES[x] ?? x;
  switch (ev.type) {
    case "stage":
      return ev.chapter
        ? `第 ${ev.chapter} 章 · ${stageName(String(ev.stage))}`
        : `${stageName(String(ev.stage))}…`;
    case "chapter_start":
      return `▶ 开始第 ${ev.chapter} 章${ev.title ? `「${ev.title}」` : ""}`;
    case "review":
      return `  评审：总分 ${ev.overall}（第 ${ev.attempt} 次尝试）${ev.passed ? "✅ 通过" : "❌ 未达标"}`;
    case "chapter_done":
      return `✔ 第 ${ev.chapter} 章完成并已保存`;
    case "chapter_skipped":
      return `✖ 第 ${ev.chapter} 章被跳过：${s("reason")}`;
    case "premise_done":
      return `✔ 故事概念已生成（genre=${s("genre")}）`;
    case "setup_stage":
      if (ev.skipped && ev.reason === "aborted")
        return `设定阶段 ${ev.stage} 未通过，设定已停止（已通过的阶段已保留）`;
      if (ev.skipped) return `设定阶段 ${ev.stage} 已通过，跳过`;
      return `设定阶段 ${ev.stage}：第 ${ev.attempt} 次生成（见审批卡片）`;
    case "gate":
      return `⚠ 等待审批：${s("label")}`;
    case "job_end":
      if (ev.status === "done") return "✅ 任务完成";
      if (ev.status === "cancelled") return "任务已取消";
      return `❌ 任务失败：${s("error")}`;
    default:
      return null;
  }
}
