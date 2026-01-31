<script lang="ts">
	import { onDestroy } from 'svelte';
	import { selectedAoiId } from '$lib/stores/aoi';
	import {
		processingRuns,
		selectedRunId,
		runsLoading,
		processingError,
		resetProcessingState
	} from '$lib/stores/processing';
	import { api, type ProcessingRunSummary } from '$lib/services/api';
	import ConfirmDialog from './ConfirmDialog.svelte';

	let showNewRunForm = false;
	let beforeDate = '';
	let afterDate = '';
	let isCreating = false;
	let pollInterval: ReturnType<typeof setInterval> | null = null;

	// Delete confirmation state
	let deleteConfirmOpen = false;
	let runToDelete: ProcessingRunSummary | null = null;
	let isDeleting = false;

	const PROCESSING_STEPS = [
		{ status: 'FetchingImagery', label: 'Fetching Imagery' },
		{ status: 'CalculatingNdvi', label: 'Calculating NDVI' },
		{ status: 'DetectingChanges', label: 'Detecting Changes' },
		{ status: 'ScoringRisk', label: 'Scoring Risk' }
	];

	function getStepState(
		currentStatus: string,
		stepStatus: string
	): 'completed' | 'active' | 'pending' {
		const statusOrder = [
			'Pending',
			'FetchingImagery',
			'CalculatingNdvi',
			'DetectingChanges',
			'ScoringRisk',
			'Completed'
		];
		const currentIndex = statusOrder.indexOf(currentStatus);
		const stepIndex = statusOrder.indexOf(stepStatus);

		if (stepIndex < currentIndex) return 'completed';
		if (stepIndex === currentIndex) return 'active';
		return 'pending';
	}

	function isRunInProgress(statusName: string): boolean {
		return statusName !== 'Completed' && statusName !== 'Failed' && statusName !== 'Pending';
	}

	// Check if any run is in progress
	$: hasRunInProgress = $processingRuns.some((run) => isRunInProgress(run.statusName));

	// Check if any run needs polling (not completed and not failed)
	$: needsPolling = $processingRuns.some(
		(run) => run.statusName !== 'Completed' && run.statusName !== 'Failed'
	);

	// Start/stop polling based on needsPolling
	$: {
		if (needsPolling && $selectedAoiId && !pollInterval) {
			startPolling($selectedAoiId);
		} else if (!needsPolling && pollInterval) {
			stopPolling();
		}
	}

	function startPolling(aoiId: string) {
		stopPolling();
		pollInterval = setInterval(async () => {
			try {
				const runs = await api.getProcessingRuns(aoiId);
				processingRuns.set(runs);

				// Auto-select most recent completed run if none selected
				if (!$selectedRunId) {
					const completedRun = runs.find((r) => r.statusName === 'Completed');
					if (completedRun) {
						selectedRunId.set(completedRun.runId);
					}
				}
			} catch (err) {
				console.error('Failed to poll processing runs:', err);
			}
		}, 5000);
	}

	function stopPolling() {
		if (pollInterval) {
			clearInterval(pollInterval);
			pollInterval = null;
		}
	}

	onDestroy(() => {
		stopPolling();
	});

	// Load runs when AOI changes
	$: if ($selectedAoiId) {
		stopPolling();
		loadRuns($selectedAoiId);
	}

	async function loadRuns(aoiId: string) {
		resetProcessingState();
		runsLoading.set(true);
		processingError.set(null);

		try {
			const runs = await api.getProcessingRuns(aoiId);
			processingRuns.set(runs);

			// Auto-select most recent completed run
			const completedRun = runs.find(r => r.statusName === 'Completed');
			if (completedRun) {
				selectedRunId.set(completedRun.runId);
			}
		} catch (err) {
			console.error('Failed to load processing runs:', err);
			processingError.set('Failed to load processing runs');
		} finally {
			runsLoading.set(false);
		}
	}

	async function createRun() {
		if (!$selectedAoiId || !beforeDate || !afterDate) return;

		isCreating = true;
		processingError.set(null);

		try {
			const run = await api.createProcessingRun({
				aoiId: $selectedAoiId,
				beforeDate,
				afterDate
			});

			// Add to list and select
			processingRuns.update(runs => [run, ...runs]);
			selectedRunId.set(run.runId);
			showNewRunForm = false;
			beforeDate = '';
			afterDate = '';
		} catch (err) {
			console.error('Failed to create processing run:', err);
			processingError.set('Failed to create processing run');
		} finally {
			isCreating = false;
		}
	}

	function formatDate(dateStr: string): string {
		const date = new Date(dateStr);
		return date.toLocaleDateString('en-US', {
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		});
	}

	function getStatusColor(status: string): string {
		const colors: Record<string, string> = {
			'Pending': '#94a3b8',
			'FetchingImagery': '#3b82f6',
			'CalculatingNdvi': '#3b82f6',
			'DetectingChanges': '#3b82f6',
			'ScoringRisk': '#3b82f6',
			'Completed': '#22c55e',
			'Failed': '#ef4444'
		};
		return colors[status] ?? '#94a3b8';
	}

	function handleDeleteClick(event: MouseEvent, run: ProcessingRunSummary) {
		event.stopPropagation();
		runToDelete = run;
		deleteConfirmOpen = true;
	}

	function cancelDelete() {
		deleteConfirmOpen = false;
		runToDelete = null;
	}

	async function confirmDelete() {
		if (!runToDelete) return;

		isDeleting = true;
		processingError.set(null);

		try {
			await api.deleteProcessingRun(runToDelete.runId);

			// Remove from store
			processingRuns.update(runs => runs.filter(r => r.runId !== runToDelete!.runId));

			// Clear selection if deleted run was selected
			if ($selectedRunId === runToDelete.runId) {
				selectedRunId.set(null);

				// Auto-select next completed run if available
				const completedRun = $processingRuns.find(r => r.statusName === 'Completed');
				if (completedRun) {
					selectedRunId.set(completedRun.runId);
				}
			}

			deleteConfirmOpen = false;
			runToDelete = null;
		} catch (err) {
			console.error('Failed to delete processing run:', err);
			processingError.set('Failed to delete processing run');
		} finally {
			isDeleting = false;
		}
	}

	$: deleteConfirmMessage = runToDelete
		? `This will permanently delete:<br>• Processing run record<br>• ${runToDelete.changePolygonCount} change polygons<br>• Associated risk events<br>• Before/after imagery files`
		: '';
