import { Card, Collapse, Empty, Space, Tag, Typography } from "antd";
import { useParams } from "react-router-dom";
import { useReviews } from "../api/hooks";
import type { ReviewRecord } from "../api/types";
import { Trend, trendPoints } from "../components/Trend";

/** Group reviews by chapter; attempts in ascending attempt order. */
export function groupByChapter(records: ReviewRecord[]): [number, ReviewRecord[]][] {
  const map = new Map<number, ReviewRecord[]>();
  for (const r of records) {
    const list = map.get(r.chapter) ?? [];
    list.push(r);
    map.set(r.chapter, list);
  }
  return [...map.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([ch, list]) => [ch, list.sort((a, b) => a.attempt - b.attempt)]);
}

/** Task 8: score history — per-chapter collapse with attempts, plus an
 * inline-SVG trend of last-attempt overall per chapter (R5). */
export default function Reviews() {
  const { name = "" } = useParams();
  const { data: records = [], isFetched } = useReviews(name);
  const grouped = groupByChapter(records);

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }} data-testid="page-reviews">
      <Typography.Title level={4} style={{ margin: 0 }}>
        评分历史
      </Typography.Title>
      {isFetched && records.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无评分记录，生成章节后自动留档" />
      ) : (
        <>
          <Card size="small" title="各章总分趋势">
            <Trend points={trendPoints(records)} />
          </Card>
          <Collapse
            defaultActiveKey={grouped.map(([ch]) => String(ch))}
            items={grouped.map(([ch, attempts]) => {
              const final = attempts[attempts.length - 1];
              return {
                key: String(ch),
                // forceRender keeps attempt rows mounted (collapsed panels would
                // otherwise defer content until first expansion)
                forceRender: true,
                label: (
                  <Space wrap>
                    <Typography.Text strong>第 {ch} 章</Typography.Text>
                    <Tag color={final.passed ? "green" : "red"}>
                      最终 {final.overall} 分 {final.passed ? "✅" : "❌"}
                    </Tag>
                    <Tag>{attempts.length} 次评分</Tag>
                  </Space>
                ),
                children: (
                  <div>
                    {attempts.map((r) => (
                      <div
                        key={r.attempt}
                        data-testid={`review-attempt-${r.chapter}-${r.attempt}`}
                        style={{ marginBottom: 16 }}
                      >
                        <Space wrap>
                          <Typography.Text strong>第 {r.attempt} 次评分</Typography.Text>
                          <Typography.Text>总分 {r.overall} 分</Typography.Text>
                          <Typography.Text
                            type={r.passed ? "success" : "danger"}
                          >
                            {r.passed ? "通过 ✅" : "未通过 ❌"}
                          </Typography.Text>
                          <Typography.Text type="secondary">{r.timestamp}</Typography.Text>
                        </Space>
                        <Typography.Paragraph
                          type="secondary"
                          style={{ whiteSpace: "pre-wrap", marginBottom: 4 }}
                        >
                          {r.summary}
                        </Typography.Paragraph>
                        <Space wrap>
                          {Object.entries(r.scores).map(([dim, s]) => (
                            <Tag key={dim}>
                              {dim}：{s.score} 分
                            </Tag>
                          ))}
                        </Space>
                      </div>
                    ))}
                  </div>
                ),
              };
            })}
          />
        </>
      )}
      <Typography.Text type="secondary">项目：{name}</Typography.Text>
    </Space>
  );
}
