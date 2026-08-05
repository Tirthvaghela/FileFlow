import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StatCard from "./StatCard.jsx";

function FakeIcon(props) {
  return <svg data-testid="fake-icon" {...props} />;
}

describe("StatCard", () => {
  it("renders the label and value", () => {
    render(<StatCard label="Files organized" value={238} />);
    expect(screen.getByText("Files organized")).toBeInTheDocument();
    expect(screen.getByText("238")).toBeInTheDocument();
  });

  it("renders no icon markup when no icon prop is passed", () => {
    render(<StatCard label="Files archived" value={12} />);
    expect(screen.queryByTestId("fake-icon")).not.toBeInTheDocument();
  });

  it("renders the given icon when one is passed", () => {
    render(<StatCard label="Files organized" value={238} icon={FakeIcon} />);
    expect(screen.getByTestId("fake-icon")).toBeInTheDocument();
  });

  it("omits the badge entirely when none is passed", () => {
    render(<StatCard label="Duplicates removed" value={9} />);
    // Dashboard relies on an absent badge meaning "not currently monitoring" --
    // it must not render a stray empty pill.
    expect(screen.queryByText(/live|paused/i)).not.toBeInTheDocument();
  });

  it("renders a badge when one is passed", () => {
    render(<StatCard label="Organized today" value={4} badge="live" />);
    expect(screen.getByText("live")).toBeInTheDocument();
  });
});
