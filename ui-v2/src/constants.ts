/** 中文文案常量（迁移自 novel/ui/static/app.js，保持一致）。 */

export const STAGE_NAMES: Record<string, string> = {
  strategist: "策略：生成故事概念",
  worldbuilder: "世界观构建中",
  character: "角色设计中",
  outliner: "大纲编排中",
  concept: "生成故事概念",
  world: "构建世界观",
  characters: "设计人物",
  outline: "编排大纲",
  resume: "从故事圣经恢复",
  writer: "正文写作中",
  writer_rewrite: "按评审意见重写中",
  scorer: "质量评分中",
  continuity: "连续性检查中",
  editor: "编辑润色中",
  extractor: "状态提取与回写中",
  rewriting: "改写稿生成中",
};

export const GATE_LABELS: Record<string, string> = {
  outline: "大纲已生成，是否批准？",
  chapter: "本章已完成，是否继续？",
  chapter_review_failed: "本章多次重写后仍未达标，是否强行放行？",
};

export const SETUP_STAGE_NAMES: Record<string, string> = {
  concept: "故事概念",
  world: "世界观",
  characters: "人物",
  outline: "大纲",
};

export const BIBLE_SECTION_NAMES: Record<string, string> = {
  concept: "概念",
  world: "世界观",
  characters: "人物",
  outline: "大纲",
  foreshadows: "伏笔",
  events: "事件",
};

export const REWRITE_MODE_NAMES: Record<string, string> = {
  polish: "微调",
  rearrange: "创意重编排",
};

/** API 路径构造。 */
export const p = (n: string): string => `/api/projects/${n}`;
