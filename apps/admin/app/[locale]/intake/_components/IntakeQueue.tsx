"use client";

import { formatK } from "@vergeo/i18n";
import { DataTableView } from "@vergeo/ui/src/data-table";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AdminLoadFailure } from "../../_components/AdminLoadFailure";
import { resolveQueueLoadFailure } from "../../_components/queue-load-failure";

import { intakeApi, type IntakeQueueItem } from "./api";

type IntakeQueueProps = {
  locale: string;
};

export function IntakeQueue({ locale }: IntakeQueueProps) {
  const t = useTranslations("admin.intake.queue");
  const tRoot = useTranslations("admin.intake");
  const [items, setItems] = useState<IntakeQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [permissionDenied, setPermissionDenied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setPermissionDenied(false);
    try {
      setItems(await intakeApi.request<IntakeQueueItem[]>("/admin/intake"));
    } catch (err) {
      const failure = resolveQueueLoadFailure(err);
      setPermissionDenied(failure.permissionDenied);
      setError(t(failure.messageKey));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const tableLabels = useMemo(
    () => ({
      sortAscending: (column: string) => t("sortAscending", { column }),
      sortDescending: (column: string) => t("sortDescending", { column }),
      sortable: (column: string) => t("sortable", { column }),
      paginationAriaLabel: t("paginationAria"),
      paginationPrevious: t("paginationPrevious"),
      paginationNext: t("paginationNext"),
      paginationPage: (page: number) => t("paginationPage", { page }),
    }),
    [t],
  );

  const columns = useMemo(
    () => [
      {
        id: "vendor",
        header: t("vendor"),
        sortLabel: t("vendor"),
        sortable: true,
        getSortValue: (row: IntakeQueueItem) => row.vendor_display_name ?? row.vendor_id,
        cell: (row: IntakeQueueItem) => row.vendor_display_name ?? row.vendor_id,
      },
      {
        id: "product",
        header: t("product"),
        sortLabel: t("product"),
        sortable: true,
        getSortValue: (row: IntakeQueueItem) => row.title ?? "",
        cell: (row: IntakeQueueItem) => row.title ?? "—",
      },
      {
        id: "price",
        header: t("price"),
        sortLabel: t("price"),
        sortable: true,
        getSortValue: (row: IntakeQueueItem) => row.price_ngwee ?? -1,
        cell: (row: IntakeQueueItem) => (row.price_ngwee === null ? "—" : formatK(row.price_ngwee)),
      },
      {
        id: "tier",
        header: t("tier"),
        sortLabel: t("tier"),
        sortable: true,
        getSortValue: (row: IntakeQueueItem) => row.vendor_kyc_tier ?? "",
        cell: (row: IntakeQueueItem) => row.vendor_kyc_tier ?? "—",
      },
      {
        id: "submitted",
        header: t("submitted"),
        sortLabel: t("submitted"),
        sortable: true,
        getSortValue: (row: IntakeQueueItem) => row.submitted_at ?? "",
        cell: (row: IntakeQueueItem) => row.submitted_at ?? "—",
      },
      {
        id: "actions",
        header: "",
        cell: (row: IntakeQueueItem) => (
          <Link
            href={`/${locale}/intake/${row.session_id}`}
            className="inline-flex min-h-11 items-center rounded-md border border-border px-3"
          >
            {t("open")}
          </Link>
        ),
        cellClassName: "text-right",
      },
    ],
    [locale, t],
  );

  if (loading) {
    return <p className="text-sm text-muted">{tRoot("loading")}</p>;
  }

  if (error) {
    return (
      <AdminLoadFailure
        permissionDenied={permissionDenied}
        message={error}
        retryLabel={tRoot("error.retry")}
        onRetry={() => void load()}
      />
    );
  }

  return (
    <DataTableView
      rows={items}
      columns={columns}
      rowKey={(row) => row.session_id}
      labels={tableLabels}
      pageSize={8}
      tableClassName="admin-data-table min-w-full w-full text-sm"
      data-testid="intake-queue"
      caption={t("tableCaption")}
      empty={{ title: tRoot("empty.title"), body: tRoot("empty.body") }}
    />
  );
}
