import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { CreateTaskInput } from "@/lib/api";
import { TaskCreationForm } from "@/components/TaskCreationForm";

function renderForm(onSubmit = vi.fn().mockResolvedValue(undefined)) {
  render(<TaskCreationForm onSubmit={onSubmit} />);
  return { onSubmit };
}

describe("TaskCreationForm", () => {
  it("blocks submission without a source or goal", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm();

    await user.click(screen.getByRole("button", { name: "Create task" }));

    expect(
      screen.getByText("Choose a Terraform repository ZIP file."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Describe the infrastructure goal for this task."),
    ).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("rejects a non-zip upload", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm();

    const input = screen.getByLabelText(/Terraform repository/i);
    const invalidFile = new File(["notes"], "notes.txt", { type: "text/plain" });
    Object.defineProperty(input, "files", { value: [invalidFile], configurable: true });
    fireEvent.change(input);

    await user.type(screen.getByLabelText(/Infrastructure goal/i), "Make the bucket private.");
    await user.click(screen.getByRole("button", { name: "Create task" }));

    expect(screen.getByText("The uploaded file must have a .zip extension.")).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("rejects an invalid git url", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm();

    await user.click(screen.getByRole("radio", { name: "Git URL" }));
    await user.type(screen.getByLabelText(/Public Git URL/i), "not a url");
    await user.type(screen.getByLabelText(/Infrastructure goal/i), "Make the bucket private.");
    await user.click(screen.getByRole("button", { name: "Create task" }));

    expect(screen.getByText(/Enter a valid Git URL/)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("creates a task with the entered repo source, goal and mode", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm();

    await user.click(screen.getByRole("radio", { name: "Git URL" }));
    await user.type(
      screen.getByLabelText(/Public Git URL/i),
      "https://github.com/example/tf-demo.git",
    );
    await user.type(
      screen.getByLabelText(/Infrastructure goal/i),
      "Make the bucket private without deleting it.",
    );
    await user.click(screen.getByRole("radio", { name: /^Audit/ }));
    await user.click(screen.getByRole("button", { name: "Create task" }));

    const expected: CreateTaskInput = {
      repo_source: {
        kind: "git_url",
        url: "https://github.com/example/tf-demo.git",
      },
      goal: "Make the bucket private without deleting it.",
      mode: "audit",
    };

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expected));
  });

  it("creates a task from an accepted zip upload", async () => {
    const user = userEvent.setup();
    const { onSubmit } = renderForm();

    await user.upload(
      screen.getByLabelText(/Terraform repository/i),
      new File(["hashicorp"], "insecure-bucket.zip", { type: "application/zip" }),
    );
    await user.type(
      screen.getByLabelText(/Infrastructure goal/i),
      "Make the bucket private without deleting it.",
    );
    await user.click(screen.getByRole("button", { name: "Create task" }));

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith({
        repo_source: {
          kind: "zip",
          filename: "insecure-bucket.zip",
          file: expect.any(File),
        },
        goal: "Make the bucket private without deleting it.",
        mode: "build",
      }),
    );
  });

  it("surfaces a submission failure", async () => {
    const user = userEvent.setup();
    const onSubmit = vi
      .fn()
      .mockRejectedValue(new Error("Worker service unreachable."));
    render(<TaskCreationForm onSubmit={onSubmit} />);

    await user.upload(
      screen.getByLabelText(/Terraform repository/i),
      new File(["x"], "repo.zip", { type: "application/zip" }),
    );
    await user.type(
      screen.getByLabelText(/Infrastructure goal/i),
      "Make the bucket private without deleting it.",
    );
    await user.click(screen.getByRole("button", { name: "Create task" }));

    expect(await screen.findByText("Worker service unreachable.")).toBeInTheDocument();
  });
});
