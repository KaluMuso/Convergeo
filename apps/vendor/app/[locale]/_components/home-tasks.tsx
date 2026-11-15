"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

import type { HomeTask, HomeTaskTone } from "../_lib/home-tasks";

const TONE_CLASSES: Record<HomeTaskTone, string> = {
  danger: "border-danger bg-danger/10",
  warning: "border-warning/40 bg-warning/10",
  info: "border-info/40 bg-info/10",
  neutral: "border-border bg-surface",
};

type HomeTaskListProps = {
  locale: string;
  tasks: HomeTask[];
};

/** Numbered "do this next" list — most urgent first, each one a single tap. */
export function HomeTaskList({ locale, tasks }: HomeTaskListProps) {
  const t = useTranslations("vendor");
  if (tasks.length === 0) {
    return null;
  }
  return (
    <section
      className="flex flex-col gap-3"
      aria-labelledby="vendor-home-tasks-heading"
      data-testid="vendor-home-tasks"
    >
      <div className="space-y-1 px-1">
        <h2 id="vendor-home-tasks-heading" className="text-base font-semibold text-text">
          {t("home.tasks.heading")}
        </h2>
        <p className="text-sm text-text-2">{t("home.tasks.intro")}</p>
      </div>
      <ol className="flex flex-col gap-2">
        {tasks.map((task, index) => (
          <li key={task.key}>
            <Link
              href={`/${locale}${task.href}`}
              className={`flex min-h-14 items-start gap-3 rounded-xl border p-3 focus-visible:outline-none focus-visible:shadow-focusRing ${TONE_CLASSES[task.tone]}`}
              data-testid="vendor-home-task"
              data-task={task.key}
            >
              <span
                aria-hidden="true"
                className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary font-mono text-xs font-semibold text-[var(--primary-btn-fg)]"
              >
                {index + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-text">
                  {t(`home.tasks.items.${task.key}.title`, { count: task.count ?? 0 })}
                </span>
                <span className="mt-0.5 block text-sm text-text-2">
                  {t(`home.tasks.items.${task.key}.body`, { count: task.count ?? 0 })}
                </span>
              </span>
              <span aria-hidden="true" className="mt-0.5 text-lg leading-none text-text-3">
                ›
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}
