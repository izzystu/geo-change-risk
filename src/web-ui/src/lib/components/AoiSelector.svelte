<script lang="ts">
	import { areasOfInterest, selectedAoiId, aoiLoading, requestZoomToAoi } from '$lib/stores/aoi';

	function handleSelect(event: Event) {
		const target = event.target as HTMLSelectElement;
		selectedAoiId.set(target.value || null);
	}
</script>

<div class="aoi-selector">
	<div class="select-row">
		<select id="aoi-select" on:change={handleSelect} disabled={$aoiLoading}>
			<option value="">Select an AOI...</option>
			{#each $areasOfInterest as aoi}
				<option value={aoi.aoiId} selected={$selectedAoiId === aoi.aoiId}>
					{aoi.name}
				</option>
			{/each}
		</select>
		<button
			class="zoom-btn"
			on:click={requestZoomToAoi}
			disabled={!$selectedAoiId}
			title="Zoom to AOI"
		>
			<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
				<circle cx="12" cy="12" r="10"/>
				<circle cx="12" cy="12" r="3"/>
			</svg>
		</button>
	</div>
</div>

<style>
	.aoi-selector {
		display: flex;
		flex-direction: column;
	}

	.select-row {
		display: flex;
		gap: 0.5rem;
		min-width: 0;
	}

	select {
		flex: 1;
		min-width: 0;
		padding: 0.5rem 0.75rem;
		font-size: 0.875rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface);
		cursor: pointer;
	}

	select:focus {
		outline: none;
		border-color: var(--color-primary);
		box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.2);
	}

	select:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.zoom-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0.5rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		background: var(--color-surface);
		color: var(--color-text-muted);
		cursor: pointer;
	}

	.zoom-btn:hover:not(:disabled) {
		background: var(--color-bg);
		color: var(--color-text);
		border-color: var(--color-text-muted);
	}

	.zoom-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}
</style>
