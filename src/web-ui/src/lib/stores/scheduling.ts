import { writable } from 'svelte/store';
import { api, type AreaOfInterest, type UpdateAoiScheduleRequest, type ProcessingRunSummary } from '$lib/services/api';

// Schedule configuration for the selected AOI
export interface ScheduleConfig {
	processingSchedule: string | null;
	processingEnabled: boolean;
	maxCloudCover: number;
	defaultLookbackDays: number;
	lastCheckedAt: string | null;
	lastProcessedAt: string | null;
}

export const scheduleConfig = writable<ScheduleConfig>({
	processingSchedule: null,
	processingEnabled: false,
	maxCloudCover: 20,
	defaultLookbackDays: 90,
	lastCheckedAt: null,
	lastProcessedAt: null
});

export const scheduleSaving = writable(false);
export const scheduleError = writable<string | null>(null);

// Scheduled processing runs (triggered_by == "scheduled_check")
export const scheduledRuns = writable<ProcessingRunSummary[]>([]);

// Cron presets
export const cronPresets = [
	{ label: 'Every 6 hours', cron: '0 */6 * * *' },
	{ label: 'Daily at 6 AM UTC', cron: '0 6 * * *' },
	{ label: 'Twice weekly (Mon/Thu)', cron: '0 6 * * 1,4' },
	{ label: 'Weekly (Monday)', cron: '0 6 * * 1' }
];

/** Load schedule from an AOI object */
export function loadScheduleFromAoi(aoi: AreaOfInterest) {
	scheduleConfig.set({
		processingSchedule: aoi.processingSchedule,
		processingEnabled: aoi.processingEnabled,
		maxCloudCover: aoi.maxCloudCover,
		defaultLookbackDays: aoi.defaultLookbackDays,
		lastCheckedAt: aoi.lastCheckedAt,
		lastProcessedAt: aoi.lastProcessedAt
	});
	scheduleError.set(null);
}

/** Save schedule to API and update store */
export async function saveSchedule(aoiId: string, request: UpdateAoiScheduleRequest): Promise<AreaOfInterest> {
	scheduleSaving.set(true);
	scheduleError.set(null);
	try {
		const updated = await api.updateAoiSchedule(aoiId, request);
		loadScheduleFromAoi(updated);
		return updated;
	} catch (e) {
		const msg = e instanceof Error ? e.message : 'Failed to save schedule';
		scheduleError.set(msg);
		throw e;
	} finally {
		scheduleSaving.set(false);
	}
}

/** Reset schedule state */
export function resetScheduleState() {
	scheduleConfig.set({
		processingSchedule: null,
		processingEnabled: false,
		maxCloudCover: 20,
		defaultLookbackDays: 90,
		lastCheckedAt: null,
		lastProcessedAt: null
	});
	scheduledRuns.set([]);
	scheduleError.set(null);
}

/** Get human-readable description of a cron expression */
export function describeCron(cron: string | null): string {
	if (!cron) return 'Not scheduled';
	const preset = cronPresets.find(p => p.cron === cron);
	if (preset) return preset.label;
	return `Custom (${cron})`;
}

/** Format a relative time string like "2 hours ago" */
export function timeAgo(dateStr: string | null): string {
	if (!dateStr) return 'Never';
	const date = new Date(dateStr);
	const now = new Date();
	const diffMs = now.getTime() - date.getTime();
	const diffMins = Math.floor(diffMs / 60000);
	if (diffMins < 1) return 'Just now';
	if (diffMins < 60) return `${diffMins}m ago`;
	const diffHours = Math.floor(diffMins / 60);
	if (diffHours < 24) return `${diffHours}h ago`;
	const diffDays = Math.floor(diffHours / 24);
	return `${diffDays}d ago`;
}
