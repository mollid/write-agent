import { useQueryClient } from "@tanstack/react-query";
import { App as AntApp, Alert, Button, Card, InputNumber, Progress, Space, Tag, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { pageTitle } from "../theme";
import {
  useCancelJob,
  useMode,
  useOutline,
  useProjectConfig,
  useStatus,
  useUpdateProjectConfig,
  useWriteChapters,
} from "../api/hooks";
import { useEvents } from "../stores/events";
import { STAGE_NAMES } from "../constants";

/** Task 7: resume-aware chapter generation with live progress, event log and
 * cancel. Cross-page affordances (JobStrip, GateModal) live in the shell. */
export default function Generate() {
  const { name = "" } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { message } = AntApp.useApp();
  const { data: status } = useStatus(name);
  const { data: outline } = useOutline(name);
  const { data: mode } = useMode();
  const job = useEvents((s) => s.job);
  const progress = useEvents((s) => s.progress);
  const lastStage = useEvents((s) => s.lastStage);
  const lines = useEvents((s) => s.lines);
  const lastEnd = useEvents((s) => s.lastEnd);
  const lastStart = useEvents((s) => s.lastChapterStart);
  const write = useWriteChapters(name);
  const cancel = useCancelJob(name);
  const { data: config } = useProjectConfig(name);
  const saveConfig = useUpdateProjectConfig(name);
  const [n, setN] = useState(1);
  const [target, setTarget] = useState<number | null>(null);
  const targetLoaded = useRef(false);
  useEffect(() => {
    if (!targetLoaded.current && config) {
      targetLoaded.current = true;
      setTarget(config.target_chapters);
    }
  }, [config]);

  async function saveTarget() {
    try {
      await saveConfig.mutateAsync({ target_chapters: target });
      message.success(
        target ? `已保存：全书计划 ${target} 章` : "已清除全书章数（回到短篇一次性大纲）",
      );
    } catch (e) {
      message.error(String(e instanceof Error ? e.message : e));
    }
  }

  const existing = status?.chapters.length ?? 0;
  const titles = new Map<number, string>();
  for (const arc of outline?.arcs ?? [])
    for (const c of arc.chapters) titles.set(c.chapter_no, c.chapter_title);

  async function start() {
    try {
      await write.mutateAsync({ n });
      // progress total set here; done increments on chapter_done AND
      // chapter_skipped (N4) via the store's apply.
      useEvents.setState({ progress: { done: 0, total: n } });
      message.info(`已开始生成 ${n} 章`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        // R6 CTA: the conflicting job may have been started from Setup/elsewhere.
        // We are already on the Generate page — pulse the JobStrip instead of a
        // no-op navigation (F2).
        message.open({
          type: "error",
          content: (
            <span>
              {e.message}{" "}
              <Button type="link" size="small" onClick={() => useEvents.getState().pulseStrip()}>
                查看运行中任务
              </Button>
            </span>
          ),
        });
      } else {
        message.error(String(e instanceof Error ? e.message : e));
      }
    }
  }

  // job_end → final toast + refresh facts (the job may have started elsewhere).
  // Seed the dedup seq with any lastEnd that predates this mount — otherwise
  // every visit (sidebar re-navigation) replays the previous job's toast.
  const endSeq = useRef(lastEnd?.seq ?? 0);
  useEffect(() => {
    if (!lastEnd || lastEnd.seq === endSeq.current) return;
    endSeq.current = lastEnd.seq;
    if (lastEnd.status === "done") message.success("任务完成");
    else if (lastEnd.status === "cancelled") message.info("任务已取消");
    else message.error(`任务失败：${lastEnd.error ?? "未知错误"}`);
    for (const key of [["status"], ["reviews", name], ["outline", name], ["chapters", name], ["projects"]]) {
      void qc.invalidateQueries({ queryKey: key });
    }
  }, [lastEnd, message, qc, name]);

  // auto-scroll the log to the bottom unless the user hovers it
  const [hover, setHover] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!hover && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [lines, hover]);

  const percent =
    progress && progress.total > 0
      ? Math.min(100, Math.round((progress.done / progress.total) * 100))
      : 0;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }} data-testid="page-generate">
      <Typography.Title level={4} style={pageTitle}>
        生成章节
      </Typography.Title>

      {/* F3: honest demo notice — same as Setup, persistent while on the page */}
      {mode && !mode.live && (
        <Alert
          type="info"
          showIcon
          data-testid="demo-notice"
          message="演示模式：反馈不会改变生成内容"
        />
      )}

      <Card size="small" title="开始 / 续写">
        <Typography.Paragraph data-testid="resume-text">
          已有 {existing} 章；本次将生成 {n} 章（含自动跳过的已完成章节）
        </Typography.Paragraph>
        <Space wrap>
          <InputNumber
            min={1}
            max={2000}
            value={n}
            onChange={(v) => setN(v ?? 1)}
            data-testid="n-input"
          />
          <Button type="primary" data-testid="start-generate" loading={write.isPending} onClick={start}>
            开始生成
          </Button>
          <Button
            danger
            data-testid="cancel-job"
            disabled={!job}
            loading={cancel.isPending}
            onClick={() => job && cancel.mutate(job.id)}
          >
            取消任务
          </Button>
        </Space>
      </Card>

      <Card size="small" title="长篇设置">
        <Space wrap>
          <InputNumber
            min={1}
            max={5000}
            value={target ?? undefined}
            onChange={(v) => setTarget(v ?? null)}
            data-testid="target-chapters-input"
            placeholder="留空 = 短篇一次性大纲"
          />
          <Button
            data-testid="save-target-chapters"
            loading={saveConfig.isPending}
            onClick={saveTarget}
          >
            保存全书章数
          </Button>
        </Space>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 8 }}>
          填写后大纲走两段式：先生成全书卷骨架、只细化第一卷，写作中自动逐卷细化。请在生成大纲之前设置。
        </Typography.Paragraph>
      </Card>

      {progress || lastStage ? (
        <Card size="small" title="进度">
          {progress ? (
            <Progress percent={percent} format={() => `${progress.done}/${progress.total}`} />
          ) : null}
          {lastStage ? (
            <Typography.Text type="secondary">
              当前阶段：{STAGE_NAMES[lastStage] ?? lastStage}
            </Typography.Text>
          ) : null}
          {lastStart?.plannedTotal ? (
            <Typography.Text data-testid="book-progress">
              全书进度：第 {lastStart.chapter} / 共 {lastStart.plannedTotal} 章
            </Typography.Text>
          ) : null}
        </Card>
      ) : null}

      <Card
        size="small"
        title="事件日志"
        extra={<Typography.Text type="secondary">悬停暂停自动滚动</Typography.Text>}
      >
        <div
          data-testid="event-log"
          ref={logRef}
          onMouseEnter={() => setHover(true)}
          onMouseLeave={() => setHover(false)}
          style={{ maxHeight: 260, overflowY: "auto", fontFamily: "monospace", fontSize: 12 }}
        >
          {lines.length === 0 ? (
            <Typography.Text type="secondary">
              暂无事件——开始生成后这里会显示实时日志
            </Typography.Text>
          ) : (
            lines.map((l, i) => (
              <div key={i}>
                <Typography.Text type="secondary">{l.time} </Typography.Text>
                <span>{l.text}</span>
              </div>
            ))
          )}
        </div>
      </Card>

      <Card size="small" title="已生成章节">
        {existing === 0 ? (
          <Typography.Text type="secondary">还没有章节——完成设定后开始生成</Typography.Text>
        ) : (
          <Space wrap>
            {(status?.chapters ?? []).map((c) => (
              <Tag
                key={c}
                style={{ cursor: "pointer" }}
                data-testid={`chapter-chip-${c}`}
                onClick={() => navigate(`/p/${name}/reader?chapter=${c}`)}
              >
                {String(c).padStart(3, "0")} · {titles.get(c) ?? "（无标题）"}
              </Tag>
            ))}
          </Space>
        )}
      </Card>
      <Typography.Text type="secondary">项目：{name}</Typography.Text>
    </Space>
  );
}
