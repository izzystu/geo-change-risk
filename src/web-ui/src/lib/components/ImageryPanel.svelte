<script lang="ts">
	import { selectedAoiId } from '$lib/stores/aoi';
	import {
		availableScenes,
		selectedBeforeSceneId,
		selectedAfterSceneId,
		beforeSceneDetail,
		afterSceneDetail,
		showBeforeImagery,
		showAfterImagery,
		imageryOpacity,
		scenesLoading,
		sceneDetailLoading,
		imageryError,
		resetImageryState
	} from '$lib/stores/imagery';
	import { api } from '$lib/services/api';

	// Load scenes when AOI changes
	$: if ($selectedAoiId) {
		loadScenes($selectedAoiId);
	}

	async function loadScenes(aoiId: string) {
		resetImageryState();
		scenesLoading.set(true);
		imageryError.set(null);

		try {
			const scenes = await api.getImageryScenes(aoiId);
			availableScenes.set(scenes);
		} catch (err) {
			console.error('Failed to load imagery scenes:', err);
			imageryError.set('Failed to load imagery scenes');
		} finally {
			scenesLoading.set(false);
		}
	}

	async function loadSceneDetail(aoiId: string, sceneId: string, isBefore: boolean) {
		sceneDetailLoading.set(true);

		try {
			const detail = await api.getImageryScene(aoiId, sceneId);
			if (isBefore) {
				beforeSceneDetail.set(detail);
			} else {
				afterSceneDetail.set(detail);
			}
		} catch (err) {
			console.error(`Failed to load scene ${sceneId}:`, err);
			imageryError.set(`Failed to load scene details`);
		} finally {
			sceneDetailLoading.set(false);
		}
	}

	// Load scene details when selection changes
	$: if ($selectedBeforeSceneId && $selectedAoiId) {
		loadSceneDetail($selectedAoiId, $selectedBeforeSceneId, true);
	}

	$: if ($selectedAfterSceneId && $selectedAoiId) {
		loadSceneDetail($selectedAoiId, $selectedAfterSceneId, false);
	}

	function formatDate(dateStr: string): string {
		const date = new Date(dateStr);
		return date.toLocaleDateString('en-US', {
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		});
	}

	function formatFileSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}
</script>

<div class="imagery-panel">
	<h3>Satellite Imagery</h3>

	{#if !$selectedAoiId}
		<p class="empty-state">Select an AOI to view imagery</p>
	{:else if $scenesLoading}
		<p class="loading">Loading scenes...</p>
	{:else if $imageryError}
		<p class="error">{$imageryError}</p>
	{:else if $availableScenes.length === 0}
		<p class="empty-state">No imagery available for this AOI</p>
	{:else}
		<div class="scene-selectors">
			<div class="scene-selector">
				<div class="selector-header">
					<label class="scene-label" for="before-scene">Before</label>
					<label class="visibility-toggle">
						<input
							type="checkbox"
							bind:checked={$showBeforeImagery}
							disabled={!$beforeSceneDetail}
						/>
						Show
					</label>
				</div>
				<select
					id="before-scene"
					class="scene-select"
					bind:value={$selectedBeforeSceneId}
				>
					<option value={null}>Select scene...</option>
					{#each $availableScenes as scene}
						<option value={scene.sceneId}>
							{scene.sceneId} ({formatDate(scene.lastModified)})
						</option>
					{/each}
				</select>
				{#if $beforeSceneDetail}
					<div class="scene-files">
						{#each $beforeSceneDetail.files as file}
							<span class="file-tag" title={file.fileName}>
								{file.fileName.split('.')[0]} ({formatFileSize(file.size)})
							</span>
						{/each}
					</div>
				{/if}
			</div>

			<div class="scene-selector">
				<div class="selector-header">
					<label class="scene-label" for="after-scene">After</label>
					<label class="visibility-toggle">
						<input
							type="checkbox"
							bind:checked={$showAfterImagery}
							disabled={!$afterSceneDetail}
						/>
						Show
					</label>
				</div>
				<select
					id="after-scene"
					class="scene-select"
					bind:value={$selectedAfterSceneId}
				>
					<option value={null}>Select scene...</option>
					{#each $availableScenes as scene}
						<option value={scene.sceneId}>
							{scene.sceneId} ({formatDate(scene.lastModified)})
						</option>
					{/each}
				</select>
				{#if $afterSceneDetail}
					<div class="scene-files">
						{#each $afterSceneDetail.files as file}
							<span class="file-tag" title={file.fileName}>
								{file.fileName.split('.')[0]} ({formatFileSize(file.size)})
							</span>
						{/each}
					</div>
				{/if}
			</div>
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

		{#if $sceneDetailLoading}
			<p class="loading">Loading scene details...</p>
		{/if}
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

	.scene-selectors {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.scene-selector {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.selector-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.scene-label {
		font-size: 0.8125rem;
		font-weight: 500;
		color: var(--color-text);
	}

	.visibility-toggle {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.75rem;
		color: var(--color-text-muted);
		cursor: pointer;
	}

	.visibility-toggle input {
		width: 0.875rem;
		height: 0.875rem;
		cursor: pointer;
	}

	.scene-select {
		padding: 0.5rem;
		font-size: 0.8125rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-bg);
		color: var(--color-text);
		cursor: pointer;
	}

	.scene-select:hover {
		border-color: var(--color-text-muted);
	}

	.scene-select:focus {
		outline: none;
		border-color: var(--color-primary);
	}

	.scene-files {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
	}

	.file-tag {
		font-size: 0.6875rem;
		padding: 0.125rem 0.375rem;
		background: var(--color-border);
		border-radius: var(--radius-sm);
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
