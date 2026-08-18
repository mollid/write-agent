import { useEvents } from "../src/stores/events";
import { describe as describeEvent } from "../src/describe";

describe("event store", () => {
  beforeEach(() => useEvents.getState().reset());

  test("gate event sets current gate; job_end clears it", () => {
    useEvents
      .getState()
      .apply({ type: "gate", gate_id: "g1", label: "setup:concept", artifact: "{}", job_id: "j1" });
    expect(useEvents.getState().gate?.id).toBe("g1");
    useEvents.getState().apply({ type: "job_end", job_id: "j1" });
    expect(useEvents.getState().gate).toBeNull();
    expect(useEvents.getState().job).toBeNull();
  });

  test("chapter_done increments progress", () => {
    useEvents.getState().apply({ type: "chapter_start", job_id: "j1" });
    // progress initialized by Generate page; simulate:
    useEvents.setState({ progress: { done: 0, total: 3 } });
    useEvents.getState().apply({ type: "chapter_done", chapter: 1, job_id: "j1" });
    expect(useEvents.getState().progress).toEqual({ done: 1, total: 3 });
  });

  test("log lines capped at 500", () => {
    for (let i = 0; i < 520; i++) useEvents.getState().pushLine(`l${i}`);
    expect(useEvents.getState().lines.length).toBe(500);
    expect(useEvents.getState().lines[0].text).toBe("l20");
  });

  test("stage event records lastStage", () => {
    useEvents.getState().apply({ type: "stage", stage: "writer", chapter: 1, job_id: "j1" });
    expect(useEvents.getState().lastStage).toBe("writer");
  });

  test("resetTransient clears gate/job/progress but keeps lines", () => {
    useEvents
      .getState()
      .apply({ type: "gate", gate_id: "g1", label: "setup:concept", artifact: "{}", job_id: "j1" });
    useEvents.getState().pushLine("keep me");
    useEvents.getState().resetTransient();
    const s = useEvents.getState();
    expect(s.gate).toBeNull();
    expect(s.job).toBeNull();
    expect(s.progress).toBeNull();
    expect(s.lines.map((l) => l.text)).toEqual(["keep me"]);
  });

  test("feedback history: pushFeedback appends; setup_stage attempt 1 resets", () => {
    useEvents.getState().pushFeedback("节奏太快");
    useEvents.getState().pushFeedback("增加悬念");
    expect(useEvents.getState().feedbackHistory).toEqual(["节奏太快", "增加悬念"]);
    useEvents.getState().apply({ type: "setup_stage", stage: "world", attempt: 2, job_id: "j1" });
    expect(useEvents.getState().feedbackHistory).toEqual(["节奏太快", "增加悬念"]);
    useEvents.getState().apply({ type: "setup_stage", stage: "characters", attempt: 1, job_id: "j1" });
    expect(useEvents.getState().feedbackHistory).toEqual([]);
  });

  test("setup_stage with artifact stores setupArtifact (N3); artifact-less events keep it", () => {
    useEvents.getState().apply({
      type: "setup_stage", stage: "concept", attempt: 1,
      artifact: '{"logline": "…"}', job_id: "j1",
    });
    expect(useEvents.getState().setupArtifact).toEqual({
      stage: "concept", attempt: 1, artifact: '{"logline": "…"}',
    });
    // skipped / aborted summary events carry no artifact — don't clobber it
    useEvents.getState().apply({
      type: "setup_stage", stage: "world", attempt: 0, skipped: true, job_id: "j1",
    });
    expect(useEvents.getState().setupArtifact?.stage).toBe("concept");
  });

  test("setupArtifact cleared by resetTransient (job death) and reset (N3)", () => {
    useEvents.getState().apply({
      type: "setup_stage", stage: "world", attempt: 2, artifact: "{}", job_id: "j1",
    });
    useEvents.getState().resetTransient();
    expect(useEvents.getState().setupArtifact).toBeNull();
    useEvents.getState().apply({
      type: "setup_stage", stage: "world", attempt: 2, artifact: "{}", job_id: "j1",
    });
    useEvents.getState().reset();
    expect(useEvents.getState().setupArtifact).toBeNull();
  });

  test("chapter_skipped also increments progress (N4)", () => {
    useEvents.setState({ progress: { done: 0, total: 3 } });
    useEvents.getState().apply({ type: "chapter_done", chapter: 4, job_id: "j1" });
    useEvents.getState().apply({
      type: "chapter_skipped", chapter: 5, reason: "already exists", job_id: "j1",
    });
    expect(useEvents.getState().progress).toEqual({ done: 2, total: 3 });
  });

  test("job_end records lastEnd with a fresh sequence and clears progress", () => {
    useEvents.setState({ progress: { done: 1, total: 3 } });
    useEvents.getState().apply({ type: "job_end", status: "done", job_id: "j1" });
    expect(useEvents.getState().lastEnd).toMatchObject({ status: "done", error: null, seq: 1 });
    expect(useEvents.getState().progress).toBeNull();
    useEvents.getState().apply({ type: "job_end", status: "error", error: "boom", job_id: "j2" });
    expect(useEvents.getState().lastEnd).toMatchObject({ status: "error", error: "boom", seq: 2 });
  });

  test("bible_proposal sets bibleProposal and gate id, not gate modal state", () => {
    const s = useEvents.getState();
    s.reset();
    s.apply({ type: "gate", gate_id: "g1", label: "bible:concept", artifact: "{}" });
    expect(useEvents.getState().gate).toBeNull();
    s.apply({ type: "bible_proposal", section: "concept", diff: "+x", draft: { a: 1 } });
    const st = useEvents.getState();
    expect(st.gate).toBeNull(); // bible: gates are handled in-page, not by GateModal
    expect(st.bibleProposal).toEqual({ section: "concept", diff: "+x", gateId: "", draft: { a: 1 } });
    s.apply({ type: "gate", gate_id: "g1", label: "bible:concept", artifact: "{}" });
    expect(useEvents.getState().gate).toBeNull();
    expect(useEvents.getState().bibleProposal?.gateId).toBe("g1");
  });

  test("bible_chat_done and job_end clear proposal", () => {
    const s = useEvents.getState();
    s.reset();
    s.apply({ type: "bible_proposal", section: "world", diff: "d", draft: {}, gate_id: "g" });
    s.apply({ type: "bible_chat_done", section: "world", applied: true });
    expect(useEvents.getState().bibleProposal).toBeNull();
    s.apply({ type: "outline_extend_proposal", added: 2, diff: "d", gate_id: "g2" });
    s.apply({ type: "job_end", status: "done", error: null, kind: "bible-chat" });
    expect(useEvents.getState().outlineProposal).toBeNull();
  });

  test("chapter_proposal → rewrite gate attaches id (never the global modal) → done clears", () => {
    const s = useEvents.getState();
    s.reset();
    s.apply({ type: "chapter_proposal", chapter: 3, mode: "polish", diff: "+d", draft: "p", job_id: "j" });
    expect(useEvents.getState().chapterProposal).toEqual({
      chapter: 3, mode: "polish", diff: "+d", draft: "p", gateId: "",
    });
    s.apply({ type: "gate", gate_id: "g9", label: "rewrite:3", artifact: "p", job_id: "j" });
    const st = useEvents.getState();
    expect(st.gate).toBeNull(); // rewrite gates render in the Reader panel only
    expect(st.chapterProposal?.gateId).toBe("g9");
    s.apply({ type: "rewrite_done", chapter: 3, applied: true, job_id: "j" });
    expect(useEvents.getState().chapterProposal).toBeNull();
  });

  test("a reconnected rewrite gate rebuilds the proposal from the artifact", () => {
    const s = useEvents.getState();
    s.reset();
    s.apply({ type: "gate", gate_id: "g7", label: "rewrite:5", artifact: "草稿全文", job_id: "j" });
    expect(useEvents.getState().chapterProposal).toEqual({
      chapter: 5, mode: "", diff: "", draft: "草稿全文", gateId: "g7",
    });
    expect(useEvents.getState().gate).toBeNull();
  });
});

