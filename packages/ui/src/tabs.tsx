"use client";

import { useCallback, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export type TabItem = {
  key: string;
  label: ReactNode;
  panel: ReactNode;
  disabled?: boolean;
};

export type TabsProps = {
  items: TabItem[];
  ariaLabel: string;
  value?: string;
  defaultValue?: string;
  onValueChange?: (key: string) => void;
  className?: string;
  tabListClassName?: string;
  panelClassName?: string;
};

function mergeClasses(...classes: Array<string | false | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

function getEnabledIndices(items: TabItem[]): number[] {
  return items.map((item, index) => (item.disabled ? -1 : index)).filter((i) => i >= 0);
}

export function Tabs({
  items,
  ariaLabel,
  value,
  defaultValue,
  onValueChange,
  className,
  tabListClassName,
  panelClassName,
}: TabsProps) {
  const baseId = useId();
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const firstEnabled = items.find((item) => !item.disabled)?.key ?? items[0]?.key ?? "";
  const [uncontrolledKey, setUncontrolledKey] = useState(defaultValue ?? firstEnabled);

  const isControlled = value !== undefined;
  const activeKey = isControlled ? value : uncontrolledKey;

  const setActiveKey = useCallback(
    (key: string) => {
      if (!isControlled) {
        setUncontrolledKey(key);
      }
      onValueChange?.(key);
    },
    [isControlled, onValueChange],
  );

  const activeIndex = items.findIndex((item) => item.key === activeKey);

  const focusTab = (index: number) => {
    const tab = tabRefs.current[index];
    tab?.focus();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const enabled = getEnabledIndices(items);
    const currentEnabledIndex = enabled.indexOf(activeIndex);
    if (currentEnabledIndex < 0) {
      return;
    }

    let nextEnabledIndex = currentEnabledIndex;

    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
        event.preventDefault();
        nextEnabledIndex = (currentEnabledIndex + 1) % enabled.length;
        break;
      case "ArrowLeft":
      case "ArrowUp":
        event.preventDefault();
        nextEnabledIndex = (currentEnabledIndex - 1 + enabled.length) % enabled.length;
        break;
      case "Home":
        event.preventDefault();
        nextEnabledIndex = 0;
        break;
      case "End":
        event.preventDefault();
        nextEnabledIndex = enabled.length - 1;
        break;
      default:
        return;
    }

    const nextIndex = enabled[nextEnabledIndex];
    if (nextIndex === undefined) {
      return;
    }
    const nextKey = items[nextIndex]?.key;
    if (nextKey) {
      setActiveKey(nextKey);
      focusTab(nextIndex);
    }
  };

  return (
    <div className={mergeClasses("w-full", className)}>
      <div
        role="tablist"
        aria-label={ariaLabel}
        className={mergeClasses(
          "flex gap-1 overflow-x-auto border-b border-border",
          tabListClassName,
        )}
        onKeyDown={handleKeyDown}
      >
        {items.map((item, index) => {
          const selected = item.key === activeKey;
          const tabId = `${baseId}-tab-${item.key}`;
          const panelId = `${baseId}-panel-${item.key}`;

          return (
            <button
              key={item.key}
              ref={(el) => {
                tabRefs.current[index] = el;
              }}
              type="button"
              role="tab"
              id={tabId}
              aria-selected={selected}
              aria-controls={panelId}
              tabIndex={selected ? 0 : -1}
              disabled={item.disabled}
              onClick={() => setActiveKey(item.key)}
              className={mergeClasses(
                "min-h-11 shrink-0 px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:shadow-focusRing",
                selected ? "border-b-2 border-primary text-primary" : "text-text-2 hover:text-text",
                item.disabled && "cursor-not-allowed opacity-50",
              )}
              style={{ transitionTimingFunction: "var(--ease-std)" }}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      {items.map((item) => {
        const selected = item.key === activeKey;
        const tabId = `${baseId}-tab-${item.key}`;
        const panelId = `${baseId}-panel-${item.key}`;

        return (
          <div
            key={item.key}
            role="tabpanel"
            id={panelId}
            aria-labelledby={tabId}
            hidden={!selected}
            tabIndex={0}
            className={mergeClasses(
              "py-4 focus-visible:outline-none focus-visible:shadow-focusRing",
              panelClassName,
            )}
          >
            {selected ? item.panel : null}
          </div>
        );
      })}
    </div>
  );
}
