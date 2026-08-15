import { useParams } from "react-router-dom";

export default function Threads() {
  const { name = "" } = useParams();
  return <div data-testid="page-threads">{name}</div>;
}
