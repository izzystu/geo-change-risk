<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/services/api';
	import { areasOfInterest, selectedAoiId, selectedAoi, aoiLoading, aoiError } from '$lib/stores/aoi';
	import { unacknowledgedCount } from '$lib/stores/processing';
	import { llmAvailable } from '$lib/stores/query';
	import { scheduleConfig } from '$lib/stores/scheduling';
	import MapView from '$lib/components/MapView.svelte';
	import CollapsibleSection from '$lib/components/CollapsibleSection.svelte';
	import AoiSelector from '$lib/components/AoiSelector.svelte';
	import LayerPanel from '$lib/components/LayerPanel.svelte';
	import BasemapPanel from '$lib/components/BasemapPanel.svelte';
	import ImageryPanel from '$lib/components/ImageryPanel.svelte';
	import ProcessingPanel from '$lib/components/ProcessingPanel.svelte';
	import QueryPanel from '$lib/components/QueryPanel.svelte';
	import RiskEventsPanel from '$lib/components/RiskEventsPanel.svelte';
	import SchedulingPanel from '$lib/components/SchedulingPanel.svelte';

	$: scheduleStatus = !$scheduleConfig.processingSchedule ? 'Off'
		: $scheduleConfig.processingEnabled ? 'Active' : 'Paused';

	let apiStatus: 'loading' | 'connected' | 'error' = 'loading';
	let mapViewComponent: MapView;

	function handleRiskEventClick(eventId: string | null) {
		if (eventId) {
			mapViewComponent?.zoomToRiskEvent(eventId);
		} else {
			mapViewComponent?.clearHighlights();
		}
	}

	function handleQueryResults(geoJson: GeoJSON.FeatureCollection | null) {
		mapViewComponent?.showQueryResults(geoJson);
	}

	onMount(async () => {
		// Check API health
		try {
			await api.getHealth();
			apiStatus = 'connected';
		} catch (error) {
			apiStatus = 'error';
			console.error('API connection failed:', error);
			return;
		}

		// Load AOIs
		aoiLoading.set(true);
		try {
			const aois = await api.getAreasOfInterest();
			areasOfInterest.set(aois);

			// Auto-select first AOI if available
			if (aois.length > 0) {
				selectedAoiId.set(aois[0].aoiId);
			}
		} catch (error) {
			aoiError.set('Failed to load areas of interest');
			console.error(error);
		} finally {
			aoiLoading.set(false);
		}
	});

	// Fetch full AOI details when selection changes
	$: if ($selectedAoiId) {
		loadAoiDetails($selectedAoiId);
	}

	async function loadAoiDetails(aoiId: string) {
		try {
			const aoi = await api.getAreaOfInterest(aoiId);
			selectedAoi.set(aoi);
		} catch (error) {
			console.error('Failed to load AOI details:', error);
			selectedAoi.set(null);
		}
	}
</script>

