"use client";

import { useTranslations } from "next-intl";

import {
  emptyValue,
  type AttributeErrors,
  type FieldDef,
  type FieldValue,
  type FieldValues,
  type Row,
} from "../_lib/archetypes";
import { Button, FormField, Input, Select } from "../_lib/ui";

type Props = {
  scope: "offer" | "service";
  defs: readonly FieldDef[];
  values: FieldValues;
  errors?: AttributeErrors;
  onChange: (next: FieldValues) => void;
  /** Service photos the vendor can attach to an offer (Cloudinary public ids). */
  portfolioImages?: readonly string[];
  idPrefix: string;
  disabled?: boolean;
};

/**
 * Renders the archetype's attribute fields from their definitions (room types, treatment
 * details, passes, rental specs, class schedule, ...). Labels live in
 * `services.vendor.attributes.<scope>.<key>`.
 */
export function AttributeFields({
  scope,
  defs,
  values,
  errors = {},
  onChange,
  portfolioImages = [],
  idPrefix,
  disabled,
}: Props) {
  const t = useTranslations("services.vendor.attributes");
  const set = (key: string, value: FieldValue) => onChange({ ...values, [key]: value });
  const label = (key: string) => t(`${scope}.${key}.label`);
  const error = (key: string) => (errors[key] ? t(`errors.${errors[key]}`) : undefined);
  const hintKey = (key: string) => `${scope}.${key}.hint`;

  return (
    <div className="grid gap-3 sm:grid-cols-2" data-testid={`${idPrefix}-attributes`}>
      {defs.map((def) => {
        const id = `${idPrefix}-${def.key.replace(".", "-")}`;
        const value = values[def.key] ?? emptyValue(def);
        const hint = t.has(hintKey(def.key)) ? t(hintKey(def.key)) : undefined;

        if (def.kind === "bool") {
          return (
            <label
              key={def.key}
              className="flex min-h-11 items-center gap-2 text-sm text-text sm:col-span-2"
            >
              <input
                type="checkbox"
                checked={value === true}
                disabled={disabled}
                data-testid={id}
                onChange={(event) => set(def.key, event.target.checked)}
              />
              {label(def.key)}
            </label>
          );
        }

        if (def.kind === "rows") {
          const rows = Array.isArray(value) ? (value as Row[]) : [];
          const update = (index: number, col: string, next: string) =>
            set(
              def.key,
              rows.map((row, i) => (i === index ? { ...row, [col]: next } : row)),
            );
          return (
            <div key={def.key} className="flex flex-col gap-2 sm:col-span-2" data-testid={id}>
              <p className="m-0 text-sm font-medium text-text">{label(def.key)}</p>
              {hint ? <p className="m-0 text-xs text-text-3">{hint}</p> : null}
              {rows.map((row, index) => (
                <div
                  key={index}
                  className="grid grid-cols-2 gap-2 rounded-md border border-border p-2 sm:grid-cols-3"
                >
                  {def.columns.map((col) => (
                    <FormField key={col.key} label={t(`${scope}.${def.key}.columns.${col.key}`)}>
                      {col.kind === "select" ? (
                        <Select
                          value={row[col.key] ?? ""}
                          disabled={disabled}
                          data-testid={`${id}-${index}-${col.key}`}
                          onChange={(event) => update(index, col.key, event.target.value)}
                        >
                          <option value="">{t("choose")}</option>
                          {col.options.map((option) => (
                            <option key={option} value={option}>
                              {t(`${scope}.${def.key}.columns.${col.key}Options.${option}`)}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <Input
                          value={row[col.key] ?? ""}
                          disabled={disabled}
                          inputMode={col.kind === "int" ? "numeric" : undefined}
                          placeholder={col.kind === "text" && col.time ? "HH:MM" : undefined}
                          data-testid={`${id}-${index}-${col.key}`}
                          onChange={(event) => update(index, col.key, event.target.value)}
                        />
                      )}
                    </FormField>
                  ))}
                  <Button
                    type="button"
                    variant="secondary"
                    loadingLabel={t("removeRow")}
                    disabled={disabled}
                    data-testid={`${id}-${index}-remove`}
                    onClick={() =>
                      set(
                        def.key,
                        rows.filter((_, i) => i !== index),
                      )
                    }
                  >
                    {t("removeRow")}
                  </Button>
                </div>
              ))}
              {error(def.key) ? <p className="m-0 text-sm text-danger">{error(def.key)}</p> : null}
              {rows.length < def.maxRows ? (
                <div>
                  <Button
                    type="button"
                    variant="secondary"
                    loadingLabel={t("addRow")}
                    disabled={disabled}
                    data-testid={`${id}-add`}
                    onClick={() =>
                      set(def.key, [
                        ...rows,
                        Object.fromEntries(def.columns.map((col) => [col.key, ""])),
                      ])
                    }
                  >
                    {t("addRow")}
                  </Button>
                </div>
              ) : null}
            </div>
          );
        }

        return (
          <FormField
            key={def.key}
            id={id}
            label={label(def.key)}
            helpText={hint}
            errorMessage={error(def.key)}
          >
            {def.kind === "select" ? (
              <Select
                id={id}
                value={typeof value === "string" ? value : ""}
                disabled={disabled}
                data-testid={id}
                onChange={(event) => set(def.key, event.target.value)}
              >
                <option value="">{t("choose")}</option>
                {def.options.map((option) => (
                  <option key={option} value={option}>
                    {t(`${scope}.${def.key}.options.${option}`)}
                  </option>
                ))}
              </Select>
            ) : def.kind === "image" ? (
              <Select
                id={id}
                value={typeof value === "string" ? value : ""}
                disabled={disabled || portfolioImages.length === 0}
                data-testid={id}
                onChange={(event) => set(def.key, event.target.value)}
              >
                <option value="">{t("noPhoto")}</option>
                {portfolioImages.map((publicId, index) => (
                  <option key={publicId} value={publicId}>
                    {t("photoOption", { position: index + 1 })}
                  </option>
                ))}
              </Select>
            ) : (
              <Input
                id={id}
                value={typeof value === "string" ? value : ""}
                disabled={disabled}
                inputMode={
                  def.kind === "int" ? "numeric" : def.kind === "money" ? "decimal" : undefined
                }
                placeholder={
                  def.kind === "text" && def.time
                    ? "HH:MM"
                    : def.kind === "tags"
                      ? t("tagsPlaceholder")
                      : undefined
                }
                data-testid={id}
                onChange={(event) => set(def.key, event.target.value)}
              />
            )}
          </FormField>
        );
      })}
    </div>
  );
}
