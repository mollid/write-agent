import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { App as AntApp, Button, Card, Empty, Input, List, Space, Tag, Typography } from "antd";
import { Link } from "react-router-dom";
import {
  useChatEntries,
  useChatSessions,
  useCreateChatSession,
  useSendChatMessage,
} from "../api/hooks";
import { CHAT_ACTION_LABELS } from "../constants";
import { pageTitle } from "../theme";

/** Work 模式:计划驱动的对话编排。进度与门禁由 Shell 的 JobStrip/GateModal
 * 呈现(跨页复用),本页只负责会话与消息流。 */
export default function Work() {
  const { name = "" } = useParams();
  const [sid, setSid] = useState<string | null>(null);
  const [text, setText] = useState("");
  /** 最新一轮回复,标记它属于哪个会话:只在对应会话渲染,服务端会话记录
   * (已含该回复)刷新进来后自动隐藏,防止重复。 */
  const [pendingReply, setPendingReply] = useState<{ sid: string; reply: string } | null>(null);
  /** 乐观 user 气泡(spec §4.5):发送瞬间渲染,服务端记录(已含该消息)刷新进来后隐藏。 */
  const [pendingUser, setPendingUser] = useState<{ sid: string; text: string } | null>(null);
  const { message } = AntApp.useApp();
  const sessions = useChatSessions(name);
  const createSession = useCreateChatSession(name);
  const entries = useChatEntries(name, sid);
  const send = useSendChatMessage(name, sid);

  useEffect(() => {
    if (!sid && (sessions.data?.length ?? 0) > 0) setSid(sessions.data![0].id);
  }, [sessions.data, sid]);

  // 切换会话时丢弃旧会话的待同步条目
  useEffect(() => {
    setPendingReply(null);
    setPendingUser(null);
  }, [sid]);

  // 当前会话的服务端条目已包含该回复 → 不再单独渲染
  useEffect(() => {
    if (
      pendingReply &&
      pendingReply.sid === sid &&
      (entries.data?.entries ?? []).some(
        (e) => e.type === "assistant" && e.text === pendingReply.reply,
      )
    )
      setPendingReply(null);
  }, [entries.data, pendingReply, sid]);

  // 当前会话的服务端条目已包含该用户消息 → 不再单独渲染
  useEffect(() => {
    if (
      pendingUser &&
      pendingUser.sid === sid &&
      (entries.data?.entries ?? []).some((e) => e.type === "user" && e.text === pendingUser.text)
    )
      setPendingUser(null);
  }, [entries.data, pendingUser, sid]);

  const errMsg = (e: unknown) => String(e instanceof Error ? e.message : e);

  const doSend = () => {
    const t = text.trim();
    if (!t || !sid || send.isPending) return;
    setText("");
    // 用发送时捕获的 sid 标记乐观气泡归属,防止串到别的会话
    setPendingUser({ sid, text: t });
    send.mutate(t, {
      // 用发送时捕获的 sid 标记回复归属,防止串到别的会话
      onSuccess: (d) => setPendingReply({ sid, reply: d.reply }),
      onError: (e) => {
        setPendingUser(null);
        setText(t); // 发送失败:还原输入,用户的文字不丢
        message.error(`发送失败：${errMsg(e)}`);
      },
    });
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }} data-testid="page-work">
      <Typography.Title level={4} style={pageTitle}>
        对话(Work)
      </Typography.Title>
      <Card size="small" title="会话" extra={
        <Button size="small" loading={createSession.isPending}
                onClick={() => createSession.mutate(undefined, {
                  onSuccess: (d) => setSid(d.session_id),
                  onError: (e) => message.error(`新建会话失败：${errMsg(e)}`),
                })}>
          新建会话
        </Button>
      }>
        <List
          size="small"
          dataSource={sessions.data ?? []}
          rowKey={(s) => s.id}
          renderItem={(s) => (
            <List.Item style={{ cursor: "pointer", padding: "4px 8px",
                                background: s.id === sid ? "#FAFAFA" : undefined }}
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
                    <Typography.Text style={{ background: "#F1E4FB", padding: "4px 10px", borderRadius: 6 }}>
                      {e.text}
                    </Typography.Text>
                  </Typography.Paragraph>;
                if (e.type === "assistant")
                  return <Typography.Paragraph>{e.text}</Typography.Paragraph>;
                if (e.type === "action")
                  return <Card size="small" style={{ margin: "6px 0", background: "#FAFAFA" }}>
                    <Space wrap>
                      <Tag color="#8848F9">{CHAT_ACTION_LABELS[e.action?.type ?? ""] ?? e.action?.type}</Tag>
                      <Typography.Text code>{JSON.stringify(e.action?.args ?? {})}</Typography.Text>
                      {e.job_id ? (
                        <Link to={`/p/${name}/generate`}>查看任务 →</Link>
                      ) : null}
                    </Space>
                  </Card>;
                return <Typography.Text type="secondary" style={{ fontSize: 12 }}>{e.text}</Typography.Text>;
              }}
            />
            {pendingUser && pendingUser.sid === sid ? (
              <Typography.Paragraph style={{ textAlign: "right" }}>
                <Typography.Text style={{ background: "#F1E4FB", padding: "4px 10px", borderRadius: 6 }}>
                  {pendingUser.text}
                </Typography.Text>
              </Typography.Paragraph>
            ) : null}
            {pendingReply && pendingReply.sid === sid ? (
              <Typography.Paragraph>{pendingReply.reply}</Typography.Paragraph>
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
