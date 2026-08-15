import { useParams } from "react-router-dom";

export default function Export() {
  const { name = "" } = useParams();
  return <div data-testid="page-export">{name}</div>;
}
