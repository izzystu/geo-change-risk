<script lang="ts">
	import { selectedAoiId } from '$lib/stores/aoi';
	import {
		riskEvents,
		selectedRunId,
		unacknowledgedCount,
		eventsLoading,
		processingError,
		filteredRiskEvents,
		riskEventFilters,
		assetTypes
	} from '$lib/stores/processing';
	import { queryResultEventIds } from '$lib/stores/query';
	import { api, RiskLevelColors, type RiskEvent, type RiskEventSummary } from '$lib/services/api';
	import { parseFactors, generateSummary, generateSuggestedAction, getFactorBarColor } from '$lib/utils/riskSummary';
	import TakeActionDialog from './TakeActionDialog.svelte';

	export let onEventClick: ((eventId: string | null) => void) | undefined = undefined;

	let expandedEventId: string | null = null;
	let expandedEventDetail: RiskEvent | null = null;
	let dismissingId: string | null = null;

	// Take Action dialog state
	let actionDialogOpen = false;
	let actionDialogEvent: RiskEventSummary | null = null;
	let actionDialogDetail: RiskEvent | null = null;

	const riskLevels = [
		{ value: null, label: 'All' },
		{ value: 3, label: 'Critical' },
		{ value: 2, label: 'High' },
		{ value: 1, label: 'Medium' },
		{ value: 0, label: 'Low' }
	];

	// Load events when AOI or selected run changes
	$: if ($selectedAoiId) {
		loadEvents($selectedAoiId, $selectedRunId);
	}

	async function loadEvents(aoiId: string, runId: string | null) {
		eventsLoading.set(true);
		expandedEventId = null;
		expandedEventDetail = null;

		try {
			const events = await api.getRiskEvents({ aoiId, runId: runId ?? undefined, limit: 500 });

			riskEvents.set(events);
			unacknowledgedCount.set(events.filter(e => !e.isAcknowledged).length);
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

	async function handleEventClick(eventId: string) {
		if (expandedEventId === eventId) {
			expandedEventId = null;
			expandedEventDetail = null;
			if (onEventClick) {
				onEventClick(null);
			}
			return;
		}

		if (onEventClick) {
			onEventClick(eventId);
		}

		expandedEventId = eventId;
		expandedEventDetail = null;

		try {
			expandedEventDetail = await api.getRiskEvent(eventId);
		} catch (err) {
			console.error('Failed to load event detail:', err);
		}
	}

	function getLandCoverClass(detail: RiskEvent): string | null {
		const factors = detail.scoringFactors?.factors as Array<{ reason_code: string; details: string }> | undefined;
		if (!factors) return null;
		const lc = factors.find(f => f.reason_code?.startsWith('LANDCOVER_'));
		if (!lc?.details) return null;
		const match = lc.details.match(/^Land cover: (\S+)/);
		return match ? match[1] : null;
	}

	async function handleDismiss(event: Event, eventId: string) {
		event.stopPropagation();
		dismissingId = eventId;

		try {
			await api.dismissRiskEvent(eventId, 'User');

			riskEvents.update(events =>
				events.map(e =>
					e.riskEventId === eventId ? { ...e, isDismissed: true } : e
				)
			);
		} catch (err) {
			console.error('Failed to dismiss event:', err);
		} finally {
			dismissingId = null;
		}
	}

	async function handleTakeAction(evt: Event, riskEvent: RiskEventSummary) {
		evt.stopPropagation();
		actionDialogEvent = riskEvent;
		actionDialogDetail = null;
		actionDialogOpen = true;

		// Reuse cached detail if this event is already expanded, otherwise fetch
		if (expandedEventId === riskEvent.riskEventId && expandedEventDetail) {
			actionDialogDetail = expandedEventDetail;
		} else {
			try {
				actionDialogDetail = await api.getRiskEvent(riskEvent.riskEventId);
			} catch (err) {
				console.error('Failed to load event detail for action dialog:', err);
			}
		}
	}

	function setRiskLevelFilter(level: number | null) {
		riskEventFilters.update(f => ({ ...f, riskLevel: level }));
	}

	function setAssetTypeFilter(type: string | null) {
		riskEventFilters.update(f => ({ ...f, assetType: type }));
	}
</script>

<TakeActionDialog
	bind:open={actionDialogOpen}
	event={actionDialogEvent}
	detail={actionDialogDetail}
	onClose={() => { actionDialogOpen = false; actionDialogEvent = null; actionDialogDetail = null; }}
/>

<div class="risk-events-panel">
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
			{#if $assetTypes.length > 1}
				<div class="filter-row">
					<span class="filter-label">Asset Type:</span>
					<div class="risk-level-buttons">
						<button
							class="level-btn"
							class:active={$riskEventFilters.assetType === null}
							on:click={() => setAssetTypeFilter(null)}
						>
							All
						</button>
						{#each $assetTypes as type}
							<button
								class="level-btn"
								class:active={$riskEventFilters.assetType === type}
								on:click={() => setAssetTypeFilter(type)}
							>
								{type}
							</button>
						{/each}
					</div>
				</div>
			{/if}
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

		{#if $queryResultEventIds !== null}
			<div class="query-filter-banner">
				<span>Filtered by query ({$queryResultEventIds.size} events)</span>
				<button class="banner-clear-btn" on:click={() => queryResultEventIds.set(null)}>Clear</button>
			</div>
		{/if}

		<div class="events-list">
			{#each $filteredRiskEvents as event}
				<button
					class="event-item"
					class:acknowledged={event.isAcknowledged}
					class:expanded={expandedEventId === event.riskEventId}
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
						<div class="header-actions">
							<button
								class="action-btn act-btn"
								title="Take action"
								on:click={(e) => handleTakeAction(e, event)}
							>
								Act
							</button>
							<button
								class="action-btn dismiss-btn"
								title="Dismiss"
								disabled={dismissingId === event.riskEventId}
								on:click={(e) => handleDismiss(e, event.riskEventId)}
							>
								{dismissingId === event.riskEventId ? '...' : '\u00d7'}
							</button>
						</div>
					</div>
					<div class="event-asset">
						<span class="asset-name">{event.assetName}</span>
						<span class="asset-type">{event.assetTypeName}</span>
					</div>
					<div class="event-details">
						<span class="distance">{formatDistance(event.distanceMeters)}</span>
						<span class="date">{formatDate(event.createdAt)}</span>
					</div>
					{#if expandedEventId === event.riskEventId}
						<div class="event-expanded">
							{#if expandedEventDetail}
								{@const factors = parseFactors(expandedEventDetail.scoringFactors)}
								{@const summary = generateSummary(factors, event.assetName, event.riskLevelName)}
								{@const suggestedAction = generateSuggestedAction(event.riskLevelName, factors, event.assetTypeName)}
								{@const landCover = getLandCoverClass(expandedEventDetail)}

								<p class="summary-text">{summary}</p>

								{#if factors.length > 0}
									<div class="factor-breakdown">
										{#each factors as factor}
											<div class="factor-row">
												<span class="factor-name">{factor.name}</span>
												{#if factor.max_points > 0}
													<div class="factor-bar-track">
														<div
															class="factor-bar-fill"
															style="width: {Math.min(100, (factor.points / factor.max_points) * 100)}%; background-color: {getFactorBarColor(factor)}"
														></div>
													</div>
													<span class="factor-pts">{factor.points}/{factor.max_points}</span>
												{:else}
													<span class="factor-detail">{factor.details}</span>
												{/if}
											</div>
										{/each}
									</div>
								{/if}

								<p class="suggested-action">{suggestedAction}</p>

								{#if landCover}
									<span class="detail-tag land-cover">{landCover}</span>
								{/if}
							{:else}
								<span class="detail-loading">Loading...</span>
							{/if}
						</div>
					{/if}
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

	.query-filter-banner {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.375rem 0.5rem;
		background: rgba(59, 130, 246, 0.1);
		border: 1px solid var(--color-primary, #3b82f6);
		border-radius: var(--radius-sm);
		font-size: 0.75rem;
		color: var(--color-primary, #3b82f6);
	}

	.banner-clear-btn {
		font-size: 0.6875rem;
		padding: 0.0625rem 0.375rem;
		border: 1px solid var(--color-primary, #3b82f6);
		border-radius: var(--radius-sm);
		background: transparent;
		color: var(--color-primary, #3b82f6);
		cursor: pointer;
	}

	.banner-clear-btn:hover {
		background: var(--color-primary, #3b82f6);
		color: white;
	}

	.events-list {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		max-height: 50vh;
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

	.event-item.expanded {
		border-color: var(--color-text-muted);
	}

	.event-expanded {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		padding-top: 0.375rem;
		border-top: 1px solid var(--color-border);
	}

	.summary-text {
		font-size: 0.75rem;
		color: var(--color-text);
		line-height: 1.4;
		margin: 0;
	}

	.factor-breakdown {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.factor-row {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		font-size: 0.6875rem;
	}

	.factor-name {
		min-width: 5.5rem;
		color: var(--color-text-muted);
		flex-shrink: 0;
	}

	.factor-bar-track {
		flex: 1;
		height: 0.375rem;
		background: var(--color-border);
		border-radius: 2px;
		overflow: hidden;
	}

	.factor-bar-fill {
		height: 100%;
		border-radius: 2px;
		transition: width 0.3s ease;
	}

	.factor-pts {
		min-width: 2.25rem;
		text-align: right;
		color: var(--color-text-muted);
		font-size: 0.625rem;
	}

	.factor-detail {
		flex: 1;
		color: var(--color-text-muted);
		font-size: 0.625rem;
	}

	.suggested-action {
		font-size: 0.6875rem;
		color: var(--color-text-muted);
		font-style: italic;
		line-height: 1.4;
		margin: 0;
	}

	.detail-tag {
		font-size: 0.625rem;
		padding: 0.0625rem 0.375rem;
		border-radius: var(--radius-sm);
		font-weight: 500;
		align-self: flex-start;
	}

	.detail-tag.land-cover {
		background: #166534;
		color: white;
	}

	.detail-loading {
		font-size: 0.6875rem;
		color: var(--color-text-muted);
		font-style: italic;
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

	.header-actions {
		margin-left: auto;
		display: flex;
		gap: 0.25rem;
	}

	.action-btn {
		padding: 0.125rem 0.375rem;
		border-radius: var(--radius-sm);
		border: 1px solid var(--color-border);
		background: var(--color-surface);
		cursor: pointer;
		font-size: 0.625rem;
		transition: all 0.15s ease;
	}

	.act-btn {
		color: var(--color-primary, #3b82f6);
		border-color: var(--color-primary, #3b82f6);
	}

	.act-btn:hover {
		background: var(--color-primary, #3b82f6);
		color: white;
	}

	.dismiss-btn {
		color: var(--color-text-muted);
		font-size: 0.75rem;
		line-height: 1;
	}

	.dismiss-btn:hover:not(:disabled) {
		background: #ef4444;
		border-color: #ef4444;
		color: white;
	}

	.dismiss-btn:disabled {
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