describe("describe() log lines", () => {
  test("maps each event type to its Chinese log line; unknown types are silent", () => {
    expect(describeEvent({ type: "stage", stage: "writer", chapter: 3, job_id: "j" })).toBe(
      "第 3 章 · 正文写作中",
    );
    expect(describeEvent({ type: "stage", stage: "resume", job_id: "j" })).toBe("从故事圣经恢复…");
    expect(describeEvent({ type: "chapter_start", chapter: 1, title: "T1", job_id: "j" })).toBe(
      "▶ 开始第 1 章「T1」",
    );
    expect(
      describeEvent({ type: "review", chapter: 1, attempt: 2, overall: 88, passed: false, job_id: "j" }),
    ).toBe("  评审：总分 88（第 2 次尝试）❌ 未达标");
    // pass rule = every dimension >= score_min: a failed review lists the weak
    // dimensions so 总分 82 + ❌ never looks contradictory
    expect(
      describeEvent({
        type: "review", chapter: 1, attempt: 3, overall: 82, passed: false,
        scores: { prose: 76, continuity: 79, pacing: 90 }, score_min: 80, job_id: "j",
      }),
    ).toBe("  评审：总分 82（第 3 次尝试）❌ 未达标：prose 76、continuity 79（每项需 ≥80）");
    expect(
      describeEvent({
        type: "review", chapter: 1, attempt: 1, overall: 90, passed: true,
        scores: { prose: 90 }, score_min: 80, job_id: "j",
      }),
    ).toBe("  评审：总分 90（第 1 次尝试）✅ 通过");
    expect(describeEvent({ type: "chapter_done", chapter: 1, job_id: "j" })).toBe(
      "✔ 第 1 章完成并已保存",
    );
    expect(
      describeEvent({ type: "chapter_skipped", chapter: 2, reason: "already exists", job_id: "j" }),
    ).toBe("✖ 第 2 章被跳过：already exists");
    expect(describeEvent({ type: "premise_done", genre: "fantasy", job_id: "j" })).toBe(
      "✔ 故事概念已生成（genre=fantasy）",
    );
    expect(
      describeEvent({ type: "setup_stage", stage: "world", attempt: 1, job_id: "j" }),
    ).toBe("设定阶段 world：第 1 次生成（见审批卡片）");
    expect(
      describeEvent({ type: "setup_stage", stage: "world", skipped: true, job_id: "j" }),
    ).toBe("设定阶段 world 已通过，跳过");
    expect(describeEvent({ type: "gate", gate_id: "g", label: "chapter", job_id: "j" })).toBe(
      "⚠ 等待审批：chapter",
    );
    expect(describeEvent({ type: "outline_extend_proposal", added: 2, job_id: "j" })).toBe(
      "大纲追章方案已生成，等待确认",
    );
    expect(describeEvent({ type: "outline_extended", added: 2, job_id: "j" })).toBe(
      "大纲已追加 2 章",
    );
    expect(describeEvent({ type: "chapter_proposal", chapter: 3, mode: "polish", job_id: "j" })).toBe(
      "第 3 章改写稿已生成，等待确认",
    );
    expect(describeEvent({ type: "rewrite_applied", chapter: 3, job_id: "j" })).toBe(
      "✔ 第 3 章已按改写稿更新（旧稿已备份）",
    );
    expect(describeEvent({ type: "rewrite_done", chapter: 3, applied: false, job_id: "j" })).toBe(
      "章节改写未应用",
    );
    expect(describeEvent({ type: "job_end", status: "done", job_id: "j" })).toBe("✅ 任务完成");
    expect(describeEvent({ type: "job_end", status: "cancelled", job_id: "j" })).toBe("任务已取消");
    expect(describeEvent({ type: "job_end", status: "error", error: "boom", job_id: "j" })).toBe(
      "❌ 任务失败：boom",
    );
    expect(describeEvent({ type: "whatever", job_id: "j" })).toBeNull();
  });
});
