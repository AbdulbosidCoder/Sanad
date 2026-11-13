import { render, screen } from "@testing-library/react";

import { Button, ErrorNotice } from "./index";
import { colors } from "./tokens";

describe("design system", () => {
  it("primary color is forest-800", () => {
    expect(colors.forest[800]).toBe("#124929");
  });

  it("button is a real button with type=button by default", () => {
    render(<Button>Купить</Button>);
    expect(screen.getByRole("button", { name: "Купить" })).toHaveProperty("type", "button");
  });

  it("error notice shows code, module and request id", () => {
    render(
      <ErrorNotice
        locale="ru"
        error={{ code: "ORDERS.OUT_OF_STOCK", module: "orders", requestId: "abc123" }}
      />,
    );
    const text = screen.getByRole("alert").textContent ?? "";
    expect(text).toContain("ORDERS.OUT_OF_STOCK");
    expect(text).toContain("orders");
    expect(text).toContain("abc123");
  });
});
