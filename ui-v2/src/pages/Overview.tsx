import { useParams } from "react-router-dom";

export default function Overview() {
  const { name = "" } = useParams();
  return <div data-testid="page-overview">{name}</div>;
}
