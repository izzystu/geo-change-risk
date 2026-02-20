<script lang="ts">
	import { selectedAoiId } from '$lib/stores/aoi';
	import {
		queryText,
		queryResponse,
		queryLoading,
		llmAvailable,
		queryError,
		queryHistory,
		queryResultEventIds
	} from '$lib/stores/query';
	import { api, type NaturalLanguageQueryResponse } from '$lib/services/api';
	import { onMount } from 'svelte';

	export let onQueryResults: ((geoJson: GeoJSON.FeatureCollection | null) => void) | undefined = undefined;

	const exampleQueries = [
		'Show critical risk events near hospitals',
		'Find landslide changes larger than 5000 sq meters',
		'Show all high criticality substations',
		'Risk events within 500m of schools'
	];

	onMount(async () => {
		try {
			const health = await api.getQueryHealth();
			llmAvailable.set(health.available);
		} catch {
			llmAvailable.set(false);
		}
	});

	async function submitQuery() {
		const text = $queryText.trim();
		if (!text || $queryLoading) return;

		queryLoading.set(true);
		queryError.set(null);
		queryResponse.set(null);

		// Add to history (dedup, max 10)
		queryHistory.update(h => {
			const filtered = h.filter(q => q !== text);
			return [text, ...filtered].slice(0, 10);
		});

		try {
			const response = await api.queryNaturalLanguage({
				query: text,
				aoiId: $selectedAoiId ?? undefined
			});

			queryResponse.set(response);

			if (response.interpretation) {
				console.log('[Query] Interpretation:', response.interpretation);
			}
			if (response.queryPlan) {
				console.log('[Query] Plan:', JSON.stringify(response.queryPlan, null, 2));
			}

			if (response.success && response.geoJson && onQueryResults) {
				onQueryResults(response.geoJson as GeoJSON.FeatureCollection);
			}

			if (!response.success) {
				queryError.set(response.errorMessage ?? 'Query failed');
			}
		} catch (err) {
			queryError.set(err instanceof Error ? err.message : 'Query failed');
		} finally {
			queryLoading.set(false);
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter' && !e.shiftKey) {
			e.preventDefault();
			submitQuery();
		}
	}

	function useExample(example: string) {
		queryText.set(example);
		submitQuery();
	}

	function clearResults() {
		queryResponse.set(null);
		queryError.set(null);
		queryText.set('');
		queryResultEventIds.set(null);
		if (onQueryResults) {
			onQueryResults(null);
		}
	}

	function showInRiskEvents() {
		if (!$queryResponse?.results) return;
		const ids = $queryResponse.results
			.map(r => prop(r, 'riskEventId'))
			.filter((id): id is string => typeof id === 'string');
		if (ids.length > 0) {
			queryResultEventIds.set(new Set(ids));
		}
	}

	function getRiskColor(level: string): string {
		const colors: Record<string, string> = {
			Low: '#22c55e',
			Medium: '#f59e0b',
			High: '#f97316',
			Critical: '#ef4444'
		};
		return colors[level] ?? '#94a3b8';
	}

	function formatDistance(meters: number): string {
		if (meters < 1000) return `${Math.round(meters)}m`;
		return `${(meters / 1000).toFixed(1)}km`;
	}

	function formatArea(sqm: number): string {
		return Math.round(sqm).toLocaleString();
	}

	// Helper to safely access properties on untyped result objects
	function prop(obj: unknown, key: string): any {
		if (obj && typeof obj === 'object') return (obj as Record<string, any>)[key];
		return undefined;
	}
</script>

