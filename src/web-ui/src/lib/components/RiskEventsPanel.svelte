<script lang="ts">
	import { selectedAoiId } from '$lib/stores/aoi';
	import {
		riskEvents,
		unacknowledgedCount,
		eventsLoading,
		processingError,
		filteredRiskEvents,
		riskEventFilters
	} from '$lib/stores/processing';
	import { api, RiskLevelColors } from '$lib/services/api';

	export let onEventClick: ((eventId: string) => void) | undefined = undefined;

	let acknowledgingId: string | null = null;

	const riskLevels = [
		{ value: null, label: 'All' },
		{ value: 3, label: 'Critical' },
		{ value: 2, label: 'High' },
		{ value: 1, label: 'Medium' },
		{ value: 0, label: 'Low' }
	];

	// Load events when AOI changes
	$: if ($selectedAoiId) {
		loadEvents($selectedAoiId);
	}

	async function loadEvents(aoiId: string) {
		eventsLoading.set(true);

		try {
			const [events, unackEvents] = await Promise.all([
				api.getRiskEvents({ aoiId, limit: 500 }),
				api.getUnacknowledgedEvents(aoiId, 2)  // High+ risk only
			]);

			riskEvents.set(events);
			unacknowledgedCount.set(unackEvents.length);
		} catch (err) {
			console.error('Failed to load risk events:', err);
			processingError.set('Failed to load risk events');
		} finally {
			eventsLoading.set(false);
		}
	}

	function formatDistance(meters: number): string {
		if (meters < 1000) {
			return `${Math.round(meters)}m`;
		}
		return `${(meters / 1000).toFixed(1)}km`;
	}

	function formatDate(dateStr: string): string {
		const date = new Date(dateStr);
		return date.toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function handleEventClick(eventId: string) {
		if (onEventClick) {
			onEventClick(eventId);
		}
	}

	async function handleAcknowledge(event: Event, eventId: string) {
		event.stopPropagation(); // Prevent triggering the zoom click
		acknowledgingId = eventId;

		try {
			await api.acknowledgeRiskEvent(eventId, 'User');

			// Update the local state
			riskEvents.update(events =>
				events.map(e =>
					e.riskEventId === eventId ? { ...e, isAcknowledged: true } : e
				)
			);

			// Decrement unacknowledged count
			unacknowledgedCount.update(n => Math.max(0, n - 1));
		} catch (err) {
			console.error('Failed to acknowledge event:', err);
		} finally {
			acknowledgingId = null;
		}
	}

	function setRiskLevelFilter(level: number | null) {
		riskEventFilters.update(f => ({ ...f, riskLevel: level }));
	}
</script>

<div class="risk-events-panel">
	<div class="header">
		<h3>
			Risk Events
			{#if $unacknowledgedCount > 0}
				<span class="unack-badge">{$unacknowledgedCount}</span>
			{/if}
		</h3>
	</div>

	{#if !$selectedAoiId}
		<p class="empty-state">Select an AOI to view events</p>
	{:else if $eventsLoading}
		<p class="loading">Loading events...</p>
	{:else if $riskEvents.length === 0}
		<p class="empty-state">No risk events detected</p>
	{:else}
		<div class="filters">
			<div class="filter-row">
				<span class="filter-label">Risk Level:</span>
				<div class="risk-level-buttons">
					{#each riskLevels as level}
						<button
							class="level-btn"
							class:active={$riskEventFilters.riskLevel === level.value}
							style={level.value !== null ? `--level-color: ${RiskLevelColors[level.label]}` : ''}
							on:click={() => setRiskLevelFilter(level.value)}
						>
							{level.label}
						</button>
					{/each}
				</div>
			</div>
			<label class="filter-item">
				<span>Min Score:</span>
				<input
					type="range"
					min="0"
					max="100"
					step="10"
					bind:value={$riskEventFilters.minScore}
				/>
				<span class="filter-value">{$riskEventFilters.minScore}</span>
			</label>
			<label class="filter-item checkbox">
				<input
					type="checkbox"
					bind:checked={$riskEventFilters.showAcknowledged}
				/>
				<span>Show acknowledged</span>
			</label>
		</div>

		<div class="events-list">
			{#each $filteredRiskEvents as event}
				<button
					class="event-item"
					class:acknowledged={event.isAcknowledged}
					on:click={() => handleEventClick(event.riskEventId)}
					title="Click to zoom to location"
				>
					<div class="event-header">
						<span
							class="risk-badge"
							style="background-color: {RiskLevelColors[event.riskLevelName]}"
						>
							{event.riskScore}
						</span>
						<span class="risk-level">{event.riskLevelName}</span>
						{#if event.isAcknowledged}
							<span class="ack-icon" title="Acknowledged">✓</span>
						{:else}
							<button
								class="ack-btn"
								title="Mark as acknowledged"
								disabled={acknowledgingId === event.riskEventId}
								on:click={(e) => handleAcknowledge(e, event.riskEventId)}
							>
								{acknowledgingId === event.riskEventId ? '...' : '✓'}
							</button>
						{/if}
					</div>
					<div class="event-asset">
						<span class="asset-name">{event.assetName}</span>
						<span class="asset-type">{event.assetTypeName}</span>
					</div>
					<div class="event-details">
						<span class="distance">{formatDistance(event.distanceMeters)}</span>
						<span class="date">{formatDate(event.createdAt)}</span>
					</div>
				</button>
			{/each}

			{#if $filteredRiskEvents.length === 0}
				<p class="empty-state">No events match filters</p>
			{/if}
		</div>

		<div class="summary">
			Showing {$filteredRiskEvents.length} of {$riskEvents.length} events
		</div>
	{/if}
</div>

<style>
	.risk-events-panel {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	h3 {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--color-text);
		margin: 0;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.unack-badge {
		font-size: 0.625rem;
		padding: 0.125rem 0.375rem;
		background: #ef4444;
		color: white;
		border-radius: 999px;
		font-weight: 600;
	}

	.empty-state, .loading {
		font-size: 0.8125rem;
		color: var(--color-text-muted);
		font-style: italic;
	}

	.filters {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		padding: 0.5rem;
		background: var(--color-bg);
		border-radius: var(--radius-sm);
	}

	.filter-item {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	.filter-item input[type="range"] {
		flex: 1;
		height: 0.25rem;
	}

	.filter-value {
		min-width: 2rem;
		text-align: right;
	}

	.filter-item.checkbox {
		cursor: pointer;
	}

	.filter-item.checkbox input {
		width: 0.875rem;
		height: 0.875rem;
	}

	.events-list {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		max-height: 300px;
		overflow-y: auto;
	}

	.event-item {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding: 0.5rem;
		background: var(--color-bg);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		cursor: pointer;
		text-align: left;
		width: 100%;
	}

	.event-item:hover {
		border-color: var(--color-text-muted);
	}

	.event-item.acknowledged {
		opacity: 0.6;
	}

	.event-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.risk-badge {
		font-size: 0.6875rem;
		padding: 0.125rem 0.375rem;
		border-radius: var(--radius-sm);
		color: white;
		font-weight: 600;
		min-width: 1.75rem;
		text-align: center;
	}

	.risk-level {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--color-text);
	}

	.ack-icon {
		margin-left: auto;
		color: #22c55e;
		font-size: 0.75rem;
	}

	.ack-btn {
		margin-left: auto;
		width: 1.5rem;
		height: 1.5rem;
		border-radius: var(--radius-sm);
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		color: var(--color-text-muted);
		cursor: pointer;
		font-size: 0.75rem;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.15s ease;
	}

	.ack-btn:hover:not(:disabled) {
		background: #22c55e;
		border-color: #22c55e;
		color: white;
	}

	.ack-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.filter-row {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.filter-label {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	.risk-level-buttons {
		display: flex;
		gap: 0.25rem;
		flex-wrap: wrap;
	}

	.level-btn {
		font-size: 0.625rem;
		padding: 0.125rem 0.375rem;
		border-radius: var(--radius-sm);
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		color: var(--color-text-muted);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.level-btn:hover {
		border-color: var(--color-text-muted);
	}

	.level-btn.active {
		background: var(--level-color, var(--color-text));
		border-color: var(--level-color, var(--color-text));
		color: white;
	}

	.event-asset {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.asset-name {
		font-size: 0.8125rem;
		color: var(--color-text);
		font-weight: 500;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		max-width: 60%;
	}

	.asset-type {
		font-size: 0.6875rem;
		color: var(--color-text-muted);
	}

	.event-details {
		display: flex;
		justify-content: space-between;
		font-size: 0.6875rem;
		color: var(--color-text-muted);
	}

	.summary {
		font-size: 0.6875rem;
		color: var(--color-text-muted);
		text-align: center;
		padding-top: 0.25rem;
		border-top: 1px solid var(--color-border);
	}
</style>
