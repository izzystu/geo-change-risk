<script lang="ts">
	import { layers, toggleLayer, setAllLayersVisible, basemapOptions, selectedBasemap } from '$lib/stores/layers';
	import { showChangePolygons, changePolygonsGeoJson } from '$lib/stores/processing';

	let allVisible = true;

	function handleToggleAll() {
		allVisible = !allVisible;
		setAllLayersVisible(allVisible);
	}

	function toggleChangePolygons() {
		showChangePolygons.update(v => !v);
	}

	// Check if there are any change polygons loaded
	$: hasChangePolygons = $changePolygonsGeoJson?.features && $changePolygonsGeoJson.features.length > 0;
</script>

<div class="layer-panel">
	<div class="basemap-section">
		<label class="basemap-label" for="basemap-select">Basemap</label>
		<select id="basemap-select" class="basemap-select" bind:value={$selectedBasemap}>
			{#each basemapOptions as option}
				<option value={option.id}>{option.name}</option>
			{/each}
		</select>
	</div>

	{#if hasChangePolygons}
		<div class="divider"></div>

		<div class="header">
			<h3>Change Detection</h3>
		</div>

		<div class="layer-list">
			<label class="layer-item">
				<input
					type="checkbox"
					checked={$showChangePolygons}
					on:change={toggleChangePolygons}
				/>
				<span class="color-swatch change-gradient"></span>
				<span class="layer-name">Change Polygons</span>
			</label>
		</div>
	{/if}

	<div class="divider"></div>

	<div class="header">
		<h3>Asset Layers</h3>
		<button class="toggle-all" on:click={handleToggleAll}>
			{allVisible ? 'Hide All' : 'Show All'}
		</button>
	</div>

	<div class="layer-list">
		{#each $layers as layer}
			<label class="layer-item">
				<input
					type="checkbox"
					checked={layer.visible}
					on:change={() => toggleLayer(layer.id)}
				/>
				<span class="color-swatch" style="background-color: {layer.color}"></span>
				<span class="layer-name">{layer.name}</span>
			</label>
		{/each}
	</div>
</div>

<style>
	.layer-panel {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.basemap-section {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.basemap-label {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--color-text);
	}

	.basemap-select {
		padding: 0.5rem;
		font-size: 0.875rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-bg);
		color: var(--color-text);
		cursor: pointer;
	}

	.basemap-select:hover {
		border-color: var(--color-text-muted);
	}

	.basemap-select:focus {
		outline: none;
		border-color: var(--color-primary);
	}

	.divider {
		height: 1px;
		background: var(--color-border);
		margin: 0.25rem 0;
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
	}

	.toggle-all {
		font-size: 0.75rem;
		padding: 0.25rem 0.5rem;
		background: var(--color-bg);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		cursor: pointer;
		color: var(--color-text-muted);
	}

	.toggle-all:hover {
		background: var(--color-border);
	}

	.layer-list {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.layer-item {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.375rem 0.5rem;
		border-radius: var(--radius-sm);
		cursor: pointer;
		font-size: 0.875rem;
	}

	.layer-item:hover {
		background: var(--color-bg);
	}

	input[type="checkbox"] {
		width: 1rem;
		height: 1rem;
		cursor: pointer;
	}

	.color-swatch {
		width: 0.75rem;
		height: 0.75rem;
		border-radius: 2px;
		flex-shrink: 0;
	}

	.color-swatch.change-gradient {
		background: linear-gradient(90deg, #fef08a 0%, #facc15 33%, #f97316 66%, #dc2626 100%);
	}

	.layer-name {
		flex: 1;
		color: var(--color-text);
	}
</style>
