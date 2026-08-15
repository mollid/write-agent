import { App as AntApp, Button, Card, Space, Typography } from "antd";
import { useParams } from "react-router-dom";
import { useExport } from "../api/hooks";

/** Task 8: export the assembled manuscript; show the result path copyable. */
export default function Export() {
  const { name = "" } = useParams();
  const { message } = AntApp.useApp();
  const exp = useExport(name);

  async function doExport() {
    try {
      await exp.mutateAsync();
      message.success("导出完成");
    } catch (e) {
      message.error(String(e instanceof Error ? e.message : e));
    }
  }

  return (
    <Card size="small" title="导出" data-testid="page-export">
      <Space direction="vertical">
        <Button type="primary" data-testid="export-button" loading={exp.isPending} onClick={doExport}>
          导出 Markdown
        </Button>
        {exp.data?.path && (
          <Typography.Text
            data-testid="export-path"
            copyable={{ text: exp.data.path, tooltips: ["复制路径", "已复制"] }}
          >
            路径：{exp.data.path}
          </Typography.Text>
        )}
        <Typography.Text type="secondary">导出文件位于项目目录</Typography.Text>
      </Space>
    </Card>
  );
}
