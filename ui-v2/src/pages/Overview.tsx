import { Button, Card, Col, Row, Space, Tag, Typography } from "antd";
import { Link, useParams } from "react-router-dom";
import { useStatus } from "../api/hooks";
import { pageTitle } from "../theme";

const JOB_KINDS: Record<string, string> = {
  premise: "创意生成",
  setup: "分阶段设定",
  "write-chapter": "章节生成",
};

/** Task 9: project overview — setup/chapters/threads/job status cards, with a
 * hero CTA to Setup when no concept exists yet (R1). */
export default function Overview() {
  const { name = "" } = useParams();
  const { data: status } = useStatus(name);

  if (!status) {
    return (
      <Card size="small" data-testid="page-overview">
        <Typography.Text type="secondary">加载中…</Typography.Text>
      </Card>
    );
  }

  // tolerate partial status payloads (e.g. loading stubs) — never crash on render
  const chapters = status.chapters ?? [];
  const openThreads = status.open_threads ?? 0;
  const job = status.job ?? null;
  const latest = chapters.length ? Math.max(...chapters) : null;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }} data-testid="page-overview">
      <Typography.Title level={4} style={pageTitle}>
        概览 · {name}
      </Typography.Title>

      {!status.has_concept && (
        <Card data-testid="overview-cta">
          <Space wrap>
            <Typography.Text strong>还没有故事概念——从一个创意开始整部小说</Typography.Text>
            <Link to={`/p/${name}/setup`}>
              <Button type="primary" data-testid="overview-cta-button">
                从一句创意开始 →
              </Button>
            </Link>
          </Space>
        </Card>
      )}

      <Row gutter={[16, 16]} data-testid="overview-stats">
        <Col xs={24} md={12} lg={6}>
          <Card size="small" title="设定">
            <Space wrap>
              <Tag color={status.has_concept ? "success" : "default"}>
                {status.has_concept ? "✓ 概念已生成" : "概念未生成"}
              </Tag>
              <Tag color={status.has_world ? "success" : "default"}>
                {status.has_world ? "✓ 世界观已构建" : "世界观未构建"}
              </Tag>
              <Tag color={status.has_outline ? "success" : "default"}>
                {status.has_outline ? "✓ 大纲已编排" : "大纲未编排"}
              </Tag>
            </Space>
            <Typography.Paragraph style={{ marginTop: 8, marginBottom: 0 }}>
              <Link to={`/p/${name}/setup`}>前往设定</Link>
            </Typography.Paragraph>
          </Card>
        </Col>
        <Col xs={24} md={12} lg={6}>
          <Card size="small" title="章节">
            {chapters.length === 0 ? (
              <Typography.Text type="secondary">
                还没有章节——完成设定后
                <Link to={`/p/${name}/generate`}>开始生成</Link>
              </Typography.Text>
            ) : (
              <Space direction="vertical">
                <Typography.Text>
                  共 {chapters.length} 章
                </Typography.Text>
                <Link to={`/p/${name}/reader?chapter=${latest}`}>最新章节：第 {latest} 章</Link>
              </Space>
            )}
          </Card>
        </Col>
        <Col xs={24} md={12} lg={6}>
          <Card size="small" title="未闭合伏笔">
            <Typography.Text>{openThreads} 条未闭合</Typography.Text>
            <Typography.Paragraph style={{ marginTop: 8, marginBottom: 0 }}>
              <Link to={`/p/${name}/threads`}>查看伏笔台账</Link>
            </Typography.Paragraph>
          </Card>
        </Col>
        <Col xs={24} md={12} lg={6}>
          <Card size="small" title="运行中任务">
            {job ? (
              <Space direction="vertical">
                <Typography.Text>{JOB_KINDS[job.kind] ?? job.kind}</Typography.Text>
                <Tag color={job.status === "running" ? "processing" : "default"}>
                  {job.status}
                </Tag>
                {job.error ? (
                  <Typography.Text type="danger">{job.error}</Typography.Text>
                ) : null}
              </Space>
            ) : (
              <Typography.Text type="secondary">当前没有运行中的任务</Typography.Text>
            )}
          </Card>
        </Col>
      </Row>
    </Space>
  );
}
