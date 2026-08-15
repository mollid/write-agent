import { useParams } from "react-router-dom";

export default function Generate() {
  const { name = "" } = useParams();
  return <div data-testid="page-generate">{name}</div>;
}
