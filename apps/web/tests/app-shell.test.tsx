import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppShell } from "@/components/layout/app-shell";

describe("AppShell", () => {
  it("renders the application identity and children", () => {
    render(
      <AppShell>
        <div>content</div>
      </AppShell>,
    );

    expect(screen.getByText("Hunar Hiring Assistant")).toBeInTheDocument();
    expect(screen.getByText("content")).toBeInTheDocument();
  });
});
