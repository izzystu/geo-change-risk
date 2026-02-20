<script lang="ts">
	export let title: string;
	export let expanded = true;
</script>

<div class="collapsible-section">
	<button class="section-header" on:click={() => expanded = !expanded}>
		<div class="section-title">
			<span>{title}</span>
			<slot name="badge" />
		</div>
		<span class="chevron" class:collapsed={!expanded}>&#9660;</span>
	</button>

	{#if expanded}
		<div class="section-body">
			<slot />
		</div>
	{/if}
</div>

<style>
	.collapsible-section {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		overflow: hidden;
		flex-shrink: 0;
	}

	.section-header {
		width: 100%;
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.5rem 0.75rem;
		background: none;
		border: none;
		cursor: pointer;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--color-text);
	}

	.section-header:hover {
		background: var(--color-bg);
	}

	.section-title {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.chevron {
		font-size: 0.625rem;
		color: var(--color-text-muted);
		transition: transform 0.2s;
	}

	.chevron.collapsed {
		transform: rotate(-90deg);
	}

	.section-body {
		padding: 0 0.75rem 0.75rem;
	}
</style>
