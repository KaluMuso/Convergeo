import { buttonBaseClasses, buttonSizeClasses, buttonVariantClasses } from "@vergeo/ui/src/button";

/** Primary CTA class map — use instead of `bg-primary text-white` (broken in dark mode). */
export const adminPrimaryButtonClass = [
  buttonBaseClasses,
  buttonVariantClasses.primary,
  buttonSizeClasses.md,
].join(" ");

export const adminPrimaryButtonSmClass = [
  buttonBaseClasses,
  buttonVariantClasses.primary,
  buttonSizeClasses.sm,
].join(" ");
