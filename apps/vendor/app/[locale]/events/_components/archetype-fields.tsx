"use client";

import {
  ARCHETYPE_SECTIONS,
  type DetailSection,
  type EventArchetype,
} from "@vergeo/ui/src/event-archetype";
import { useTranslations } from "next-intl";

import {
  DIETARY_OPTIONS,
  LINE_SPECS,
  LIST_SPECS,
  MENU_LIMITS,
  SCALAR_SPECS,
  type DetailsDraft,
  type FieldSpec,
  type MenuSectionRow,
  type Row,
} from "../_lib/archetype-draft";
import { Button, FormField, Input, Select } from "../_lib/ui";

type Props = {
  archetype: EventArchetype;
  draft: DetailsDraft;
  onChange: (next: DetailsDraft) => void;
  disabled?: boolean;
};

const textareaClass =
  "min-h-20 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm";

type Translate = (key: string) => string;

function FieldInput({
  spec,
  label,
  value,
  onChange,
  disabled,
  t,
}: {
  spec: FieldSpec;
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  t: Translate;
}) {
  return (
    <FormField label={label} required={spec.required} requiredMarker="*">
      {spec.kind === "textarea" ? (
        <textarea
          className={textareaClass}
          value={value}
          maxLength={spec.max}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        />
      ) : spec.kind === "select" ? (
        <Select
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">{t("archetype.none")}</option>
          {(spec.options ?? []).map((option) => (
            <option key={option} value={option}>
              {t(`archetype.options.${spec.key}.${option}`)}
            </option>
          ))}
        </Select>
      ) : (
        <Input
          type={spec.kind === "time" ? "time" : spec.kind === "number" ? "number" : "text"}
          inputMode={spec.kind === "number" ? "numeric" : undefined}
          min={spec.kind === "number" ? 0 : undefined}
          max={spec.kind === "number" ? 120 : undefined}
          maxLength={spec.kind === "text" ? spec.max : undefined}
          value={value}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        />
      )}
    </FormField>
  );
}

function RowEditor({
  section,
  rows,
  fields,
  max,
  onChange,
  disabled,
  t,
}: {
  section: string;
  rows: Row[];
  fields: FieldSpec[];
  max: number;
  onChange: (rows: Row[]) => void;
  disabled?: boolean;
  t: Translate;
}) {
  return (
    <div className="flex flex-col gap-3">
      {rows.map((row, index) => (
        <div
          key={index}
          className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-3"
          data-testid={`row-${section}-${index}`}
        >
          {section === "sponsors" ? (
            <p
              className="text-xs text-text-2"
              data-testid={`sponsor-status-${index}`}
              data-status={row.status || "pending"}
            >
              <span className="font-semibold">
                {t(`archetype.sponsorStatus.${row.status || "pending"}`)}
              </span>{" "}
              {t("archetype.sponsorReviewNote")}
            </p>
          ) : null}
          {fields.map((field) => (
            <FieldInput
              key={field.key}
              spec={{ ...field, key: field.key }}
              label={t(`archetype.fields.${section}.${field.key}`)}
              value={row[field.key] ?? ""}
              disabled={disabled}
              t={t}
              onChange={(value) =>
                onChange(rows.map((r, i) => (i === index ? { ...r, [field.key]: value } : r)))
              }
            />
          ))}
          <Button
            loadingLabel={t("archetype.remove")}
            type="button"
            variant="ghost"
            size="sm"
            disabled={disabled}
            onClick={() => onChange(rows.filter((_, i) => i !== index))}
          >
            {t("archetype.remove")}
          </Button>
        </div>
      ))}
      {rows.length < max ? (
        <Button
          type="button"
          loadingLabel={t("archetype.remove")}
          variant="secondary"
          size="sm"
          disabled={disabled}
          onClick={() => onChange([...rows, Object.fromEntries(fields.map((f) => [f.key, ""]))])}
        >
          {t(`archetype.add.${section}`)}
        </Button>
      ) : null}
    </div>
  );
}

