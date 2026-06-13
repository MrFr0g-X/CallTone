import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Turn a raw stored upload name (e.g. "8f2a1c-uuid_call_recording.wav") into a clean,
 * human-readable title: strips a leading UUID/hash prefix and the file extension.
 */
export function cleanCallTitle(filename?: string | null): string {
  if (!filename) return "Untitled Call";
  let base = filename.replace(/\.[a-z0-9]{2,4}$/i, "");
  base = base.replace(/^[0-9a-f]{6,}[-_]/i, "");
  base = base.replace(/[_-]+/g, " ").trim();
  if (!base) return "Call Recording";
  return base.charAt(0).toUpperCase() + base.slice(1);
}
