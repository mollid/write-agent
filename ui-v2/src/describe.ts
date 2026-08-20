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
    case "review": {
      const base = `  评审：总分 ${ev.overall}（第 ${ev.attempt} 次尝试）`;
      if (ev.passed) return `${base}✅ 通过`;
      // pass rule = every dimension >= score_min; list the weak dimensions so
      // 总分 82 + ❌ never reads as a contradiction
      const min = Number(ev.score_min);
      const weak = Number.isFinite(min) && typeof ev.scores === "object" && ev.scores !== null
        ? Object.entries(ev.scores as Record<string, unknown>)
            .filter(([, v]) => Number(v) < min)
            .map(([dim, v]) => `${dim} ${v}`)
        : [];
      return weak.length
        ? `${base}❌ 未达标：${weak.join("、")}（每项需 ≥${min}）`
        : `${base}❌ 未达标`;
    }
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
    case "bible_proposal":
      return "设定改写稿已生成，等待确认";
    case "bible_applied":
      return "设定改写已应用";
    case "bible_chat_done":
      return ev.applied ? "对话改写结束（已应用）" : "对话改写结束（未应用）";
    case "outline_extend_proposal":
      return "大纲追章方案已生成，等待确认";
    case "outline_extended":
      return `大纲已追加 ${ev.added} 章`;
    case "chapter_proposal":
      return `第 ${ev.chapter} 章改写稿已生成，等待确认`;
    case "rewrite_applied":
      return `✔ 第 ${ev.chapter} 章已按改写稿更新（旧稿已备份）`;
    case "rewrite_done":
      return ev.applied ? "章节改写完成" : "章节改写未应用";
    case "tts_done":
      return `✔ 第 ${ev.chapter} 章语音已生成`;
    case "warning":
      return ev.warning === "chapter_edited"
        ? `⚠ 第 ${ev.chapter} 章正文与摘要记录不一致（手动修改？）——状态未自动重算`
        : `⚠ ${s("warning")}`;
    case "arc_detailed":
      return `📖 卷「${s("arc")}」明细已生成（${s("chapters")} 章）`;
    case "arc_summary_done":
      return `📘 卷「${s("arc")}」摘要与全书梗概已更新`;
    case "job_end":
      if (ev.status === "done") return "✅ 任务完成";
      if (ev.status === "cancelled") return "任务已取消";
      return `❌ 任务失败：${s("error")}`;
    default:
      return null;
  }
}
