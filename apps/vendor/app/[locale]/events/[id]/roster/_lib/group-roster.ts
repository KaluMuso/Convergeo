import type { RosterAttendee } from "./roster-client";

export type DateGroup = {
  instanceId: string;
  startsAt: string;
  attendees: RosterAttendee[];
};

/**
 * Group roster rows into one section per event instance, preserving the API's
 * ordering (attendees arrive ordered by date → type → name). The first row seen
 * for an instance fixes the section's position and `startsAt`.
 */
export function groupByInstance(attendees: RosterAttendee[]): DateGroup[] {
  const groups: DateGroup[] = [];
  const index = new Map<string, DateGroup>();
  for (const attendee of attendees) {
    let group = index.get(attendee.instance_id);
    if (!group) {
      group = {
        instanceId: attendee.instance_id,
        startsAt: attendee.starts_at,
        attendees: [],
      };
      index.set(attendee.instance_id, group);
      groups.push(group);
    }
    group.attendees.push(attendee);
  }
  return groups;
}
