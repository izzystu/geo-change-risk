import { writable, derived } from 'svelte/store';
import type { ProcessingRunSummary, RiskEventSummary, AssetGeoJSON } from '$lib/services/api';

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
    showAcknowledged: true
});

// Derived: filtered risk events
export const filteredRiskEvents = derived(
    [riskEvents, riskEventFilters],
    ([$events, $filters]) => {
        return $events.filter(event => {
            if (event.riskScore < $filters.minScore) return false;
            if ($filters.riskLevel !== null && getRiskLevelValue(event.riskLevelName) !== $filters.riskLevel) return false;
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
