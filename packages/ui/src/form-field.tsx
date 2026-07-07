import { cloneElement, useId, type ReactElement, type ReactNode } from "react";

export interface FormFieldProps {
  id?: string;
  label: string;
  helpText?: string;
  errorMessage?: string;
  required?: boolean;
  requiredMarker?: string;
  children: ReactElement<{
    id?: string;
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
  children,
  className,
}: FormFieldProps) {
  const generatedId = useId();
  const fieldId = idProp ?? generatedId;
  const helpId = helpText ? `${fieldId}-help` : undefined;
  const errorId = errorMessage ? `${fieldId}-error` : undefined;

  const describedBy = [helpId, errorId].filter(Boolean).join(" ") || undefined;

  const control = cloneElement(children, {
    id: fieldId,
    "aria-describedby": describedBy,
    "aria-invalid": errorMessage ? true : children.props["aria-invalid"],
    "aria-required": required ? true : children.props["aria-required"],
  });

  return (
    <div className={cx("flex w-full flex-col gap-2", className)}>
      <label htmlFor={fieldId} className="font-body text-sm font-medium text-text">
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
