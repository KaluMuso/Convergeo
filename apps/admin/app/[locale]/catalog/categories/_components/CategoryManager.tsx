"use client";

import { ApiError } from "@vergeo/config";
import { notify } from "@vergeo/ui/src/toast";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useAdminPermissions } from "../../../../../lib/roles-api";
import { classifyAdminRequestError } from "../../../_components/admin-request";
import { AdminLoadFailure } from "../../../_components/AdminLoadFailure";
import { ConfirmModal } from "../../../_components/ConfirmModal";
import { EmptyBlock, LoadingBlock } from "../../../_components/StateBlocks";

import {
  createNode,
  deleteNode,
  listNodes,
  moveNode,
  reorderNodes,
  setStatus,
  updateNode,
  uploadNodeImage,
} from "./taxonomy-api";
import {
  canManageUmbrella,
  flattenTree,
  movableParents,
  reorderedIds,
  slugify,
  UMBRELLAS,
  type TaxonomyNode,
  type TaxonomyStatus,
  type Umbrella,
} from "./taxonomy-model";

const inputClass = "min-h-11 w-full rounded-md border border-border bg-bg px-3 text-sm text-text";
const buttonClass =
  "inline-flex min-h-11 items-center rounded-md border border-border px-3 text-xs font-medium text-text disabled:opacity-50";
const STATUS_CLASS: Record<TaxonomyStatus, string> = {
  published: "bg-success/10 text-success",
  draft: "bg-warning/10 text-warning",
  blocked: "bg-danger/10 text-danger",
};

type LoadState =
  | { kind: "loading" }
  | { kind: "error"; permission: boolean }
  | { kind: "ready"; nodes: TaxonomyNode[] };

type Dialog =
  | { kind: "form"; node: TaxonomyNode | null; parentId: string | null }
  | { kind: "block"; node: TaxonomyNode }
  | { kind: "delete"; node: TaxonomyNode }
  | null;

type FormState = {
  name: string;
  slug: string;
  slugTouched: boolean;
  parentId: string;
  status: TaxonomyStatus;
  showCustomer: boolean;
  showVendor: boolean;
  icon: string;
  imagePublicId: string | null;
  imageAlt: string;
  previewUrl: string | null;
};

function initialForm(node: TaxonomyNode | null, parentId: string | null): FormState {
  return {
    name: node?.name ?? "",
    slug: node?.slug ?? "",
    slugTouched: node !== null,
    parentId: node ? (node.parent_id ?? "") : (parentId ?? ""),
    status: node?.status ?? "draft",
    showCustomer: node?.show_in_customer ?? true,
    showVendor: node?.show_in_vendor ?? true,
    icon: node?.icon ?? "",
    imagePublicId: node?.image_public_id ?? null,
    imageAlt: node?.image_alt ?? "",
    previewUrl: node?.image_url ?? null,
  };
}