</script>

<div class="processing-panel">
	<div class="header">
		<h3>Processing Runs</h3>
		<button
			class="new-run-btn"
			on:click={() => (showNewRunForm = !showNewRunForm)}
			disabled={!$selectedAoiId || hasRunInProgress}
			title={hasRunInProgress ? 'Wait for current run to complete' : ''}
		>
			{showNewRunForm ? 'Cancel' : '+ New'}
		</button>
	</div>

	{#if !$selectedAoiId}
		<p class="empty-state">Select an AOI to view runs</p>
	{:else if showNewRunForm}
		<div class="new-run-form">
			<div class="form-group">
				<label for="before-date">Before Date</label>
				<input
					id="before-date"
					type="date"
					bind:value={beforeDate}
				/>
			</div>
			<div class="form-group">
				<label for="after-date">After Date</label>
				<input
					id="after-date"
					type="date"
					bind:value={afterDate}
				/>
			</div>
			<button
				class="create-btn"
				on:click={createRun}
				disabled={isCreating || !beforeDate || !afterDate}
			>
				{isCreating ? 'Creating...' : 'Create Run'}
			</button>
		</div>
	{:else if $runsLoading}
		<p class="loading">Loading runs...</p>
	{:else if $processingError}
		<p class="error">{$processingError}</p>
	{:else if $processingRuns.length === 0}
		<p class="empty-state">No processing runs yet</p>
	{:else}
		<div class="runs-list">
			{#each $processingRuns as run}
				<button
					class="run-item"
					class:selected={$selectedRunId === run.runId}
					on:click={() => selectedRunId.set(run.runId)}
				>
					<div class="run-header">
						<span
							class="status-badge"
							style="background-color: {getStatusColor(run.statusName)}"
						>
							{run.statusName}
						</span>
						<div class="header-right">
							<span class="change-count">{run.changePolygonCount} changes</span>
							<button
								class="delete-btn"
								on:click={(e) => handleDeleteClick(e, run)}
								title="Delete run"
								disabled={isRunInProgress(run.statusName)}
							>
								&times;
							</button>
						</div>
					</div>
					<div class="run-dates">
						{formatDate(run.beforeDate)} &rarr; {formatDate(run.afterDate)}
					</div>
					{#if isRunInProgress(run.statusName)}
						<div class="progress-steps">
							{#each PROCESSING_STEPS as step}
								{@const state = getStepState(run.statusName, step.status)}
								<div class="progress-step" class:completed={state === 'completed'} class:active={state === 'active'} class:pending={state === 'pending'}>
									<span class="step-icon">
										{#if state === 'completed'}
											<span class="icon-completed">&#10003;</span>
										{:else if state === 'active'}
											<span class="icon-active">&#10227;</span>
										{:else}
											<span class="icon-pending">&#9675;</span>
										{/if}
									</span>
									<span class="step-label">{step.label}</span>
								</div>
							{/each}
						</div>
					{/if}
					<div class="run-created">
						{formatDate(run.createdAt)}
					</div>
				</button>
			{/each}
		</div>
	{/if}
</div>

<ConfirmDialog
	bind:open={deleteConfirmOpen}
	title="Delete Processing Run"
	message={deleteConfirmMessage}
	confirmLabel={isDeleting ? 'Deleting...' : 'Delete'}
	onConfirm={confirmDelete}
	onCancel={cancelDelete}
	destructive={true}
/>

<style>
	.processing-panel {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
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

	.new-run-btn {
		font-size: 0.75rem;
		padding: 0.25rem 0.5rem;
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: var(--radius-sm);
		cursor: pointer;
	}

	.new-run-btn:hover:not(:disabled) {
		opacity: 0.9;
	}

	.new-run-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
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

	.new-run-form {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		padding: 0.5rem;
		background: var(--color-bg);
		border-radius: var(--radius-sm);
	}

	.form-group {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.form-group label {
		font-size: 0.75rem;
		color: var(--color-text-muted);
	}

	.form-group input {
		padding: 0.375rem;
		font-size: 0.8125rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-surface);
		color: var(--color-text);
	}

	.create-btn {
		padding: 0.5rem;
		font-size: 0.8125rem;
		background: var(--color-primary);
		color: white;
		border: none;
		border-radius: var(--radius-sm);
		cursor: pointer;
	}

	.create-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.runs-list {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		max-height: 200px;
		overflow-y: auto;
	}

	.run-item {
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

	.run-item:hover {
		border-color: var(--color-text-muted);
	}

	.run-item.selected {
		border-color: var(--color-primary);
		background: color-mix(in srgb, var(--color-primary) 10%, var(--color-bg));
	}

	.run-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.delete-btn {
		width: 1.25rem;
		height: 1.25rem;
		padding: 0;
		border: none;
		background: transparent;
		color: var(--color-text-muted);
		font-size: 1rem;
		line-height: 1;
		cursor: pointer;
		border-radius: var(--radius-sm);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.delete-btn:hover:not(:disabled) {
		background: rgba(239, 68, 68, 0.1);
		color: #ef4444;
	}

	.delete-btn:disabled {
		opacity: 0.3;
		cursor: not-allowed;
	}

	.status-badge {
		font-size: 0.625rem;
		padding: 0.125rem 0.375rem;
		border-radius: var(--radius-sm);
		color: white;
		font-weight: 500;
		text-transform: uppercase;
	}

	.change-count {
		font-size: 0.6875rem;
		color: var(--color-text-muted);
	}

	.run-dates {
		font-size: 0.75rem;
		color: var(--color-text);
	}

	.run-created {
		font-size: 0.6875rem;
		color: var(--color-text-muted);
	}

	.progress-steps {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		margin: 0.5rem 0;
		padding: 0.5rem;
		background: var(--color-surface);
		border-radius: var(--radius-sm);
	}

	.progress-step {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.75rem;
	}

	.step-icon {
		width: 1rem;
		text-align: center;
		font-size: 0.875rem;
	}

	.icon-completed {
		color: #22c55e;
		font-weight: bold;
	}

	.icon-active {
		color: #3b82f6;
		display: inline-block;
		animation: spin 1s linear infinite;
	}

	.icon-pending {
		color: #94a3b8;
	}

	.step-label {
		flex: 1;
	}

	.progress-step.completed .step-label {
		color: #22c55e;
	}

	.progress-step.active .step-label {
		color: #3b82f6;
		font-weight: 500;
	}

	.progress-step.pending .step-label {
		color: var(--color-text-muted);
	}

	@keyframes spin {
		from {
			transform: rotate(0deg);
		}
		to {
			transform: rotate(360deg);
		}
	}
</style>
