"use client";

import { Button } from "@vergeo/ui/src/button";
import { ConfirmDialog } from "@vergeo/ui/src/confirm-dialog";
import { EmptyState } from "@vergeo/ui/src/empty-state";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { createAccountApiClient, type Address } from "./account-api";
import { AddressForm, type AddressFormLabels } from "./address-form";

export type AddressManagerLabels = AddressFormLabels & {
  add: string;
  edit: string;
  emptyTitle: string;
  emptyBody: string;
  countLabel: string;
  coordsTemplate: string;
  delete: string;
  deleteConfirmTitle: string;
  deleteConfirmBody: string;
  saved: string;
};

type AddressManagerProps = {
  locale: string;
  accessToken: string;
  initialAddresses: Address[];
  labels: AddressManagerLabels;
};

export function AddressManager({
  locale,
  accessToken,
  initialAddresses,
  labels,
}: AddressManagerProps) {
  const router = useRouter();
  const api = createAccountApiClient(() => accessToken);

  const [addresses, setAddresses] = useState(initialAddresses);
  const [editing, setEditing] = useState<Address | "new" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Address | null>(null);
  const [status, setStatus] = useState<string | undefined>();

  const refreshAddresses = async () => {
    const next = await api.listAddresses();
    setAddresses(next);
    router.refresh();
  };

  const handleDelete = async () => {
    if (!deleteTarget) {
      return;
    }
    await api.deleteAddress(deleteTarget.id);
    setDeleteTarget(null);
    setStatus(labels.saved);
    await refreshAddresses();
  };

  if (editing) {
    return (
      <div className="space-y-4">
        <h2 className="font-display text-h2 text-display-ink">
          {editing === "new" ? labels.add : labels.edit}
        </h2>
        <AddressForm
          locale={locale}
          accessToken={accessToken}
          labels={labels}
          initial={editing === "new" ? undefined : editing}
          onCancel={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            setStatus(labels.saved);
            void refreshAddresses();
          }}
        />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-text-2">{labels.countLabel}</p>
        <Button
          type="button"
          loading={false}
          loadingLabel={labels.saving}
          onClick={() => setEditing("new")}
        >
          {labels.add}
        </Button>
      </div>

      {status ? (
        <p className="text-sm text-success" role="status">
          {status}
        </p>
      ) : null}

      {addresses.length === 0 ? (
        <EmptyState title={labels.emptyTitle} body={labels.emptyBody} />
      ) : (
        <ul className="space-y-3">
          {addresses.map((address) => (
            <li
              key={address.id}
              className="rounded-lg border border-border bg-surface p-4 shadow-1"
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="space-y-1">
                  <p className="font-medium text-text">{address.label ?? address.landmark}</p>
                  {address.label ? <p className="text-sm text-text-2">{address.landmark}</p> : null}
                  {address.lat !== null && address.lng !== null ? (
                    <p className="text-xs text-text-3">
                      {labels.coordsTemplate
                        .replace("{lat}", address.lat.toFixed(5))
                        .replace("{lng}", address.lng.toFixed(5))}
                    </p>
                  ) : null}
                  {address.phone ? <p className="text-sm text-text-2">{address.phone}</p> : null}
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    loading={false}
                    loadingLabel={labels.saving}
                    onClick={() => setEditing(address)}
                  >
                    {labels.edit}
                  </Button>
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    loading={false}
                    loadingLabel={labels.saving}
                    onClick={() => setDeleteTarget(address)}
                  >
                    {labels.delete}
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        title={labels.deleteConfirmTitle}
        body={labels.deleteConfirmBody}
        confirmLabel={labels.delete}
        cancelLabel={labels.cancel}
        destructive
        onConfirm={handleDelete}
      />
    </div>
  );
}
