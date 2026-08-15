import { useParams } from "react-router-dom";

export default function Reviews() {
  const { name = "" } = useParams();
  return <div data-testid="page-reviews">{name}</div>;
}
