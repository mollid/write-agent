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
  arc_detail: "生成下一卷明细",
  arc_detail_retry: "按反馈重细化下一卷",
  arc_cast: "规划本卷新登场角色",
  arc_cast_retry: "按反馈重拟本卷角色",
  summary_backfill: "补生成上一章摘要",
  writer: "正文写作中",
  writer_rewrite: "按评审意见重写中",
  scorer: "质量评分中",
  continuity: "连续性检查中",
  editor: "编辑润色中",
  extractor: "状态提取与回写中",
  rewriting: "改写稿生成中",
  tts: "语音合成中",
};

export const GATE_LABELS: Record<string, string> = {
  outline: "大纲已生成，是否批准？",
  chapter: "本章已完成，是否继续？",
  chapter_review_failed: "本章多次重写后仍未达标，是否强行放行？",
  arc_detail: "下一卷明细已生成——通过、带反馈重细化，或拒绝（骨架回到队列）",
  arc_cast: "本卷新登场角色建议，是否采用？（留空拒绝 = 本卷不新增）",
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

/** edge-tts 预设音色表（与后端 novel/tts.py 的 TTS_VOICES 保持一致——两侧
 * 各自硬编码，测试各锁一份，改动需同步）。 */
export const TTS_VOICE_NAMES: Record<string, string> = {
  "zh-CN-XiaoxiaoNeural": "晓晓（女 · 温暖通用）",
  "zh-CN-XiaoyiNeural": "晓伊（女 · 活泼）",
  "zh-CN-XiaochenNeural": "晓辰（女 · 知性）",
  "zh-CN-XiaomengNeural": "晓梦（女 · 温柔）",
  "zh-CN-XiaoqiuNeural": "晓秋（女 · 文艺）",
  "zh-CN-YunxiNeural": "云希（男 · 阳光）",
  "zh-CN-YunjianNeural": "云健（男 · 浑厚）",
  "zh-CN-YunyangNeural": "云扬（男 · 新闻）",
  "zh-CN-YunyeNeural": "云野（男 · 成熟）",
  "zh-CN-YunxiaNeural": "云夏（男 · 少年）",
};

/** Work 模式聊天里 action 卡片的动作中文名（与后端 chat 路由的动作枚举对应）。 */
export const CHAT_ACTION_LABELS: Record<string, string> = {
  write_premise: "生成故事前提",
  run_setup: "分阶段设定",
  write_chapters: "撰写章节",
  rewrite_chapter: "改写章节",
  edit_bible: "编辑设定",
  extend_outline: "扩展大纲",
  run_tts: "语音合成",
  wait_job: "等待任务",
  none: "无动作",
};

/** API 路径构造。 */
export const p = (n: string): string => `/api/projects/${n}`;
