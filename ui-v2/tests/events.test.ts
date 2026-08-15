import { useEvents } from "../src/stores/events";

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

  test("feedback history: pushFeedback appends; setup_stage attempt 1 resets", () => {
    useEvents.getState().pushFeedback("节奏太快");
    useEvents.getState().pushFeedback("增加悬念");
    expect(useEvents.getState().feedbackHistory).toEqual(["节奏太快", "增加悬念"]);
    useEvents.getState().apply({ type: "setup_stage", stage: "world", attempt: 2, job_id: "j1" });
    expect(useEvents.getState().feedbackHistory).toEqual(["节奏太快", "增加悬念"]);
    useEvents.getState().apply({ type: "setup_stage", stage: "characters", attempt: 1, job_id: "j1" });
    expect(useEvents.getState().feedbackHistory).toEqual([]);
  });
});
