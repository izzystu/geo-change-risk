import { writable, derived } from 'svelte/store';
import type { ProcessingRunSummary, RiskEventSummary, AssetGeoJSON } from '$lib/services/api';
import { queryResultEventIds } from '$lib/stores/query';

// Processing runs for the current AOI
export const processingRuns = writable<ProcessingRunSummary[]>([]);

// Currently selected processing run
export const selectedRunId = writable<string | null>(null);

// Change polygons GeoJSON for the selected run
export const changePolygonsGeoJson = writable<AssetGeoJSON | null>(null);

// Whether to show change polygons on the map
export const showChangePolygons = writable<boolean>(true);

// Risk events for current AOI
export const riskEvents = writable<RiskEventSummary[]>([]);

// Unacknowledged count for badge display
export const unacknowledgedCount = writable<number>(0);

// Loading states
export const runsLoading = writable(false);
export const eventsLoading = writable(false);
export const processingError = writable<string | null>(null);

// Filter state for risk events
export const riskEventFilters = writable({
    minScore: 0,
    riskLevel: null as number | null,
    assetType: null as string | null,
    showAcknowledged: true
});

// Derived: unique asset type names from current events
export const assetTypes = derived(riskEvents, ($events) => {
    const types = new Set($events.map(e => e.assetTypeName));
    return [...types].sort();
});

// Derived: filtered risk events
export const filteredRiskEvents = derived(
    [riskEvents, riskEventFilters, queryResultEventIds],
    ([$events, $filters, $queryIds]) => {
        return $events.filter(event => {
            if ($queryIds !== null && !$queryIds.has(event.riskEventId)) return false;
            if (event.isDismissed) return false;
            if (event.riskScore < $filters.minScore) return false;
            if ($filters.riskLevel !== null && getRiskLevelValue(event.riskLevelName) !== $filters.riskLevel) return false;
            if ($filters.assetType !== null && event.assetTypeName !== $filters.assetType) return false;
            if (!$filters.showAcknowledged && event.isAcknowledged) return false;
            return true;
        });
    }
);

// Derived: high-priority events (Critical and High)
export const highPriorityEvents = derived(riskEvents, ($events) => {
    return $events.filter(e =>
        e.riskLevelName === 'Critical' || e.riskLevelName === 'High'
    );
});

function getRiskLevelValue(levelName: string): number {
    const levels: Record<string, number> = {
        'Low': 0,
        'Medium': 1,
        'High': 2,
        'Critical': 3
    };
    return levels[levelName] ?? 0;
}

// Reset processing state when AOI changes
export function resetProcessingState() {
    processingRuns.set([]);
    selectedRunId.set(null);
    changePolygonsGeoJson.set(null);
    riskEvents.set([]);
    unacknowledgedCount.set(0);
    processingError.set(null);
}