function MenuEditor({
  menu,
  onChange,
  disabled,
  t,
}: {
  menu: MenuSectionRow[];
  onChange: (menu: MenuSectionRow[]) => void;
  disabled?: boolean;
  t: Translate;
}) {
  const setSection = (index: number, next: MenuSectionRow) =>
    onChange(menu.map((s, i) => (i === index ? next : s)));
  return (
    <div className="flex flex-col gap-3" data-testid="menu-editor">
      {menu.map((section, si) => (
        <div
          key={si}
          className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-3"
        >
          <FormField label={t("archetype.fields.menu_sections.title")} required requiredMarker="*">
            <Input
              value={section.title}
              maxLength={80}
              disabled={disabled}
              onChange={(event) => setSection(si, { ...section, title: event.target.value })}
            />
          </FormField>
          {section.items.map((item, ii) => (
            <div key={ii} className="flex flex-col gap-2 rounded-md bg-bg-2 p-2">
              <FormField label={t("archetype.fields.menu_sections.name")}>
                <Input
                  value={item.name}
                  maxLength={80}
                  disabled={disabled}
                  onChange={(event) =>
                    setSection(si, {
                      ...section,
                      items: section.items.map((it, i) =>
                        i === ii ? { ...it, name: event.target.value } : it,
                      ),
                    })
                  }
                />
              </FormField>
              <FormField label={t("archetype.fields.menu_sections.description")}>
                <Input
                  value={item.description}
                  maxLength={160}
                  disabled={disabled}
                  onChange={(event) =>
                    setSection(si, {
                      ...section,
                      items: section.items.map((it, i) =>
                        i === ii ? { ...it, description: event.target.value } : it,
                      ),
                    })
                  }
                />
              </FormField>
              <FormField
                label={t("archetype.fields.menu_sections.price")}
                helpText={t("archetype.fields.menu_sections.priceHelp")}
              >
                <Input
                  inputMode="decimal"
                  value={item.price}
                  disabled={disabled}
                  onChange={(event) =>
                    setSection(si, {
                      ...section,
                      items: section.items.map((it, i) =>
                        i === ii ? { ...it, price: event.target.value } : it,
                      ),
                    })
                  }
                />
              </FormField>
              <FormField label={t("archetype.fields.menu_sections.dietary")}>
                <Input
                  value={item.dietary}
                  disabled={disabled}
                  placeholder={DIETARY_OPTIONS.join(", ")}
                  onChange={(event) =>
                    setSection(si, {
                      ...section,
                      items: section.items.map((it, i) =>
                        i === ii ? { ...it, dietary: event.target.value } : it,
                      ),
                    })
                  }
                />
              </FormField>
              <Button
                type="button"
                loadingLabel={t("archetype.remove")}
                variant="ghost"
                size="sm"
                disabled={disabled}
                onClick={() =>
                  setSection(si, {
                    ...section,
                    items: section.items.filter((_, i) => i !== ii),
                  })
                }
              >
                {t("archetype.remove")}
              </Button>
            </div>
          ))}
          <div className="flex gap-2">
            {section.items.length < MENU_LIMITS.items ? (
              <Button
                type="button"
                loadingLabel={t("archetype.remove")}
                variant="secondary"
                size="sm"
                disabled={disabled}
                onClick={() =>
                  setSection(si, {
                    ...section,
                    items: [
                      ...section.items,
                      { name: "", description: "", price: "", dietary: "" },
                    ],
                  })
                }
              >
                {t("archetype.add.menu_item")}
              </Button>
            ) : null}
            <Button
              type="button"
              loadingLabel={t("archetype.remove")}
              variant="ghost"
              size="sm"
              disabled={disabled}
              onClick={() => onChange(menu.filter((_, i) => i !== si))}
            >
              {t("archetype.remove")}
            </Button>
          </div>
        </div>
      ))}
      {menu.length < MENU_LIMITS.sections ? (
        <Button
          type="button"
          loadingLabel={t("archetype.remove")}
          variant="secondary"
          size="sm"
          disabled={disabled}
          onClick={() =>
            onChange([
              ...menu,
              {
                title: "",
                items: [{ name: "", description: "", price: "", dietary: "" }],
              },
            ])
          }
        >
          {t("archetype.add.menu_sections")}
        </Button>
      ) : null}
    </div>
  );
}

/**
 * Archetype-specific optional fields. Which sections appear comes from
 * `ARCHETYPE_SECTIONS`, so the form adapts when the page style changes. Nothing here
 * touches ticketing or payments.
 */
export function ArchetypeFields({ archetype, draft, onChange, disabled }: Props) {
  const tv = useTranslations("vendor");
  const t: Translate = (key) => tv(`events.${key}` as never);
  const sections = ARCHETYPE_SECTIONS[archetype];

  return (
    <div className="flex flex-col gap-4" data-testid="archetype-fields" data-archetype={archetype}>
      <div>
        <h2 className="text-sm font-semibold text-text">{t("archetype.heading")}</h2>
        <p className="mt-1 text-xs text-text-2">{t("archetype.help")}</p>
        {archetype === "restaurant" ? (
          <p className="mt-2 text-xs text-text-2" data-testid="restaurant-tables-hint">
            {t("archetype.restaurantTables")}
          </p>
        ) : null}
      </div>

      {sections.map((section) => {
        const scalar = SCALAR_SPECS[section];
        const list = LIST_SPECS[section];
        const line = LINE_SPECS[section];
        if (scalar) {
          return (
            <FieldInput
              key={section}
              spec={scalar}
              label={t(`archetype.fields.${section}`)}
              value={draft.scalars[section] ?? ""}
              disabled={disabled}
              t={t}
              onChange={(value) =>
                onChange({
                  ...draft,
                  scalars: { ...draft.scalars, [section]: value },
                })
              }
            />
          );
        }
        if (list) {
          return (
            <fieldset key={section} className="flex flex-col gap-2">
              <legend className="mb-1 text-sm font-medium text-text">
                {t(`archetype.sections.${section}`)}
              </legend>
              <RowEditor
                section={section}
                rows={draft.rows[section] ?? []}
                fields={list.fields}
                max={list.max}
                disabled={disabled}
                t={t}
                onChange={(rows) =>
                  onChange({
                    ...draft,
                    rows: { ...draft.rows, [section]: rows },
                  })
                }
              />
            </fieldset>
          );
        }
        if (line) {
          return (
            <FormField
              key={section}
              label={t(`archetype.sections.${section}`)}
              helpText={t("archetype.onePerLine")}
            >
              <textarea
                className={textareaClass}
                value={draft.lines[section] ?? ""}
                disabled={disabled}
                onChange={(event) =>
                  onChange({
                    ...draft,
                    lines: { ...draft.lines, [section]: event.target.value },
                  })
                }
              />
            </FormField>
          );
        }
        if (section === "menu_sections") {
          return (
            <fieldset key={section} className="flex flex-col gap-2">
              <legend className="mb-1 text-sm font-medium text-text">
                {t("archetype.sections.menu_sections")}
              </legend>
              <MenuEditor
                menu={draft.menu}
                disabled={disabled}
                t={t}
                onChange={(menu) => onChange({ ...draft, menu })}
              />
            </fieldset>
          );
        }
        return null;
      })}
    </div>
  );
}
