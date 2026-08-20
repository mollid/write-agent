# Live-LLM end-to-end run

Set API keys in env, then:

    NOVEL_LIVE=1 uv run novel init demo --genre fantasy
    cd demo
    NOVEL_LIVE=1 uv run novel premise "a thief who steals time"
    NOVEL_LIVE=1 uv run novel write-chapter 3
    uv run novel export

`write-chapter` takes the chapter count as a positional argument (`write-chapter 3`).
Re-running `write-chapter N` continues from the last written chapter instead of overwriting.

This exercises real models (configured in project.config.yaml). Not run in CI.
When `NOVEL_LIVE=1`, chapter/outline gates prompt for approval interactively.
For a no-LLM smoke run, omit `NOVEL_LIVE=1` (demo mode uses canned responses).

## 长篇试跑一卷

验证长文（10 卷 +）能力。以目标全书 240 章为例：

1. 在 `project.config.yaml` 的 `generation` 段配置 `target_chapters: 240`（可配 `chapter_target_length` 与 `arc_detail_lookahead`）。
2. 两段式大纲：先由 setup 生成全书卷骨架，再按卷生成明细。
3. 试跑第一卷：`NOVEL_LIVE=1 uv run novel write-chapter 20`。

检查项：

- 跨章一致性：前卷事件、角色状态、伏笔回收在续卷上下文里是否保持。
- `chapters/_summaries/` 下每章摘要质量：150–250 字，覆盖情节、角色、状态。
- 卷完结时 `.meta/summaries.json` 已生成（卷摘要 + 全书摘要）。
- `arc_detail` 人工门只在该卷明细生成阶段出现，其余阶段不打扰。