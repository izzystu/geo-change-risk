import { writable } from 'svelte/store';
import type { AreaOfInterestSummary, AreaOfInterest } from '$lib/services/api';

// List of available AOIs (summary)
export const areasOfInterest = writable<AreaOfInterestSummary[]>([]);

// Currently selected AOI ID
export const selectedAoiId = writable<string | null>(null);

// Full details of the selected AOI (fetched when selected)
export const selectedAoi = writable<AreaOfInterest | null>(null);

// Loading state
export const aoiLoading = writable(false);
export const aoiError = writable<string | null>(null);

// Zoom trigger - increment to request zoom to current AOI
export const zoomToAoiTrigger = writable(0);
export function requestZoomToAoi() {
	zoomToAoiTrigger.update(n => n + 1);
}
