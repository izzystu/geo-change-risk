<script lang="ts">
	import { selectedAoiId } from '$lib/stores/aoi';
	import { selectedRunId, processingRuns } from '$lib/stores/processing';
	import {
		beforeSceneDetail,
		afterSceneDetail,
		showBeforeImagery,
		showAfterImagery,
		imageryOpacity,
		sceneDetailLoading,
		imageryError,
		resetImageryState
	} from '$lib/stores/imagery';
	import { api } from '$lib/services/api';

	// Track which run we've loaded imagery for
	let loadedForRunId: string | null = null;

	// Reset when AOI changes
	$: if ($selectedAoiId) {
		resetImageryState();
		loadedForRunId = null;
	}

	// Auto-load before/after scenes when a processing run is selected
	$: if ($selectedRunId && $selectedAoiId && $selectedRunId !== loadedForRunId) {
		loadScenesForRun($selectedAoiId, $selectedRunId);
	}

	async function loadScenesForRun(aoiId: string, runId: string) {
		loadedForRunId = runId;
		resetImageryState();
		sceneDetailLoading.set(true);
		imageryError.set(null);

		try {
			const run = await api.getProcessingRun(runId);

			const loads: Promise<void>[] = [];
			if (run.beforeSceneId) {
				loads.push(
					api.getImageryScene(aoiId, run.beforeSceneId).then(detail => {
						beforeSceneDetail.set(detail);
					})
				);
			}
			if (run.afterSceneId) {
				loads.push(
					api.getImageryScene(aoiId, run.afterSceneId).then(detail => {
						afterSceneDetail.set(detail);
					})
				);
			}
			await Promise.all(loads);
		} catch (err) {
			console.error('Failed to load imagery for run:', err);
			imageryError.set('Failed to load imagery');
		} finally {
			sceneDetailLoading.set(false);
		}
	}

	// Derive friendly date labels from the selected run
	$: selectedRun = $processingRuns.find(r => r.runId === $selectedRunId) ?? null;

	type ImagerySelection = 'none' | 'before' | 'after';
	$: selection = $showAfterImagery ? 'after' : $showBeforeImagery ? 'before' : 'none' as ImagerySelection;

	function setSelection(value: ImagerySelection) {
		showBeforeImagery.set(value === 'before');
		showAfterImagery.set(value === 'after');
	}

	function formatDate(dateStr: string): string {
		const date = new Date(dateStr);
		return date.toLocaleDateString('en-US', {
			year: 'numeric',
			month: 'short',
			day: 'numeric',
			timeZone: 'UTC'
		});
	}
</script>

<div class="imagery-panel">
	<h3>Satellite Imagery</h3>

	{#if !$selectedAoiId}
		<p class="empty-state">Select an AOI to view imagery</p>
	{:else if !$selectedRunId}
		<p class="empty-state">Select a processing run to view imagery</p>
	{:else if $sceneDetailLoading}
		<p class="loading">Loading imagery...</p>
	{:else if $imageryError}
		<p class="error">{$imageryError}</p>
	{:else if !$beforeSceneDetail && !$afterSceneDetail}
		<p class="empty-state">No imagery available for this run</p>
	{:else}
		<div class="imagery-selector">
			<div class="segment-group">
				<button
					class="segment-btn"
					class:active={selection === 'none'}
					on:click={() => setSelection('none')}
				>
					None
				</button>
				{#if $beforeSceneDetail}
					<button
						class="segment-btn"
						class:active={selection === 'before'}
						on:click={() => setSelection('before')}
					>
						Before
					</button>
				{/if}
				{#if $afterSceneDetail}
					<button
						class="segment-btn"
						class:active={selection === 'after'}
						on:click={() => setSelection('after')}
					>
						After
					</button>
				{/if}
			</div>
			{#if selectedRun && selection !== 'none'}
				<span class="selection-date">
					{formatDate(selection === 'before' ? selectedRun.beforeDate : selectedRun.afterDate)}
				</span>
			{/if}
		</div>

		<div class="opacity-control">
			<label for="opacity-slider">Opacity: {Math.round($imageryOpacity * 100)}%</label>
			<input
				id="opacity-slider"
				type="range"
				min="0"
				max="1"
				step="0.05"
				bind:value={$imageryOpacity}
			/>
		</div>
	{/if}
</div>

<style>
	.imagery-panel {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	h3 {
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--color-text);
		margin: 0;
	}

	.empty-state, .loading {
		font-size: 0.8125rem;
		color: var(--color-text-muted);
		font-style: italic;
	}

	.error {
		font-size: 0.8125rem;
		color: #ef4444;
	}

	.imagery-selector {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.segment-group {
		display: flex;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		overflow: hidden;
	}

	.segment-btn {
		font-size: 0.75rem;
		padding: 0.25rem 0.625rem;
		border: none;
		background: var(--color-bg);
		color: var(--color-text-muted);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.segment-btn:not(:last-child) {
		border-right: 1px solid var(--color-border);
	}

	.segment-btn:hover:not(.active) {
		background: var(--color-surface);
	}

	.segment-btn.active {
		background: var(--color-primary);
		color: white;
	}

	.selection-date {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	.opacity-control {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		padding-top: 0.5rem;
		border-top: 1px solid var(--color-border);
	}

	.opacity-control label {
		font-size: 0.8125rem;
		color: var(--color-text);
	}

	.opacity-control input[type="range"] {
		width: 100%;
		height: 0.375rem;
		cursor: pointer;
	}
</style>
