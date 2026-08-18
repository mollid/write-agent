import { Alert, App as AntApp, Button, Card, Empty, Input, Menu, Segmented, Select, Slider, Space, Spin, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  useAudioList,
  useChapter,
  useChapterRewrite,
  useMode,
  useOutline,
  useResolveGate,
  useSaveChapter,
  useStatus,
  useTts,
} from "../api/hooks";
import { useEvents } from "../stores/events";
import { REWRITE_MODE_NAMES, TTS_VOICE_NAMES } from "../constants";

/** Task 8: chapter reader — left chapter list (outline titles), right prose at
 * a comfortable measure. F1: `?chapter=N` deep links from Generate preselect.
 * Below the prose: chapter rewrite (微调 / 创意重编排) with a diff proposal
 * panel approved via the rewrite:{N} gate, plus manual in-place editing. */
export default function Reader() {
  const { name = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: status } = useStatus(name);
  const { data: modeInfo } = useMode();
  const { data: outline } = useOutline(name);
  const [selected, setSelected] = useState<number | null>(null);
  const chapter = useChapter(name, selected);
  const job = useEvents((s) => s.job);
  const proposal = useEvents((s) => s.chapterProposal);
  const rewrite = useChapterRewrite(name);
  const resolve = useResolveGate(name);
  const saveChapter = useSaveChapter(name);
  const [mode, setMode] = useState<string>("polish");
  const [instruction, setInstruction] = useState("");
  const [feedback, setFeedback] = useState("");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  /** True from the moment the rewrite POST is accepted until its proposal
   * lands (or the job dies) — the model call in between can take a minute,
   * and without feedback the page reads as frozen. */
  const [rewritePending, setRewritePending] = useState(false);
  const lastEnd = useEvents((s) => s.lastEnd);
  const { message } = AntApp.useApp();

  // edge-tts: synthesis controls + pending feedback (mirrors the rewrite card)
  const audioList = useAudioList(name);
  const tts = useTts(name);
  // numeric slider values, serialized as edge-tts strings on request
  const [ttsVoice, setTtsVoice] = useState("zh-CN-XiaoxiaoNeural");
  const [ttsRate, setTtsRate] = useState(0);      // percent
  const [ttsVolume, setTtsVolume] = useState(0);  // percent
  const [ttsPitch, setTtsPitch] = useState(0);    // Hz
  const [ttsPending, setTtsPending] = useState(false);
  const ttsDone = useEvents((s) => s.ttsDone);

  const titles = useMemo(() => {
    const m = new Map<number, string>();
    for (const arc of outline?.arcs ?? [])
      for (const c of arc.chapters) m.set(c.chapter_no, c.chapter_title);
    return m;
  }, [outline]);
  const chapters = status?.chapters ?? [];

  // F1: honor the ?chapter=N deep link once, then clear it (replace, not push)
  // so the browser back button returns to the referring page, not a re-select.
  const param = searchParams.get("chapter");
  useEffect(() => {
    if (param == null) return;
    const n = Number(param);
    if (Number.isInteger(n) && n > 0) setSelected(n);
    setSearchParams({}, { replace: true });
  }, [param, setSearchParams]);

  // default to the first chapter once the list is known
  useEffect(() => {
    if (selected == null && chapters.length > 0) setSelected(chapters[0]);
  }, [selected, chapters]);

  // switching chapters abandons any in-progress manual edit (draft belongs to
  // the old chapter)
  useEffect(() => {
    setEditing(false);
  }, [selected]);

  // the awaited proposal arrived — stop the pending indicator (match chapter:
  // a stale proposal from another chapter must not clear it prematurely)
  useEffect(() => {
    if (proposal != null && selected != null && proposal.chapter === selected)
      setRewritePending(false);
  }, [proposal, selected]);

  // job died (done/error/cancelled) before a proposal landed — stop spinning
  const endSeq = lastEnd?.seq ?? 0;
  useEffect(() => {
    if (endSeq > 0) setRewritePending(false);
  }, [endSeq]);

  // refill persisted TTS params once per project
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(`tts-params:${name}`);
      if (raw) {
        const v = JSON.parse(raw) as { voice: string; rate: number; volume: number; pitch: number };
        setTtsVoice(v.voice); setTtsRate(v.rate); setTtsVolume(v.volume); setTtsPitch(v.pitch);
      }
    } catch { /* ignore corrupt entries */ }
  }, [name]);

  // tts_done for our chapter ends the pending state (audio for the chapter
  // appearing in /audio — reload or the SSE invalidation — also ends it)
  useEffect(() => {
    if (ttsDone != null && ttsDone.chapter === selected) setTtsPending(false);
  }, [ttsDone, selected]);
  useEffect(() => {
    if (audioList.data?.some((a) => a.chapter === selected)) setTtsPending(false);
  }, [audioList.data, selected]);
  useEffect(() => {
    if ((lastEnd?.seq ?? 0) > 0) setTtsPending(false);
  }, [lastEnd?.seq]);

  const hasLaterChapters = selected != null && chapters.some((c) => c > selected);

  function startEditing() {
    if (chapter.data) setDraft(chapter.data.content);
    setEditing(true);
  }

  function saveEdit() {
    if (selected == null) return;
    saveChapter.mutate(
      { chapter: selected, content: draft },
      {
        onSuccess: () => {
          setEditing(false);
          message.success("已保存，旧稿已自动备份");
        },
        onError: (e) => message.error(String(e)),
      },
    );
  }

  function startRewrite() {
    if (selected == null) return;
    if (!instruction.trim()) {
      message.warning("请先填写改写指令");
      return;
    }
    setFeedback("");
    setRewritePending(true);
    rewrite.mutate(
      { chapter: selected, mode, instruction: instruction.trim() },
      {
        onSuccess: () => message.info("已开始改写，改写稿生成后将在下方展示"),
        onError: (e) => {
          setRewritePending(false);
          message.error(String(e));
        },
      },
    );
  }

  function startTts() {
    if (selected == null) return;
    const pct = (v: number) => `${v >= 0 ? "+" : ""}${v}%`;
    const hz = (v: number) => `${v >= 0 ? "+" : ""}${v}Hz`;
    window.localStorage.setItem(
      `tts-params:${name}`,
      JSON.stringify({ voice: ttsVoice, rate: ttsRate, volume: ttsVolume, pitch: ttsPitch }));
    setTtsPending(true);
    tts.mutate(
      { chapter: selected, voice: ttsVoice, rate: pct(ttsRate), volume: pct(ttsVolume), pitch: hz(ttsPitch) },
      {
        onSuccess: () => message.info("已开始合成，完成后可在此试听"),
        onError: (e) => { setTtsPending(false); message.error(String(e)); },
      },
    );
  }

  async function resolveProposal(approve: boolean, fb = "") {
    if (!proposal) return;
    if (!approve && !fb.trim()) {
      message.warning("请填写修改意见，或点击「应用改写」/「放弃」");
      return;
    }
    try {
      await resolve.mutateAsync({ id: proposal.gateId, approve, feedback: fb });
      if (!approve && fb.trim()) setFeedback("");
    } catch (e) {
      message.error(String(e));
    }
  }

  return (
    <div data-testid="page-reader" style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
      <Card size="small" title="章节目录" style={{ minWidth: 230 }}>
        {chapters.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚无章节">
            <Link to={`/p/${name}/generate`}>去生成</Link>
          </Empty>
        ) : (
          <Menu
            mode="inline"
            style={{ borderInlineEnd: 0 }}
            selectedKeys={selected != null ? [String(selected)] : []}
            items={chapters.map((c) => ({
              key: String(c),
              label: `${String(c).padStart(3, "0")} · ${titles.get(c) ?? "（无标题）"}`,
            }))}
            onSelect={({ key }) => setSelected(Number(key))}
          />
        )}
      </Card>
      <Space direction="vertical" size="middle" style={{ flex: 1, minWidth: 0 }}>
        <Card
          size="small"
          extra={
            !editing && chapter.data && selected != null ? (
              <Button size="small" data-testid="edit-chapter" disabled={!!job} onClick={startEditing}>
                编辑
              </Button>
            ) : undefined
          }
          title={
            selected != null
              ? `第 ${selected} 章 · ${titles.get(selected) ?? "（无标题）"}`
              : "正文"
          }
        >
          {editing ? (
            <Space direction="vertical" size="small" style={{ width: "100%" }}>
              <Input.TextArea
                data-testid="edit-area"
                rows={16}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
              <Space>
                <Button
                  type="primary"
                  data-testid="edit-save"
                  loading={saveChapter.isPending}
                  disabled={!!job}
                  onClick={saveEdit}
                >
                  保存（旧稿自动备份）
                </Button>
                <Button data-testid="edit-cancel" onClick={() => setEditing(false)}>
                  取消
                </Button>
              </Space>
            </Space>
          ) : chapter.data ? (
            <Typography.Paragraph
              data-testid="reader-prose"
              style={{ maxWidth: "72ch", lineHeight: 1.8, whiteSpace: "pre-wrap", marginBottom: 0 }}
            >
              {chapter.data.content}
            </Typography.Paragraph>
          ) : chapter.isError ? (
            <Typography.Text type="danger">章节内容加载失败</Typography.Text>
          ) : selected != null ? (
            <Typography.Text type="secondary">加载中…</Typography.Text>
          ) : (
            <Typography.Text type="secondary">从左侧选择一章开始阅读</Typography.Text>
          )}
        </Card>
        {proposal && (
          <Card
            size="small"
            data-testid="rewrite-proposal"
            title={`第 ${proposal.chapter} 章改写提案${
              proposal.mode ? ` · ${REWRITE_MODE_NAMES[proposal.mode] ?? proposal.mode}` : ""
            }`}
          >
            {proposal.diff ? (
              <pre
                data-testid="rewrite-diff"
                style={{ whiteSpace: "pre-wrap", maxHeight: "50vh", overflow: "auto",
                         fontSize: 12, lineHeight: 1.6, marginTop: 0 }}
              >
                {proposal.diff}
              </pre>
            ) : (
              <Typography.Text type="secondary">
                （差异不可用——重连恢复的提案，下方为改写稿全文）
              </Typography.Text>
            )}
            <Input.TextArea
              data-testid="rewrite-feedback"
              rows={2}
              style={{ marginTop: 8 }}
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="修改意见（自然语言）：不满意可带意见重新改写…"
            />
            <Space style={{ marginTop: 8 }}>
              <Button
                type="primary"
                data-testid="rewrite-approve"
                disabled={!proposal.gateId}
                onClick={() => resolveProposal(true)}
              >
                应用改写
              </Button>
              <Button
                data-testid="rewrite-reject"
                disabled={!proposal.gateId}
                onClick={() => resolveProposal(false, feedback)}
              >
                带反馈再改
              </Button>
              <Button
                data-testid="rewrite-abandon"
                disabled={!proposal.gateId}
                onClick={() => resolveProposal(false)}
              >
                放弃
              </Button>
            </Space>
          </Card>
        )}
        {chapters.length > 0 && (
          <Card size="small" title="章节改写" data-testid="rewrite-card">
            {hasLaterChapters && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 8 }}
                message="本章之后已有后续章节：重写本章可能与后续内容衔接不畅"
              />
            )}
            {rewritePending && (
              <Alert
                data-testid="rewrite-pending"
                type="info"
                showIcon
                icon={<Spin size="small" />}
                style={{ marginBottom: 8 }}
                message="正在生成改写稿…（真实模型模式下约需数十秒到一分钟，可在顶部任务条查看进度或取消）"
              />
            )}
            <Space direction="vertical" size="small" style={{ width: "100%" }}>
              <Segmented
                data-testid="rewrite-mode"
                value={mode}
                onChange={(v) => setMode(v as string)}
                options={Object.entries(REWRITE_MODE_NAMES).map(([value, label]) => ({
                  value,
                  label,
                }))}
              />
              <Input.TextArea
                data-testid="rewrite-instruction"
                rows={2}
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                disabled={rewritePending}
                placeholder={
                  mode === "polish"
                    ? "微调指令，例如：把结尾的对白改短，语气更克制"
                    : "重编排指令，例如：把酒馆冲突提前开场，回忆改为插叙"
                }
              />
              <Button
                type="primary"
                data-testid="rewrite-start"
                disabled={selected == null || !!job}
                loading={rewrite.isPending || rewritePending}
                onClick={startRewrite}
              >
                开始改写
              </Button>
            </Space>
          </Card>
        )}
        {chapters.length > 0 && (
          <Card size="small" title="语音合成" data-testid="tts-card">
            {modeInfo && !modeInfo.live && (
              <Alert
                type="info"
                showIcon
                data-testid="tts-demo-notice"
                message="演示模式：生成的是占位静音音频"
                style={{ marginBottom: 8 }}
              />
            )}
            <Space direction="vertical" size="small" style={{ width: "100%" }}>
              <div data-testid="tts-voice">
                <Select
                  style={{ minWidth: 220 }}
                  value={ttsVoice}
                  onChange={setTtsVoice}
                  disabled={ttsPending}
                  options={Object.entries(TTS_VOICE_NAMES).map(([value, label]) => ({ value, label }))}
                />
              </div>
              <div data-testid="tts-rate">
                <Typography.Text data-testid="tts-rate-label" type="secondary">
                  {`语速 ${ttsRate >= 0 ? "+" : ""}${ttsRate}%`}
                </Typography.Text>
                <Slider min={-50} max={100} step={5} value={ttsRate}
                        onChange={(v) => setTtsRate(v as number)} disabled={ttsPending} />
              </div>
              <div data-testid="tts-volume">
                <Typography.Text data-testid="tts-volume-label" type="secondary">
                  {`音量 ${ttsVolume >= 0 ? "+" : ""}${ttsVolume}%`}
                </Typography.Text>
                <Slider min={-50} max={100} step={5} value={ttsVolume}
                        onChange={(v) => setTtsVolume(v as number)} disabled={ttsPending} />
              </div>
              <div data-testid="tts-pitch">
                <Typography.Text data-testid="tts-pitch-label" type="secondary">
                  {`音调 ${ttsPitch >= 0 ? "+" : ""}${ttsPitch}Hz`}
                </Typography.Text>
                <Slider min={-50} max={50} step={5} value={ttsPitch}
                        onChange={(v) => setTtsPitch(v as number)} disabled={ttsPending} />
              </div>
              {ttsPending && (
                <Alert data-testid="tts-pending" type="info" showIcon icon={<Spin size="small" />}
                       message="正在合成语音…" />
              )}
              <Space>
                <Button type="primary" data-testid="tts-generate"
                        disabled={selected == null || !!job || ttsPending}
                        loading={tts.isPending || ttsPending} onClick={startTts}>
                  生成语音
                </Button>
                <Button data-testid="tts-reset" disabled={ttsPending}
                        onClick={() => { setTtsVoice("zh-CN-XiaoxiaoNeural"); setTtsRate(0); setTtsVolume(0); setTtsPitch(0); }}>
                  重置默认
                </Button>
              </Space>
              {(() => {
                const hit = audioList.data?.find((a) => a.chapter === selected);
                return hit ? (
                  <Space direction="vertical" size={0} style={{ width: "100%" }}>
                    <audio data-testid="tts-player" controls preload="none"
                           style={{ width: "100%" }}
                           src={`/api/projects/${name}/audio/${hit.chapter}`} />
                    <a href={`/api/projects/${name}/audio/${hit.chapter}`}
                       download={`${String(hit.chapter).padStart(3, "0")}.mp3`}>
                      下载 MP3（{(hit.size / 1024).toFixed(0)} KB）
                    </a>
                  </Space>
                ) : null;
              })()}
            </Space>
          </Card>
        )}
      </Space>
    </div>
  );
}
