<script lang="ts">
	import { basemapOptions, selectedBasemap } from '$lib/stores/layers';
</script>

<div class="basemap-panel">
	<select class="basemap-select" bind:value={$selectedBasemap}>
		{#each basemapOptions as option}
			<option value={option.id}>{option.name}</option>
		{/each}
	</select>
</div>

<style>
	.basemap-panel {
		display: flex;
		flex-direction: column;
	}

	.basemap-select {
		padding: 0.5rem;
		font-size: 0.8125rem;
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
</style>
