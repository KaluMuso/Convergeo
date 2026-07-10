export function playPickupSuccessHaptic(): void {
  if (typeof navigator === "undefined" || typeof navigator.vibrate !== "function") {
    return;
  }
  navigator.vibrate([40, 30, 40]);
}
