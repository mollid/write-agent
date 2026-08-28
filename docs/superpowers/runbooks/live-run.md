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
2. 两段式大纲：运行 `write-chapter`（其内部 setup 会先由卷规划器生成全书卷骨架，再按卷生成明细）；引导式 `setup`（CLI 或界面「分阶段设定」）同样读取 `target_chapters`，且大纲阶段的反馈会喂给卷骨架规划器。
3. 试跑第一卷：`NOVEL_LIVE=1 uv run novel write-chapter 20`。

检查项：

- 跨章一致性：前卷事件、角色状态、伏笔回收在续卷上下文里是否保持。
- `chapters/_summaries/` 下每章摘要质量：150–250 字，覆盖情节、角色、状态。
- 卷完结时 `.meta/summaries.json` 已生成（卷摘要 + 全书摘要）。
- `arc_cast` 人工门出现在**每卷明细生成之前**（该卷有新角色建议时）：审批阵容规划器提议的 0–5 名新登场角色，可「通过」采用、「带反馈重拟」（≤3 轮）或留空拒绝（本卷不新增）；通过后新角色先入库，再进入卷细化。把关点：新角色是否与本卷 premise 强相关、动机是否与前卷剧情挂钩、有没有重复的旧角色。
- `arc_detail` 人工门出现在**每卷明细生成之后**：审批的是已细化的卷（章 + 节拍），可「通过」、「带反馈重细化」（反馈进入 detailer，每卷最多 3 轮）或留空拒绝（骨架回队列，本次运行不再细化该卷）。重点把关卷长是否明显低于骨架规划。