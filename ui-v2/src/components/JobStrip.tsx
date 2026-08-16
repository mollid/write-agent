import { Alert, Button, Space, Tag, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useEvents } from "../stores/events";
import { STAGE_NAMES } from "../constants";
import { useCancelJob } from "../api/hooks";

/** R2: persistent job strip — visible across all pages while a job runs. */
export default function JobStrip({ project }: { project: string }) {
  const job = useEvents((s) => s.job);
  const progress = useEvents((s) => s.progress);
  const gate = useEvents((s) => s.gate);
  const connected = useEvents((s) => s.connected);
  const lastStage = useEvents((s) => s.lastStage);
  const stripPulse = useEvents((s) => s.stripPulse);
  const dismissed = useEvents((s) => s.gateDismissed);
  const reopenGate = useEvents((s) => s.reopenGate);
  const navigate = useNavigate();
  const cancel = useCancelJob();

  // F2: when stripPulse bumps (Generate 409 CTA clicked), flash a highlight
  // for ~1.5s so the user's eye is drawn to the running-job strip.
  const [pulsing, setPulsing] = useState(false);
  const seenPulse = useRef<number | null>(null);
  useEffect(() => {
    if (seenPulse.current === null) {
      seenPulse.current = stripPulse;
      return;
    }
    if (stripPulse === seenPulse.current) return;
    seenPulse.current = stripPulse;
    setPulsing(true);
    const t = setTimeout(() => setPulsing(false), 1500);
    return () => clearTimeout(t);
  }, [stripPulse]);

  if (!job) return null;
  const stageText = lastStage ? (STAGE_NAMES[lastStage] ?? lastStage) : null;
  return (
    <Alert
      data-testid="job-strip"
      className={pulsing ? "job-strip-pulse" : undefined}
      type={gate ? "warning" : "info"}
      showIcon
      message={
        <Space wrap>
          <Typography.Text strong>{gate ? "等待审批" : "任务进行中"}</Typography.Text>
          {/* Visible live stage label (R6: map through STAGE_NAMES, raw fallback) */}
          {stageText ? (
            <Tag data-testid="job-stage">{stageText}</Tag>
          ) : null}
          {gate ? <Tag color="orange">{gate.label}</Tag> : null}
          {gate && dismissed ? (
            <Button size="small" type="primary" data-testid="reopen-gate" onClick={reopenGate}>
              打开审批
            </Button>
          ) : null}
          {progress && progress.total ? (
            <Tag>
              章节 {Math.min(progress.done, progress.total)}/{progress.total}
            </Tag>
          ) : null}
          {!connected && <Tag color="red">连接断开，重连中…</Tag>}
          <Button size="small" onClick={() => navigate(`/p/${project}/generate`)}>
            查看进度
          </Button>
          <Button size="small" danger onClick={() => cancel.mutate(job.id)}>
            取消任务
          </Button>
          {/* R6: separate polite live region announcing stage changes to screen readers */}
          <span
            aria-live="polite"
            style={{
              position: "absolute",
              width: 1,
              height: 1,
              overflow: "hidden",
              clip: "rect(0 0 0 0)",
              whiteSpace: "nowrap",
            }}
          >
            {stageText}
          </span>
        </Space>
      }
    />
  );
}