export function CategoryManager() {
  const t = useTranslations("admin.catalog.categories");
  const grants = useAdminPermissions();
  const [umbrella, setUmbrella] = useState<Umbrella>("product");
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [dialog, setDialog] = useState<Dialog>(null);
  const [form, setForm] = useState<FormState>(initialForm(null, null));
  const [reason, setReason] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const canWrite = canManageUmbrella(umbrella, grants);

  const load = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const nodes = await listNodes(umbrella, submitted);
      setState({ kind: "ready", nodes: Array.isArray(nodes) ? nodes : [] });
    } catch (error) {
      setState({
        kind: "error",
        permission: classifyAdminRequestError(error).kind === "permission",
      });
    }
  }, [umbrella, submitted]);

  useEffect(() => {
    if (!grants) return;
    if (!canManageUmbrella(umbrella, grants)) {
      setState({ kind: "error", permission: true });
      return;
    }
    void load();
  }, [grants, umbrella, load]);

  const nodes = state.kind === "ready" ? state.nodes : [];
  const rows = useMemo(() => flattenTree(nodes), [nodes]);

  const errorMessage = (error: unknown): string => {
    if (classifyAdminRequestError(error).kind === "permission") return t("errors.permission");
    if (error instanceof ApiError) {
      if (error.code === "category_has_listings") return t("errors.hasListings");
      if (error.code === "category_has_children") return t("errors.hasChildren");
      if (error.code === "slug_taken") return t("errors.slugTaken");
      if (error.code === "category_cycle") return t("errors.cycle");
      if (error.status === 422) return t("errors.invalid");
    }
    return t("errors.generic");
  };

  const openForm = (node: TaxonomyNode | null, parentId: string | null) => {
    setForm(initialForm(node, parentId));
    setActionError(null);
    setDialog({ kind: "form", node, parentId });
  };

  const quick = async (node: TaxonomyNode, status: TaxonomyStatus, doneKey: string) => {
    setBusyId(node.id);
    try {
      await setStatus(umbrella, node.id, status);
      notify.success(t(`done.${doneKey}`));
      await load();
    } catch (error) {
      notify.error(errorMessage(error));
    } finally {
      setBusyId(null);
    }
  };

  const move = async (siblings: TaxonomyNode[], node: TaxonomyNode, direction: -1 | 1) => {
    const ids = reorderedIds(siblings, node.id, direction);
    if (!ids) return;
    setBusyId(node.id);
    try {
      await reorderNodes(umbrella, node.parent_id, ids);
      await load();
    } catch (error) {
      notify.error(errorMessage(error));
    } finally {
      setBusyId(null);
    }
  };

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    setActionError(null);
    try {
      const publicId = await uploadNodeImage(umbrella, file);
      setForm((prev) => ({
        ...prev,
        imagePublicId: publicId,
        previewUrl: URL.createObjectURL(file),
      }));
    } catch {
      setActionError(t("errors.upload"));
    } finally {
      setUploading(false);
    }
  };

  const saveForm = async (): Promise<boolean> => {
    if (dialog?.kind !== "form") return false;
    const { node } = dialog;
    const common = {
      show_in_customer: form.showCustomer,
      show_in_vendor: form.showVendor,
      icon: form.icon.trim() || null,
      image_public_id: form.imagePublicId,
      image_alt: form.imagePublicId ? form.imageAlt.trim() : null,
    };
    try {
      if (node) {
        await updateNode(umbrella, node.id, {
          name: form.name.trim(),
          ...common,
        });
        if ((node.parent_id ?? "") !== form.parentId) {
          await moveNode(umbrella, node.id, form.parentId || null);
        }
      } else {
        await createNode(umbrella, {
          name: form.name.trim(),
          slug: form.slug.trim() || undefined,
          parent_id: form.parentId || null,
          status: form.status,
          ...common,
        });
      }
      notify.success(t(node ? "done.saved" : "done.created"));
      await load();
      return true;
    } catch (error) {
      setActionError(errorMessage(error));
      return false;
    }
  };

  const runBlock = async (): Promise<boolean> => {
    if (dialog?.kind !== "block") return false;
    try {
      await setStatus(umbrella, dialog.node.id, "blocked", reason.trim());
      notify.success(t("done.blocked"));
      await load();
      return true;
    } catch (error) {
      setActionError(errorMessage(error));
      return false;
    }
  };

  const runDelete = async (): Promise<boolean> => {
    if (dialog?.kind !== "delete") return false;
    try {
      await deleteNode(umbrella, dialog.node.id);
      notify.success(t("done.deleted"));
      await load();
      return true;
    } catch (error) {
      setActionError(errorMessage(error));
      return false;
    }
  };

  const formValid =
    form.name.trim().length >= 2 && (!form.imagePublicId || form.imageAlt.trim().length > 0);
  const parentOptions =
    dialog?.kind === "form" && dialog.node ? movableParents(nodes, dialog.node.id) : nodes;

  return (
    <div className="space-y-4">
      <div role="tablist" aria-label={t("tabsLabel")} className="flex flex-wrap gap-2">
        {UMBRELLAS.map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={umbrella === key}
            className={`${buttonClass} ${umbrella === key ? "border-primary bg-primary/10" : ""}`}
            onClick={() => setUmbrella(key)}
          >
            {t(`tabs.${key}`)}
          </button>
        ))}
      </div>
      <p className="text-sm text-text-2">{t(`hints.${umbrella}`)}</p>

      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          setSubmitted(query);
        }}
      >
        <label className="min-w-0 flex-1 space-y-1 text-sm">
          <span className="text-muted">{t("search")}</span>
          <input
            className={inputClass}
            value={query}
            maxLength={80}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <button type="submit" className={buttonClass}>
          {t("searchButton")}
        </button>
        {canWrite ? (
          <button
            type="button"
            className={`${buttonClass} border-primary text-primary`}
            onClick={() => openForm(null, null)}
          >
            {t("add")}
          </button>
        ) : null}
      </form>

      {state.kind === "loading" ? (
        <LoadingBlock label={t("loading")} />
      ) : state.kind === "error" ? (
        <AdminLoadFailure
          permissionDenied={state.permission}
          message={state.permission ? t("permissionDenied") : t("loadError")}
          retryLabel={t("retry")}
          onRetry={() => void load()}
        />
      ) : rows.length === 0 ? (
        <EmptyBlock title={t("empty")} body={t("emptyBody")} />
      ) : (
        <ul className="space-y-2" data-testid="taxonomy-rows">
          {rows.map(({ node, depth, siblings }) => {
            const index = siblings.findIndex((s) => s.id === node.id);
            const busy = busyId === node.id;
            return (
              <li
                key={node.id}
                data-testid={`taxonomy-row-${node.slug}`}
                style={{ marginInlineStart: `${depth * 1.25}rem` }}
                className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-surface p-3 text-sm"
              >
                {node.image_url ? (
                  <img
                    src={node.image_url}
                    alt={node.image_alt ?? ""}
                    loading="lazy"
                    className="size-12 shrink-0 rounded-full border border-border object-cover"
                  />
                ) : (
                  <span
                    aria-hidden="true"
                    className="grid size-12 shrink-0 place-items-center rounded-full border border-border bg-bg-2 font-display text-text-2"
                  >
                    {node.name.slice(0, 1).toUpperCase()}
                  </span>
                )}
                <div className="min-w-0 flex-1 space-y-1">
                  <p className="font-medium text-text">{node.name}</p>
                  <p className="text-xs text-muted">{node.slug}</p>
                  <div className="flex flex-wrap gap-1">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_CLASS[node.status]}`}
                    >
                      {t(`status.${node.status}`)}
                    </span>
                    {node.show_in_customer ? (
                      <span className="rounded-full bg-bg-2 px-2 py-0.5 text-xs text-text-2">
                        {t("visibility.customer")}
                      </span>
                    ) : null}
                    {node.show_in_vendor ? (
                      <span className="rounded-full bg-bg-2 px-2 py-0.5 text-xs text-text-2">
                        {t("visibility.vendor")}
                      </span>
                    ) : null}
                  </div>
                </div>
                {canWrite ? (
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      className={buttonClass}
                      aria-label={t("moveUp", { name: node.name })}
                      disabled={busy || index <= 0}
                      onClick={() => void move(siblings, node, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className={buttonClass}
                      aria-label={t("moveDown", { name: node.name })}
                      disabled={busy || index >= siblings.length - 1}
                      onClick={() => void move(siblings, node, 1)}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      className={buttonClass}
                      onClick={() => openForm(node, null)}
                    >
                      {t("actions.edit")}
                    </button>
                    <button
                      type="button"
                      className={buttonClass}
                      onClick={() => openForm(null, node.id)}
                    >
                      {t("actions.addChild")}
                    </button>
                    {node.status === "published" ? (
                      <button
                        type="button"
                        className={buttonClass}
                        disabled={busy}
                        onClick={() => void quick(node, "draft", "unpublished")}
                      >
                        {t("actions.unpublish")}
                      </button>
                    ) : (
                      <button
                        type="button"
                        className={buttonClass}
                        disabled={busy}
                        onClick={() =>
                          void quick(
                            node,
                            "published",
                            node.status === "blocked" ? "unblocked" : "published",
                          )
                        }
                      >
                        {node.status === "blocked" ? t("actions.unblock") : t("actions.publish")}
                      </button>
                    )}
                    {node.status !== "blocked" ? (
                      <button
                        type="button"
                        className={`${buttonClass} border-danger text-danger`}
                        onClick={() => {
                          setReason("");
                          setActionError(null);
                          setDialog({ kind: "block", node });
                        }}
                      >
                        {t("actions.block")}
                      </button>
                    ) : null}
                    <button
                      type="button"
                      className={`${buttonClass} text-danger`}
                      onClick={() => {
                        setActionError(null);
                        setDialog({ kind: "delete", node });
                      }}
                    >
                      {t("actions.delete")}
                    </button>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      {dialog?.kind === "form" ? (
        <ConfirmModal
          open
          data-testid="taxonomy-form"
          title={t(dialog.node ? "form.editTitle" : "form.createTitle")}
          summary={t("form.summary")}
          confirmLabel={t("form.save")}
          canConfirm={formValid && !uploading}
          error={actionError}
          onConfirm={saveForm}
          onClose={() => setDialog(null)}
        >
          <div className="space-y-3">
            <label className="block space-y-1 text-sm">
              <span className="text-muted">{t("form.name")}</span>
              <input
                className={inputClass}
                value={form.name}
                maxLength={120}
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    name: event.target.value,
                    slug: prev.slugTouched ? prev.slug : slugify(event.target.value),
                  }))
                }
              />
            </label>
            {!dialog.node ? (
              <label className="block space-y-1 text-sm">
                <span className="text-muted">{t("form.slug")}</span>
                <input
                  className={inputClass}
                  value={form.slug}
                  maxLength={80}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      slug: event.target.value,
                      slugTouched: true,
                    }))
                  }
                />
              </label>
            ) : null}
            <label className="block space-y-1 text-sm">
              <span className="text-muted">{t("form.parent")}</span>
              <select
                className={inputClass}
                value={form.parentId}
                onChange={(event) => setForm((prev) => ({ ...prev, parentId: event.target.value }))}
              >
                <option value="">{t("form.noParent")}</option>
                {parentOptions.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.name}
                  </option>
                ))}
              </select>
            </label>
            {!dialog.node ? (
              <label className="block space-y-1 text-sm">
                <span className="text-muted">{t("form.status")}</span>
                <select
                  className={inputClass}
                  value={form.status}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      status: event.target.value as TaxonomyStatus,
                    }))
                  }
                >
                  <option value="draft">{t("status.draft")}</option>
                  <option value="published">{t("status.published")}</option>
                </select>
              </label>
            ) : null}
            <div className="flex flex-wrap gap-4">
              <label className="flex min-h-11 items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.showCustomer}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      showCustomer: event.target.checked,
                    }))
                  }
                />
                {t("form.showCustomer")}
              </label>
              <label className="flex min-h-11 items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={form.showVendor}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      showVendor: event.target.checked,
                    }))
                  }
                />
                {t("form.showVendor")}
              </label>
            </div>
            <label className="block space-y-1 text-sm">
              <span className="text-muted">{t("form.icon")}</span>
              <input
                className={inputClass}
                value={form.icon}
                maxLength={40}
                onChange={(event) => setForm((prev) => ({ ...prev, icon: event.target.value }))}
              />
            </label>
            <div className="space-y-2 text-sm">
              <span className="text-muted">{t("form.image")}</span>
              <div className="flex items-center gap-3">
                {form.previewUrl ? (
                  <img
                    src={form.previewUrl}
                    alt={form.imageAlt}
                    data-testid="taxonomy-image-preview"
                    className="size-16 rounded-full border border-border object-cover"
                  />
                ) : null}
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  aria-label={t("form.image")}
                  disabled={uploading}
                  onChange={(event) => void onFile(event.target.files?.[0])}
                />
              </div>
              {uploading ? <p role="status">{t("form.uploading")}</p> : null}
              {form.imagePublicId ? (
                <>
                  <label className="block space-y-1">
                    <span className="text-muted">{t("form.imageAlt")}</span>
                    <input
                      className={inputClass}
                      value={form.imageAlt}
                      maxLength={200}
                      onChange={(event) =>
                        setForm((prev) => ({
                          ...prev,
                          imageAlt: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <button
                    type="button"
                    className={buttonClass}
                    onClick={() =>
                      setForm((prev) => ({
                        ...prev,
                        imagePublicId: null,
                        imageAlt: "",
                        previewUrl: null,
                      }))
                    }
                  >
                    {t("form.removeImage")}
                  </button>
                </>
              ) : null}
            </div>
          </div>
        </ConfirmModal>
      ) : null}

      {dialog?.kind === "block" ? (
        <ConfirmModal
          open
          destructive
          data-testid="taxonomy-block"
          title={t("block.title")}
          summary={t("block.summary", { name: dialog.node.name })}
          confirmLabel={t("block.confirm")}
          canConfirm={reason.trim().length >= 3}
          error={actionError}
          onConfirm={runBlock}
          onClose={() => setDialog(null)}
        >
          <label className="block space-y-1 text-sm">
            <span className="text-muted">{t("block.reason")}</span>
            <input
              className={inputClass}
              value={reason}
              maxLength={500}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
        </ConfirmModal>
      ) : null}

      {dialog?.kind === "delete" ? (
        <ConfirmModal
          open
          destructive
          data-testid="taxonomy-delete"
          title={t("delete.title")}
          summary={t("delete.summary", { name: dialog.node.name })}
          confirmLabel={t("delete.confirm")}
          error={actionError}
          onConfirm={runDelete}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </div>
  );
}