<div class="app">
	<aside class="sidebar">
		<header class="sidebar-header">
			<h1>Geo Change Risk</h1>
			<p class="subtitle">Infrastructure Risk Intelligence</p>
		</header>

		{#if apiStatus === 'loading'}
			<div class="status-message">Connecting to API...</div>
		{:else if apiStatus === 'error'}
			<div class="status-message error">
				Failed to connect to API.
				<br />
				Make sure the API is running at localhost:5074
			</div>
		{:else}
			<div class="sidebar-content">
				<CollapsibleSection title="Area of Interest" expanded={true}>
					<AoiSelector />
				</CollapsibleSection>

				<CollapsibleSection title="Layers" expanded={true}>
					<LayerPanel />
					<div class="layers-divider"></div>
					<BasemapPanel />
					<div class="layers-divider"></div>
					<ImageryPanel />
				</CollapsibleSection>

				<CollapsibleSection title="Processing Runs" expanded={true}>
					<ProcessingPanel />
				</CollapsibleSection>

				<CollapsibleSection title="Natural Language Query" expanded={false}>
					<svelte:fragment slot="badge">
						{#if $llmAvailable === true}
							<span class="llm-dot available" title="LLM service available"></span>
						{:else if $llmAvailable === false}
							<span class="llm-dot unavailable" title="LLM service unavailable"></span>
						{/if}
					</svelte:fragment>
					<QueryPanel onQueryResults={handleQueryResults} />
				</CollapsibleSection>

				<CollapsibleSection title="Risk Events" expanded={true}>
					<svelte:fragment slot="badge">
						{#if $unacknowledgedCount > 0}
							<span class="badge-pill">{$unacknowledgedCount}</span>
						{/if}
					</svelte:fragment>
					<RiskEventsPanel onEventClick={handleRiskEventClick} />
				</CollapsibleSection>

				<CollapsibleSection title="Scheduling" expanded={false}>
					<svelte:fragment slot="badge">
						<span class="schedule-badge" class:active={scheduleStatus === 'Active'} class:paused={scheduleStatus === 'Paused'}>
							{scheduleStatus}
						</span>
					</svelte:fragment>
					<SchedulingPanel />
				</CollapsibleSection>
			</div>
		{/if}

		<footer class="sidebar-footer">
			<div class="api-status" class:connected={apiStatus === 'connected'}>
				<span class="status-dot"></span>
				{apiStatus === 'connected' ? 'API Connected' : 'API Disconnected'}
			</div>
		</footer>
	</aside>

	<main class="map-area">
		<MapView bind:this={mapViewComponent} />
	</main>
</div>

<style>
	.app {
		display: flex;
		height: 100vh;
		width: 100vw;
	}

	.sidebar {
		width: 300px;
		flex-shrink: 0;
		background: var(--color-surface);
		border-right: 1px solid var(--color-border);
		display: flex;
		flex-direction: column;
		box-shadow: var(--shadow-md);
		z-index: 10;
	}

	.sidebar-header {
		padding: 1.25rem;
		border-bottom: 1px solid var(--color-border);
	}

	h1 {
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--color-text);
		margin: 0;
	}

	.subtitle {
		font-size: 0.75rem;
		color: var(--color-text-muted);
		margin-top: 0.25rem;
	}

	.sidebar-content {
		flex: 1;
		overflow-y: auto;
		padding: 0.5rem;
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.llm-dot {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
		display: inline-block;
	}

	.llm-dot.available {
		background: var(--color-success, #22c55e);
	}

	.llm-dot.unavailable {
		background: var(--color-danger, #ef4444);
	}

	.badge-pill {
		font-size: 0.625rem;
		padding: 0.0625rem 0.375rem;
		background: var(--color-border);
		color: var(--color-text-muted);
		border-radius: 999px;
		font-weight: 600;
	}

	.schedule-badge {
		font-size: 0.5625rem;
		font-weight: 600;
		padding: 0.0625rem 0.375rem;
		border-radius: var(--radius-sm);
		text-transform: uppercase;
		background: var(--color-bg);
		color: var(--color-text-muted);
	}

	.schedule-badge.active {
		background: #dcfce7;
		color: #166534;
	}

	.schedule-badge.paused {
		background: #fef3c7;
		color: #92400e;
	}

	.layers-divider {
		height: 1px;
		background: var(--color-border);
		margin: 0.5rem 0;
	}

	.sidebar-footer {
		padding: 0.75rem 1rem;
		border-top: 1px solid var(--color-border);
		font-size: 0.75rem;
	}

	.api-status {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		color: var(--color-text-muted);
	}

	.status-dot {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
		background: var(--color-danger);
	}

	.api-status.connected .status-dot {
		background: var(--color-success);
	}

	.map-area {
		flex: 1;
		position: relative;
	}

	.status-message {
		padding: 1.5rem;
		text-align: center;
		color: var(--color-text-muted);
		font-size: 0.875rem;
	}

	.status-message.error {
		color: var(--color-danger);
	}
</style>
