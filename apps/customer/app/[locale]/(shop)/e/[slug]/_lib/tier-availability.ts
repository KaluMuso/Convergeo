/** Show tier scarcity copy only when cap is set and ≤20 remain (honest urgency). */
export function tierSpotsRemaining(qtyCap: number | null, ticketsSold: number): number | null {
  if (qtyCap === null) {
    return null;
  }
  const remaining = Math.max(0, qtyCap - ticketsSold);
  return remaining <= 20 ? remaining : null;
}

export function splitTicketPerks(perks: string | null | undefined): string[] {
  if (!perks) {
    return [];
  }
  return perks
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}
