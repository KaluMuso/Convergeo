// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { addRecentSearch, readRecentSearches } from "./recent-searches";
import { SearchInput, type SuggestResponse } from "./search-input";

const { request, push } = vi.hoisted(() => ({
  request: vi.fn(),
  push: vi.fn(),
}));
vi.mock("@vergeo/config", () => ({ createApiClient: () => ({ request }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const labels = {
  placeholder: "Search Convergeo",
  submit: "Search",
  ariaLabel: "Search",
  suggestionsLabel: "Search suggestions",
  noSuggestions: "No suggestions",
  recentTitle: "Recent searches",
};

function response(title: string): SuggestResponse {
  return {
    query: title,
    suggestions: [{ title, entity_kind: "product", entity_id: title, slug: title }],
  };
}

function deferred() {
  let resolve!: (value: SuggestResponse) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<SuggestResponse>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function change(value: string) {
  fireEvent.change(screen.getByRole("combobox"), { target: { value } });
}

async function debounce() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(200);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  request.mockReset();
  push.mockReset();
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe("SearchInput request lifecycle", () => {
  it("resumes a blurred queued query on refocus without editing", async () => {
    request.mockResolvedValue(response("phone"));
    render(<SearchInput locale="en" labels={labels} />);
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    change("phone");
    fireEvent.blur(input);
    await debounce();
    expect(request).not.toHaveBeenCalled();
    fireEvent.focus(input);
    await debounce();
    expect(request).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("option", { name: /phone/ })).toBeInTheDocument();
  });

  it("resumes a blurred in-flight query on refocus and ignores its old response", async () => {
    const old = deferred();
    request.mockReturnValueOnce(old.promise).mockResolvedValueOnce(response("current"));
    render(<SearchInput locale="en" labels={labels} />);
    const input = screen.getByRole("combobox");
    fireEvent.focus(input);
    change("phone");
    await debounce();
    fireEvent.blur(input);
    await debounce();
    fireEvent.focus(input);
    await debounce();
    expect(request).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("option", { name: /current/ })).toBeInTheDocument();
    await act(async () => {
      old.resolve(response("stale"));
    });
    expect(screen.queryByRole("option", { name: /stale/ })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: /current/ })).toBeInTheDocument();
  });

  it("does not duplicate queued or in-flight work on focus", async () => {
    const pending = deferred();
    request.mockReturnValue(pending.promise);
    render(<SearchInput locale="en" labels={labels} />);
    const input = screen.getByRole("combobox");
    change("phone");
    fireEvent.focus(input);
    fireEvent.focus(input);
    await debounce();
    expect(request).toHaveBeenCalledTimes(1);
    fireEvent.focus(input);
    await debounce();
    expect(request).toHaveBeenCalledTimes(1);
    await act(async () => {
      pending.resolve(response("phone"));
    });
    expect(screen.getByRole("option", { name: /phone/ })).toBeInTheDocument();
  });

  it("reopens already loaded suggestions without refetching", async () => {
    request.mockResolvedValue(response("phone"));
    render(<SearchInput locale="en" labels={labels} />);
    const input = screen.getByRole("combobox");
    change("phone");
    await debounce();
    fireEvent.blur(input);
    await debounce();
    fireEvent.focus(input);
    await debounce();
    expect(request).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("option", { name: /phone/ })).toBeInTheDocument();
  });

  it("preserves recent searches on autofocus", () => {
    addRecentSearch("chitenge");
    render(<SearchInput locale="en" labels={labels} autoFocus />);
    expect(screen.getByRole("option", { name: "chitenge" })).toBeInTheDocument();
  });

  it("cancels a queued suggestion when cleared before debounce", async () => {
    request.mockResolvedValue(response("phone"));
    render(<SearchInput locale="en" labels={labels} />);
    change("phone");
    change("");
    await debounce();
    expect(request).not.toHaveBeenCalled();
    expect(screen.getByRole("combobox")).toHaveValue("");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it.each([false, true])(
    "ignores a late response after clearing (recents: %s)",
    async (recents) => {
      const pending = deferred();
      request.mockReturnValue(pending.promise);
      if (recents) addRecentSearch("chitenge");
      render(<SearchInput locale="en" labels={labels} />);
      change("phone");
      await debounce();
      change("");
      await act(async () => {
        pending.resolve(response("phone"));
      });
      expect(screen.getByRole("combobox")).toHaveValue("");
      expect(screen.queryByRole("option", { name: /phone/ })).not.toBeInTheDocument();
      if (recents) {
        expect(screen.getByRole("listbox", { name: labels.recentTitle })).toBeInTheDocument();
        fireEvent.keyDown(screen.getByRole("combobox"), { key: "Enter" });
        expect(push).toHaveBeenCalledWith("/en/search?q=chitenge");
      } else {
        expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
      }
    },
  );

  it("invalidates A immediately while B is still debouncing", async () => {
    const a = deferred();
    request.mockReturnValueOnce(a.promise).mockResolvedValueOnce(response("B"));
    render(<SearchInput locale="en" labels={labels} />);
    change("A");
    await debounce();
    change("B");
    await act(async () => {
      a.resolve(response("A"));
    });
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
    await debounce();
    expect(screen.getByRole("option", { name: /B/ })).toBeInTheDocument();
  });

  it.each(["resolve", "reject"] as const)(
    "keeps B when A settles out of order: %s",
    async (settle) => {
      const a = deferred();
      const b = deferred();
      request.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise);
      render(<SearchInput locale="en" labels={labels} />);
      change("A");
      await debounce();
      change("B");
      await debounce();
      await act(async () => {
        b.resolve(response("B"));
      });
      await act(async () => {
        if (settle === "resolve") a.resolve(response("A"));
        else a.reject(new Error("offline"));
      });
      expect(screen.getByRole("option", { name: /B/ })).toBeInTheDocument();
      expect(screen.queryByRole("option", { name: /A/ })).not.toBeInTheDocument();
    },
  );

  it("removes old selectable results as soon as the input changes", async () => {
    request.mockResolvedValue(response("A"));
    render(<SearchInput locale="en" labels={labels} />);
    change("A");
    await debounce();
    change("B");
    expect(screen.queryByRole("option")).not.toBeInTheDocument();
    fireEvent.submit(screen.getByRole("search"));
    expect(push).toHaveBeenCalledWith("/en/search?q=B");
    await debounce();
    expect(request).toHaveBeenCalledTimes(1);
  });

  it("cancels queued work and blur timers on unmount", async () => {
    const view = render(<SearchInput locale="en" labels={labels} />);
    change("phone");
    fireEvent.blur(screen.getByRole("combobox"));
    view.unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(vi.getTimerCount()).toBe(0);
    await debounce();
    expect(request).not.toHaveBeenCalled();
  });

  it("does not consume an in-flight response after unmount", async () => {
    const pending = deferred();
    request.mockReturnValue(pending.promise);
    const view = render(<SearchInput locale="en" labels={labels} />);
    change("phone");
    await debounce();
    view.unmount();
    const read = vi.fn(() => response("phone").suggestions);
    const result = {
      query: "phone",
      get suggestions() {
        return read();
      },
    };
    await act(async () => {
      pending.resolve(result);
    });
    expect(read).not.toHaveBeenCalled();
  });

  it("does not reopen after submitting during an in-flight request", async () => {
    const pending = deferred();
    request.mockReturnValue(pending.promise);
    render(<SearchInput locale="en" labels={labels} />);
    change("phone");
    await debounce();
    fireEvent.submit(screen.getByRole("search"));
    expect(push).toHaveBeenCalledWith("/en/search?q=phone");
    expect(readRecentSearches()).toEqual(["phone"]);
    await act(async () => {
      pending.resolve(response("phone"));
    });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("invalidates requests when navigation replaces initialQuery", async () => {
    const pending = deferred();
    request.mockReturnValue(pending.promise);
    const view = render(<SearchInput locale="en" labels={labels} />);
    change("phone");
    await debounce();
    view.rerender(<SearchInput locale="en" labels={labels} initialQuery="shoes" />);
    await act(async () => {
      pending.resolve(response("phone"));
    });
    expect(screen.getByRole("combobox")).toHaveValue("shoes");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it.each(["Escape", "blur"])("keeps pending results dismissed after %s", async (dismiss) => {
    const pending = deferred();
    request.mockReturnValue(pending.promise);
    render(<SearchInput locale="en" labels={labels} />);
    change("phone");
    await debounce();
    if (dismiss === "blur") {
      fireEvent.blur(screen.getByRole("combobox"));
      await debounce();
    } else fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
    await act(async () => {
      pending.resolve(response("phone"));
    });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("preserves keyboard wrapping, product links and recents under StrictMode", async () => {
    request.mockResolvedValue({
      query: "phone",
      suggestions: [...response("first").suggestions, ...response("second").suggestions],
    });
    render(
      <StrictMode>
        <SearchInput locale="en" labels={labels} />
      </StrictMode>,
    );
    change("phone");
    await debounce();
    const input = screen.getByRole("combobox");
    expect(screen.getByRole("option", { name: /first/ })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(input, { key: "ArrowUp" });
    expect(screen.getByRole("option", { name: /second/ })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(screen.getByRole("option", { name: /first/ })).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(push).toHaveBeenCalledWith("/en/p/first");
    expect(readRecentSearches()).toEqual(["first"]);
    expect(input).toHaveAttribute("aria-expanded", "false");
  });

  it.each(["empty", "error"])(
    "keeps the dropdown closed while loading and after %s, then recovers",
    async (outcome) => {
      const pending = deferred();
      request.mockReturnValueOnce(pending.promise).mockResolvedValueOnce(response("shoes"));
      render(<SearchInput locale="en" labels={labels} />);
      change("phone");
      await debounce();
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
      expect(screen.queryByText(labels.noSuggestions)).not.toBeInTheDocument();
      await act(async () => {
        if (outcome === "empty") pending.resolve({ query: "phone", suggestions: [] });
        else pending.reject(new Error("offline"));
      });
      expect(screen.getByRole("combobox")).toHaveValue("phone");
      expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
      change("shoes");
      await debounce();
      expect(screen.getByRole("option", { name: /shoes/ })).toBeInTheDocument();
    },
  );
});
