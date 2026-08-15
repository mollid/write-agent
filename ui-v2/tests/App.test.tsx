import { render, screen } from "@testing-library/react";
import App from "../src/App";

test("app shell renders", () => {
  render(<App />);
  expect(screen.getByTestId("app-shell")).toBeInTheDocument();
});
