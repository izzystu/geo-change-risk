import { writable } from 'svelte/store';
import type { LidarSourceDetail } from '$lib/services/api';

// Data stores
export const selectedLidarSource = writable<LidarSourceDetail | null>(null);

// UI state
export const showLidarViewer = writable(false);
export const lidarLoading = writable(false);
export const lidarError = writable<string | null>(null);

// Per-polygon context: set when viewing terrain from a change polygon popup
export const viewingPolygonId = writable<string | null>(null);
