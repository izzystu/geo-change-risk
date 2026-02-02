<script lang="ts">
	export let open = false;
	export let assetName = '';
	export let riskLevelName = '';
	export let onClose: () => void = () => { open = false; };
</script>

{#if open}
<div class="dialog-overlay" on:click={onClose} role="presentation">
	<div class="dialog" on:click|stopPropagation role="dialog">
		<h3>Take Action: {assetName}</h3>
		<div class="message">
			<p>
				A <strong>{riskLevelName}</strong>-level risk event has been detected near
				<strong>{assetName}</strong>.
			</p>
			<p>
				An on-site inspection can verify the detected change and determine whether
				protective measures are needed for this asset.
			</p>
		</div>
		<div class="actions">
			<button class="schedule-btn" disabled>
				Schedule Inspection <span class="coming-soon">(Coming soon)</span>
			</button>
			<button class="close-btn" on:click={onClose}>Close</button>
		</div>
	</div>
</div>
{/if}

<style>
	.dialog-overlay {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.5);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
	}
	.dialog {
		background: var(--color-surface, white);
		border-radius: 8px;
		padding: 1.5rem;
		max-width: 400px;
		width: 90%;
		box-shadow: 0 4px 20px rgba(0,0,0,0.3);
	}
	h3 {
		margin: 0 0 1rem 0;
		font-size: 1.1rem;
		color: var(--color-text, #333);
	}
	.message {
		margin-bottom: 1.5rem;
		font-size: 0.875rem;
		color: var(--color-text-muted, #666);
		line-height: 1.5;
	}
	.message p {
		margin: 0 0 0.75rem 0;
	}
	.message p:last-child {
		margin-bottom: 0;
	}
	.actions {
		display: flex;
		gap: 0.5rem;
		justify-content: flex-end;
	}
	button {
		padding: 0.5rem 1rem;
		border-radius: 4px;
		cursor: pointer;
		font-size: 0.875rem;
	}
	.schedule-btn {
		background: var(--color-primary, #3b82f6);
		color: white;
		border: none;
		opacity: 0.5;
		cursor: not-allowed;
	}
	.coming-soon {
		font-size: 0.75rem;
		opacity: 0.8;
	}
	.close-btn {
		background: transparent;
		border: 1px solid var(--color-border, #ccc);
		color: var(--color-text, #333);
	}
	.close-btn:hover {
		background: var(--color-bg, #f5f5f5);
	}
</style>
