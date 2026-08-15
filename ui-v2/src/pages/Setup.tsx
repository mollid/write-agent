import { useParams } from "react-router-dom";

export default function Setup() {
  const { name = "" } = useParams();
  return <div data-testid="page-setup">{name}</div>;
}
