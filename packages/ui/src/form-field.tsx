import { cloneElement, useId, type ReactElement, type ReactNode } from "react";

export interface FormFieldProps {
  id?: string;
  label: string;
  helpText?: string;
  errorMessage?: string;
  required?: boolean;
  requiredMarker?: string;
  /**
   * Set when the child is a *group* of controls (e.g. country + number), not a single
   * labelable control. The child is then associated as `role="group"` via
   * `aria-labelledby` and does NOT receive `aria-required` — that attribute is invalid on
   * the generic/group role (axe `aria-allowed-attr`). Mark the required control(s) inside
   * the group with `aria-required` instead.
   */
  asGroup?: boolean;
  children: ReactElement<{
    id?: string;
    role?: string;
    "aria-labelledby"?: string;
    "aria-describedby"?: string;
    "aria-invalid"?: boolean;
    "aria-required"?: boolean;
  }>;
  className?: string;
}

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function FormField({
  id: idProp,
  label,
  helpText,
  errorMessage,
  required = false,
  requiredMarker,
  asGroup = false,
  children,
  className,
}: FormFieldProps) {
  const generatedId = useId();
  const fieldId = idProp ?? generatedId;
  const labelId = `${fieldId}-label`;
  const helpId = helpText ? `${fieldId}-help` : undefined;
  const errorId = errorMessage ? `${fieldId}-error` : undefined;

  const describedBy = [helpId, errorId].filter(Boolean).join(" ") || undefined;

  const control = asGroup
    ? cloneElement(children, {
        // A group of controls: label it via aria-labelledby and expose the group role.
        // aria-invalid is a global state (valid here); aria-required is NOT allowed on a
        // group — mark the required control(s) inside the group instead.
        role: "group",
        "aria-labelledby": labelId,
        "aria-describedby": describedBy,
        "aria-invalid": errorMessage ? true : children.props["aria-invalid"],
      })
    : cloneElement(children, {
        id: fieldId,
        "aria-describedby": describedBy,
        "aria-invalid": errorMessage ? true : children.props["aria-invalid"],
        "aria-required": required ? true : children.props["aria-required"],
      });

  return (
    <div className={cx("flex w-full flex-col gap-2", className)}>
      <label
        htmlFor={asGroup ? undefined : fieldId}
        id={asGroup ? labelId : undefined}
        className="font-body text-sm font-medium text-text"
      >
        {label}
        {required && requiredMarker ? (
          <span className="ms-1 text-danger" aria-hidden="true">
            {requiredMarker}
          </span>
        ) : null}
      </label>
      {control}
      {helpText ? (
        <p id={helpId} className="font-body text-sm text-text-2">
          {helpText}
        </p>
      ) : null}
      {errorMessage ? (
        <p id={errorId} role="alert" className="font-body text-sm text-danger">
          {errorMessage}
        </p>
      ) : null}
    </div>
  );
}

export type { ReactNode };
