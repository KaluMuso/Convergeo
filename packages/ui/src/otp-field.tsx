"use client";

import {
  useCallback,
  useId,
  useRef,
  type ClipboardEvent,
  type KeyboardEvent,
  useEffect,
} from "react";

const OTP_LENGTH = 6;

export interface OtpFieldProps {
  value?: string;
  defaultValue?: string;
  onChange?: (value: string) => void;
  onComplete?: (code: string) => void;
  disabled?: boolean;
  ariaLabel: string;
  getDigitAriaLabel: (index: number) => string;
  className?: string;
}

function cx(...parts: Array<string | false | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

function digitsOnly(value: string): string {
  return value.replace(/\D/g, "");
}

function normalizeOtp(value: string): string {
  return digitsOnly(value).slice(0, OTP_LENGTH);
}

function splitOtp(value: string): string[] {
  const normalized = normalizeOtp(value);
  return Array.from({ length: OTP_LENGTH }, (_, index) => normalized[index] ?? "");
}

export function OtpField({
  value,
  defaultValue = "",
  onChange,
  onComplete,
  disabled = false,
  ariaLabel,
  getDigitAriaLabel,
  className,
}: OtpFieldProps) {
  const groupId = useId();
  const inputRefs = useRef<Array<HTMLInputElement | null>>([]);
  const isControlled = value !== undefined;
  const completedRef = useRef<string | null>(null);

  const currentValue = isControlled ? normalizeOtp(value) : undefined;

  const setValue = useCallback(
    (next: string) => {
      const normalized = normalizeOtp(next);
      onChange?.(normalized);
      if (normalized.length === OTP_LENGTH && completedRef.current !== normalized) {
        completedRef.current = normalized;
        onComplete?.(normalized);
      }
      if (normalized.length < OTP_LENGTH) {
        completedRef.current = null;
      }
      return normalized;
    },
    [onChange, onComplete],
  );

  const focusIndex = useCallback((index: number) => {
    const clamped = Math.max(0, Math.min(OTP_LENGTH - 1, index));
    inputRefs.current[clamped]?.focus();
    inputRefs.current[clamped]?.select();
  }, []);

  const applyDigits = useCallback(
    (startIndex: number, digitString: string) => {
      const source = isControlled
        ? (currentValue ?? "")
        : normalizeOtp(inputRefs.current.map((input) => input?.value ?? "").join(""));
      const chars = splitOtp(source);
      const incoming = digitsOnly(digitString);

      for (let offset = 0; offset < incoming.length; offset += 1) {
        const targetIndex = startIndex + offset;
        if (targetIndex >= OTP_LENGTH) {
          break;
        }
        const digit = incoming[offset];
        if (digit) {
          chars[targetIndex] = digit;
        }
      }

      const next = chars.join("");
      if (!isControlled) {
        chars.forEach((digit, index) => {
          const input = inputRefs.current[index];
          if (input) {
            input.value = digit;
          }
        });
      }
      const normalized = setValue(next);
      const nextFocus = Math.min(startIndex + incoming.length, OTP_LENGTH - 1);
      focusIndex(normalized.length === OTP_LENGTH ? OTP_LENGTH - 1 : nextFocus);
    },
    [currentValue, focusIndex, isControlled, setValue],
  );

  const handleInput = (index: number, nextDigit: string) => {
    const digit = digitsOnly(nextDigit).slice(-1);
    applyDigits(index, digit);
  };

  const handleKeyDown = (index: number, event: KeyboardEvent<HTMLInputElement>) => {
    const input = event.currentTarget;
    const source = isControlled
      ? splitOtp(currentValue ?? "")
      : splitOtp(inputRefs.current.map((el) => el?.value ?? "").join(""));

    if (event.key === "Backspace") {
      event.preventDefault();
      if (source[index]) {
        const chars = [...source];
        chars[index] = "";
        const next = chars.join("");
        if (!isControlled) {
          input.value = "";
        }
        setValue(next);
        focusIndex(index);
        return;
      }
      if (index > 0) {
        const chars = [...source];
        chars[index - 1] = "";
        const next = chars.join("");
        if (!isControlled) {
          const previous = inputRefs.current[index - 1];
          if (previous) {
            previous.value = "";
          }
        }
        setValue(next);
        focusIndex(index - 1);
      }
      return;
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      focusIndex(index - 1);
      return;
    }

    if (event.key === "ArrowRight") {
      event.preventDefault();
      focusIndex(index + 1);
    }
  };

  const handlePaste = (index: number, event: ClipboardEvent<HTMLInputElement>) => {
    event.preventDefault();
    const pasted = event.clipboardData.getData("text");
    if (!pasted) {
      return;
    }
    applyDigits(index, pasted);
  };

  useEffect(() => {
    if (!isControlled) {
      return;
    }
    const cells = splitOtp(currentValue ?? "");
    cells.forEach((digit, index) => {
      const input = inputRefs.current[index];
      if (input && input.value !== digit) {
        input.value = digit;
      }
    });
  }, [currentValue, isControlled]);

  const initialCells = splitOtp(isControlled ? (currentValue ?? "") : defaultValue);

  return (
    <div
      id={groupId}
      role="group"
      aria-label={ariaLabel}
      className={cx("flex w-full max-w-full gap-2", className)}
    >
      {initialCells.map((digit, index) => (
        <input
          key={index}
          ref={(element) => {
            inputRefs.current[index] = element;
          }}
          type="text"
          inputMode="numeric"
          autoComplete={index === 0 ? "one-time-code" : "off"}
          pattern="[0-9]*"
          maxLength={1}
          defaultValue={isControlled ? undefined : digit}
          disabled={disabled}
          aria-label={getDigitAriaLabel(index)}
          className={cx(
            "size-11 min-h-11 min-w-11 flex-1 rounded bg-surface text-center font-mono text-body text-text",
            "border border-border",
            "transition-[border-color,box-shadow] duration-fast ease-std",
            "motion-reduce:transition-none",
            "focus-visible:outline-none focus-visible:shadow-focusRing",
            "disabled:cursor-not-allowed disabled:bg-bg-2 disabled:text-text-3",
          )}
          onChange={(event) => handleInput(index, event.target.value)}
          onKeyDown={(event) => handleKeyDown(index, event)}
          onPaste={(event) => handlePaste(index, event)}
        />
      ))}
    </div>
  );
}
