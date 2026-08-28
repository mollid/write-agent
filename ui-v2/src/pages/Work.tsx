import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { Button, Card, Empty, Input, List, Space, Tag, Typography } from "antd";
import { Link } from "react-router-dom";
import {
  useChatEntries,
  useChatSessions,
  useCreateChatSession,
  useSendChatMessage,
} from "../api/hooks";
import { CHAT_ACTION_LABELS } from "../constants";

/** Work 模式:计划驱动的对话编排。进度与门禁由 Shell 的 JobStrip/GateModal
 * 呈现(跨页复用),本页只负责会话与消息流。 */
export default function Work() {
  const { name = "" } = useParams();
  const [sid, setSid] = useState<string | null>(null);
  const [text, setText] = useState("");
  const sessions = useChatSessions(name);
  const createSession = useCreateChatSession(name);
  const entries = useChatEntries(name, sid);
  const send = useSendChatMessage(name, sid);

  useEffect(() => {
    if (!sid && (sessions.data?.length ?? 0) > 0) setSid(sessions.data![0].id);
  }, [sessions.data, sid]);

  const doSend = () => {
    const t = text.trim();
    if (!t || !sid || send.isPending) return;
    setText("");
    send.mutate(t);
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }} data-testid="page-work">
      <Typography.Title level={4} style={{ margin: 0 }}>
        对话(Work)
      </Typography.Title>
      <Card size="small" title="会话" extra={
        <Button size="small" loading={createSession.isPending}
                onClick={() => createSession.mutate(undefined, { onSuccess: (d) => setSid(d.session_id) })}>
          新建会话
        </Button>
      }>
        <List
          size="small"
          dataSource={sessions.data ?? []}
          rowKey={(s) => s.id}
          renderItem={(s) => (
            <List.Item style={{ cursor: "pointer", padding: "4px 8px",
                                background: s.id === sid ? "#f5f5f5" : undefined }}
              onClick={() => setSid(s.id)}>
              <Typography.Text ellipsis style={{ maxWidth: 240 }}>{s.title}</Typography.Text>
            </List.Item>
          )}
        />
      </Card>
      <Card size="small" title="消息">
        {sid == null ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="新建会话后开始对话" />
        ) : (
          <div style={{ maxHeight: "50vh", overflowY: "auto", padding: "0 4px" }}>
            <List
              size="small"
              dataSource={entries.data?.entries ?? []}
              rowKey={(e) => String(e.seq)}
              renderItem={(e) => {
                if (e.type === "user")
                  return <Typography.Paragraph style={{ textAlign: "right" }}>
                    <Typography.Text style={{ background: "#e6f4ff", padding: "4px 10px", borderRadius: 6 }}>
                      {e.text}
                    </Typography.Text>
                  </Typography.Paragraph>;
                if (e.type === "assistant")
                  return <Typography.Paragraph>{e.text}</Typography.Paragraph>;
                if (e.type === "action")
                  return <Card size="small" style={{ margin: "6px 0", background: "#fafafa" }}>
                    <Space wrap>
                      <Tag color="blue">{CHAT_ACTION_LABELS[e.action?.type ?? ""] ?? e.action?.type}</Tag>
                      <Typography.Text code>{JSON.stringify(e.action?.args ?? {})}</Typography.Text>
                      {e.job_id ? (
                        <Link to={`/p/${name}/generate`}>查看任务 →</Link>
                      ) : null}
                    </Space>
                  </Card>;
                return <Typography.Text type="secondary" style={{ fontSize: 12 }}>{e.text}</Typography.Text>;
              }}
            />
            {/* 最新一轮回复先从 mutation 结果渲染,避免等 refetch;当服务端
             * 会话记录(含该回复)刷新进来后自动隐藏,防止重复。 */}
            {send.data && !(entries.data?.entries ?? []).some(
              (e) => e.type === "assistant" && e.text === send.data!.reply,
            ) ? (
              <Typography.Paragraph>{send.data.reply}</Typography.Paragraph>
            ) : null}
          </div>
        )}
        <Space.Compact style={{ width: "100%", marginTop: 8 }}>
          <Input.TextArea
            data-testid="chat-input"
            autoSize={{ minRows: 1, maxRows: 4 }}
            value={text}
            placeholder={sid == null ? "先新建会话" : "例如:继续写 3 章 / 把第 2 章改得紧张一点"}
            disabled={sid == null}
            onChange={(e) => setText(e.target.value)}
            onPressEnter={(e) => { if (!e.shiftKey) { e.preventDefault(); doSend(); } }}
          />
          <Button type="primary" data-testid="chat-send"
                  loading={send.isPending} disabled={sid == null} onClick={doSend}>
            发送
          </Button>
        </Space.Compact>
      </Card>
    </Space>
  );
}
