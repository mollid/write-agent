import { Card, Empty, Menu, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useChapter, useOutline, useStatus } from "../api/hooks";

/** Task 8: chapter reader — left chapter list (outline titles), right prose at
 * a comfortable measure. F1: `?chapter=N` deep links from Generate preselect. */
export default function Reader() {
  const { name = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: status } = useStatus(name);
  const { data: outline } = useOutline(name);
  const [selected, setSelected] = useState<number | null>(null);
  const chapter = useChapter(name, selected);

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
      <Card
        size="small"
        style={{ flex: 1, minWidth: 0 }}
        title={
          selected != null
            ? `第 ${selected} 章 · ${titles.get(selected) ?? "（无标题）"}`
            : "正文"
        }
      >
        {chapter.data ? (
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
    </div>
  );
}
