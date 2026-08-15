import { useParams } from "react-router-dom";

export default function Reader() {
  const { name = "" } = useParams();
  return <div data-testid="page-reader">{name}</div>;
}
