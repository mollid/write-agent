import { App as AntApp, Alert, Button, Input, List, Modal, Space, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useEvents } from "../stores/events";
import { useResolveGate } from "../api/hooks";
import { GATE_LABELS, SETUP_STAGE_NAMES } from "../constants";

/** R4: global approval modal. Setup gates carry a feedback box; the
 * force-pass gate requires an explicit second confirmation step. */
export default function GateModal({ project }: { project: string }) {
  const gate = useEvents((s) => s.gate);
  const feedbackHistory = useEvents((s) => s.feedbackHistory);
  const pushFeedback = useEvents((s) => s.pushFeedback);
  const resolve = useResolveGate();
  const [feedback, setFeedback] = useState("");
  const [confirmForce, setConfirmForce] = useState(false);
  const openerRef = useRef<HTMLElement | null>(null);
  const { message } = AntApp.useApp();

  useEffect(() => {
    if (gate) {
      openerRef.current = document.activeElement as HTMLElement | null;
      setFeedback("");
      setConfirmForce(false);
    } else if (openerRef.current) {
      // R6: return focus to the element that had it when the modal opened
      openerRef.current.focus();
      openerRef.current = null;
    }
  }, [gate]);

  if (!gate) return null;
  const isSetup = gate.label.startsWith("setup:");
  const isForce = gate.label === "chapter_review_failed";
  const title = isSetup
    ? `设定阶段：${SETUP_STAGE_NAMES[gate.label.slice(6)] ?? gate.label.slice(6)} — 通过还是修改？`
    : (GATE_LABELS[gate.label] ?? gate.label);

  async function submit(approve: boolean, fb = "") {
    if (!approve && isSetup && !fb.trim()) {
      message.warning("请填写修改意见，或点击「通过」");
      return;
    }
    if (approve && isForce && !confirmForce) {
      setConfirmForce(true);
      return;
    }
    try {
      if (!approve && fb.trim()) pushFeedback(fb.trim());
      await resolve.mutateAsync({ id: gate!.id, approve, feedback: fb });
    } catch (e) {
      message.error(String(e));
    }
  }

  return (
    <Modal
      open
      title={title}
      closable={false}
      footer={null}
      width={720}
      data-testid="gate-modal"
      aria-live="polite"
    >
      {gate.artifact ? (
        <pre data-testid="gate-artifact" style={{ whiteSpace: "pre-wrap", maxHeight: 320, overflow: "auto" }}>
          {gate.artifact.slice(0, 4000)}
        </pre>
      ) : (
        <Typography.Text type="secondary">（产物内容不可用——重连恢复的审批）</Typography.Text>
      )}
      {gate.label === "chapter" && (
        <Typography.Paragraph>
          <Link to={`/p/${project}/reader`}>查看本章</Link>
        </Typography.Paragraph>
      )}
      {isSetup && (
        <>
          {feedbackHistory.length > 0 && (
            <List
              size="small"
              header={<Typography.Text type="secondary">已提交的反馈</Typography.Text>}
              dataSource={feedbackHistory}
              renderItem={(item) => <List.Item style={{ padding: "4px 0" }}>{item}</List.Item>}
            />
          )}
          <Input.TextArea
            data-testid="gate-feedback"
            rows={3}
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="修改意见（自然语言），系统会带着意见重新生成该阶段…"
          />
        </>
      )}
      {isForce && confirmForce && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 8 }}
          message="强行放行不可撤销：该章将以未达标状态保存。确认放行？"
        />
      )}
      <Space style={{ marginTop: 12 }}>
        <Button type="primary" data-testid="gate-approve" onClick={() => submit(true)}>
          {isForce && confirmForce ? "确认强行放行" : "通过"}
        </Button>
        <Button
          data-testid="gate-reject"
          danger={isForce && confirmForce}
          onClick={() => submit(false, feedback)}
        >
          {isSetup ? "带反馈重生成" : isForce ? "放行前再想想（取消）" : "拒绝"}
        </Button>
      </Space>
    </Modal>
  );
}