<div class="query-panel">
	<div class="input-area">
		<textarea
			placeholder="Ask about risk events, changes, assets..."
			bind:value={$queryText}
			on:keydown={handleKeydown}
			disabled={$queryLoading}
			rows="3"
		></textarea>
		<button
			class="submit-btn"
			on:click={submitQuery}
			disabled={$queryLoading || !$queryText.trim()}
		>
			{#if $queryLoading}
				<span class="spinner"></span> Querying...
			{:else}
				Query
			{/if}
		</button>
	</div>

	{#if $queryError}
		<div class="error-msg">{$queryError}</div>
	{/if}

	{#if $queryResponse}
		{#if $queryResponse.success}
			<div class="result-count">
				Found {$queryResponse.totalCount} results
				{#if $queryResponse.queryPlan}
					<span class="entity-tag">{$queryResponse.queryPlan.targetEntity}</span>
				{/if}
			</div>

			{#if $queryResponse.results && $queryResponse.results.length > 0}
				<div class="results-list">
					{#each $queryResponse.results.slice(0, 20) as result}
						<div class="result-item">
							{#if $queryResponse.queryPlan?.targetEntity === 'RiskEvent'}
								<div class="result-header">
									<span class="risk-badge" style="background-color: {getRiskColor(prop(result, 'riskLevelName'))}">{prop(result, 'riskScore')}</span>
									<span class="result-title">{prop(result, 'assetName') ?? 'Unknown'}</span>
								</div>
								<div class="result-meta">
									<span>{prop(result, 'riskLevelName')}</span>
									<span>{prop(result, 'assetTypeName')}</span>
									{#if prop(result, 'distanceMeters')}<span>{formatDistance(prop(result, 'distanceMeters'))}</span>{/if}
								</div>
							{:else if $queryResponse.queryPlan?.targetEntity === 'ChangePolygon'}
								<div class="result-header">
									<span class="result-title">{prop(result, 'changeTypeName') ?? 'Change'}</span>
								</div>
								<div class="result-meta">
									<span>{formatArea(prop(result, 'areaSqMeters'))} m2</span>
									<span>NDVI: {prop(result, 'ndviDropMean')?.toFixed(3)}</span>
								</div>
							{:else if $queryResponse.queryPlan?.targetEntity === 'Asset'}
								<div class="result-header">
									<span class="result-title">{prop(result, 'name')}</span>
								</div>
								<div class="result-meta">
									<span>{prop(result, 'assetTypeName')}</span>
									<span>{prop(result, 'criticalityName')}</span>
								</div>
							{:else}
								<div class="result-header">
									<span class="result-title">{prop(result, 'statusName') ?? prop(result, 'name') ?? 'Item'}</span>
								</div>
							{/if}
						</div>
					{/each}
					{#if $queryResponse.results.length > 20}
						<div class="more-results">...and {$queryResponse.results.length - 20} more</div>
					{/if}
				</div>
			{/if}
		{/if}

		<div class="actions-row">
			{#if $queryResponse?.success && $queryResponse?.queryPlan?.targetEntity === 'RiskEvent' && $queryResponse.results?.length > 0}
				<button class="show-events-btn" on:click={showInRiskEvents}>Show in Risk Events</button>
			{/if}
			<button class="clear-btn" on:click={clearResults}>Clear</button>
		</div>
	{:else if !$queryLoading && !$queryError}
		<div class="examples">
			<span class="examples-label">Try:</span>
			{#each exampleQueries as example}
				<button class="example-btn" on:click={() => useExample(example)}>
					{example}
				</button>
			{/each}
		</div>
	{/if}
</div>

<style>
	.query-panel {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.input-area {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.input-area textarea {
		width: 100%;
		padding: 0.375rem 0.5rem;
		font-size: 0.8125rem;
		font-family: inherit;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-bg);
		color: var(--color-text);
		resize: vertical;
		min-height: 3rem;
		box-sizing: border-box;
	}

	.input-area textarea::placeholder {
		color: var(--color-text-muted);
	}

	.input-area textarea:focus {
		outline: none;
		border-color: var(--color-primary, #3b82f6);
	}

	.submit-btn {
		align-self: flex-end;
		padding: 0.375rem 0.75rem;
		font-size: 0.8125rem;
		font-weight: 500;
		border: 1px solid var(--color-primary, #3b82f6);
		border-radius: var(--radius-sm);
		background: var(--color-primary, #3b82f6);
		color: white;
		cursor: pointer;
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}

	.submit-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.submit-btn:hover:not(:disabled) {
		opacity: 0.9;
	}

	.spinner {
		display: inline-block;
		width: 0.75rem;
		height: 0.75rem;
		border: 2px solid rgba(255, 255, 255, 0.3);
		border-top-color: white;
		border-radius: 50%;
		animation: spin 0.6s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.error-msg {
		font-size: 0.75rem;
		color: var(--color-danger, #ef4444);
		padding: 0.25rem 0.5rem;
		background: rgba(239, 68, 68, 0.1);
		border-radius: var(--radius-sm);
	}

	.result-count {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}

	.entity-tag {
		font-size: 0.625rem;
		padding: 0.0625rem 0.375rem;
		background: var(--color-border);
		border-radius: var(--radius-sm);
		color: var(--color-text-muted);
	}

	.results-list {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		max-height: 250px;
		overflow-y: auto;
	}

	.result-item {
		padding: 0.375rem 0.5rem;
		background: var(--color-bg);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
	}

	.result-header {
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}

	.risk-badge {
		font-size: 0.625rem;
		padding: 0.0625rem 0.25rem;
		border-radius: var(--radius-sm);
		color: white;
		font-weight: 600;
		min-width: 1.5rem;
		text-align: center;
	}

	.result-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--color-text);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.result-meta {
		display: flex;
		gap: 0.5rem;
		font-size: 0.6875rem;
		color: var(--color-text-muted);
		margin-top: 0.125rem;
	}

	.more-results {
		font-size: 0.6875rem;
		color: var(--color-text-muted);
		font-style: italic;
		text-align: center;
		padding: 0.25rem;
	}

	.actions-row {
		display: flex;
		gap: 0.375rem;
		justify-content: flex-end;
	}

	.show-events-btn {
		font-size: 0.6875rem;
		padding: 0.125rem 0.375rem;
		border: 1px solid var(--color-primary, #3b82f6);
		border-radius: var(--radius-sm);
		background: var(--color-surface);
		color: var(--color-primary, #3b82f6);
		cursor: pointer;
	}

	.show-events-btn:hover {
		background: var(--color-primary, #3b82f6);
		color: white;
	}

	.clear-btn {
		font-size: 0.6875rem;
		padding: 0.125rem 0.375rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-surface);
		color: var(--color-text-muted);
		cursor: pointer;
	}

	.clear-btn:hover {
		border-color: var(--color-text-muted);
	}

	.examples {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.examples-label {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		font-weight: 500;
	}

	.example-btn {
		font-size: 0.6875rem;
		padding: 0.25rem 0.5rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-surface);
		color: var(--color-text);
		cursor: pointer;
		text-align: left;
		transition: border-color 0.15s ease;
	}

	.example-btn:hover {
		border-color: var(--color-primary, #3b82f6);
		color: var(--color-primary, #3b82f6);
	}
</style>
