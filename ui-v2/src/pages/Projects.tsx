import {
  App as AntApp,
  Button,
  Card,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Select,
  Space,
  Typography,
} from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useCreateProject, useProjects } from "../api/hooks";

const GENRES = [
  { value: "fantasy", label: "奇幻" },
  { value: "scifi", label: "科幻" },
  { value: "mystery", label: "悬疑" },
  { value: "romance", label: "言情" },
  { value: "historical", label: "历史" },
];

interface CreateValues {
  name: string;
  genre: string;
  targetChapters?: number;
}

/** Task 9: project list + create modal (name required ≤64, genre default fantasy). */
export default function Projects() {
  const navigate = useNavigate();
  const { data: projects = [], isFetched } = useProjects();
  const create = useCreateProject();
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<CreateValues>();
  const { message } = AntApp.useApp();

  async function submit(values: CreateValues) {
    try {
      await create.mutateAsync({
        name: values.name,
        genre: values.genre,
        // undefined is dropped by JSON.stringify → short-form projects stay clean
        target_chapters: values.targetChapters || undefined,
      });
      message.success(`项目 ${values.name} 已创建`);
      setOpen(false);
      form.resetFields();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409)
        message.error(`创建失败（冲突）：${e.message}`);
      else message.error(String(e instanceof Error ? e.message : e));
    }
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }} data-testid="page-projects">
      <Typography.Title level={4} style={{ margin: 0 }}>
        项目
      </Typography.Title>
      <Button type="primary" data-testid="new-project" onClick={() => setOpen(true)}>
        新建项目
      </Button>
      {isFetched && projects.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="还没有项目——新建一个，从一句创意开始你的小说"
        />
      ) : (
        <List
          grid={{ gutter: 16, column: 3 }}
          dataSource={projects}
          renderItem={(p) => (
            <List.Item>
              <Card
                size="small"
                title={p.name}
                extra={
                  <Button
                    type="primary"
                    data-testid={`enter-${p.name}`}
                    onClick={() => navigate(`/p/${p.name}/overview`)}
                  >
                    进入控制台
                  </Button>
                }
              >
                <Typography.Text type="secondary">点击进入控制台开始创作</Typography.Text>
              </Card>
            </List.Item>
          )}
        />
      )}
      <Modal
        open={open}
        title="新建项目"
        onCancel={() => setOpen(false)}
        footer={null}
        data-testid="create-project-modal"
      >
        <Form form={form} layout="vertical" initialValues={{ genre: "fantasy" }} onFinish={submit}>
          <Form.Item
            name="name"
            label="项目名"
            rules={[
              { required: true, message: "请输入项目名" },
              { max: 64, message: "项目名不超过 64 个字符" },
            ]}
          >
            <Input data-testid="project-name-input" placeholder="例如：clockwork-city" />
          </Form.Item>
          <Form.Item name="genre" label="类型" rules={[{ required: true, message: "请选择类型" }]}>
            <Select options={GENRES} />
          </Form.Item>
          <Form.Item
            name="targetChapters"
            label="计划全书章数"
            extra="长篇小说请填写（如 660）：启用两段式大纲——先出全书卷骨架，写作时逐卷细化。留空为短篇一次性大纲。"
          >
            <InputNumber
              min={1}
              max={5000}
              style={{ width: "100%" }}
              data-testid="project-target-input"
              placeholder="留空 = 短篇"
            />
          </Form.Item>
          <Space>
            <Button onClick={() => setOpen(false)}>取消</Button>
            <Button
              type="primary"
              htmlType="submit"
              data-testid="create-submit"
              loading={create.isPending}
            >
              创建
            </Button>
          </Space>
        </Form>
      </Modal>
    </Space>
  );
}
