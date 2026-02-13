<script lang="ts">
	import { selectedAoiId, selectedAoi } from '$lib/stores/aoi';
	import {
		scheduleConfig,
		scheduleSaving,
		scheduleError,
		scheduledRuns,
		cronPresets,
		loadScheduleFromAoi,
		saveSchedule,
		resetScheduleState,
		describeCron,
		timeAgo
	} from '$lib/stores/scheduling';
	import { api, type ProcessingRunSummary } from '$lib/services/api';

	let expanded = false;
	let selectedPreset = '';
	let customCron = '';
	let showCustomInput = false;
	let localMaxCloud = 20;
	let hasUnsavedChanges = false;
	let currentAoiId: string | null = null;
	let loadedScheduleForAoi: string | null = null;
	let loadingAoiId: string | null = null;

	// Load schedule when AOI changes or when AOI details finish loading async.
	// The loadedScheduleForAoi guard ensures we load once per AOI selection,
	// even when selectedAoi arrives after selectedAoiId (async fetch).
	$: if ($selectedAoiId !== currentAoiId) {
		currentAoiId = $selectedAoiId;
		loadedScheduleForAoi = null;
		if (!$selectedAoiId) resetScheduleState();
	}

	$: if ($selectedAoi && $selectedAoi.aoiId === currentAoiId && loadedScheduleForAoi !== currentAoiId) {
		loadedScheduleForAoi = currentAoiId;
		loadScheduleFromAoi($selectedAoi);
		loadScheduledRuns($selectedAoi.aoiId);
		syncLocalState($selectedAoi);
	}

	function syncLocalState(aoi: import('$lib/services/api').AreaOfInterest) {
		localMaxCloud = aoi.maxCloudCover;
		const currentCron = aoi.processingSchedule;
		const preset = cronPresets.find(p => p.cron === currentCron);
		if (preset) {
			selectedPreset = preset.cron;
			showCustomInput = false;
		} else if (currentCron) {
			selectedPreset = 'custom';
			customCron = currentCron;
			showCustomInput = true;
		} else {
			selectedPreset = '';
			showCustomInput = false;
		}
		hasUnsavedChanges = false;
	}

	function handlePresetChange(event: Event) {
		const value = (event.target as HTMLSelectElement).value;
		selectedPreset = value;
		showCustomInput = value === 'custom';
		if (value !== 'custom') {
			customCron = '';
		}
		hasUnsavedChanges = true;
	}

	function handleCloudChange(event: Event) {
		localMaxCloud = parseInt((event.target as HTMLInputElement).value);
		hasUnsavedChanges = true;
	}

	async function handleSave() {
		if (!$selectedAoiId) return;
		const rawCron = selectedPreset === 'custom' ? customCron : selectedPreset || null;
		const cron = rawCron?.trim() || null;

		// Basic cron validation for custom expressions
		if (cron && selectedPreset === 'custom') {
			const parts = cron.split(/\s+/);
			if (parts.length !== 5) {
				scheduleError.set('Cron expression must have exactly 5 fields (minute hour day month weekday)');
				return;
			}
		}

		try {
			const updated = await saveSchedule($selectedAoiId, {
				processingSchedule: cron,
				processingEnabled: cron !== null,
				maxCloudCover: localMaxCloud
			});
			// Also update the selectedAoi store so other components see the change
			selectedAoi.set(updated);
			hasUnsavedChanges = false;
		} catch {
			// Error is already set in scheduleError store
		}
	}

	async function handleToggleEnabled() {
		if (!$selectedAoiId) return;
		try {
			const updated = await saveSchedule($selectedAoiId, {
				processingEnabled: !$scheduleConfig.processingEnabled
			});
			selectedAoi.set(updated);
		} catch {
			// Error handled by store
		}
	}

	async function loadScheduledRuns(aoiId: string) {
		loadingAoiId = aoiId;
		try {
			const runs = await api.getProcessingRuns(aoiId);
			if (loadingAoiId !== aoiId) return; // AOI changed while loading
			scheduledRuns.set(runs.slice(0, 5));
		} catch {
			if (loadingAoiId !== aoiId) return;
			scheduledRuns.set([]);
		}
	}

	function getStatusBadgeClass(status: string): string {
		switch (status) {
			case 'Completed': return 'badge-success';
			case 'Failed': return 'badge-danger';
			case 'Pending': return 'badge-muted';
			default: return 'badge-active';
		}
	}

	function getScheduleStatusClass(config: typeof $scheduleConfig): 'active' | 'paused' | 'none' {
		if (!config.processingSchedule) return 'none';
		if (config.processingEnabled) return 'active';
		return 'paused';
	}

	$: scheduleStatus = getScheduleStatusClass($scheduleConfig);
</script>

{#if $selectedAoiId}
<div class="panel">
	<button class="panel-header" on:click={() => expanded = !expanded}>
		<div class="panel-title">
			<span>Scheduling</span>
			<span class="status-badge" class:active={scheduleStatus === 'active'} class:paused={scheduleStatus === 'paused'}>
				{scheduleStatus === 'active' ? 'Active' : scheduleStatus === 'paused' ? 'Paused' : 'Off'}
			</span>
		</div>
		<span class="chevron" class:collapsed={!expanded}>&#9660;</span>
	</button>

	{#if expanded}
	<div class="panel-body">
		<!-- Schedule Settings -->
		<div class="section">
			<div class="section-title">Schedule Settings</div>

			<div class="field">
				<label for="frequency">Frequency</label>
				<select id="frequency" value={selectedPreset} on:change={handlePresetChange}>
					<option value="">Not scheduled</option>
					{#each cronPresets as preset}
						<option value={preset.cron}>{preset.label}</option>
					{/each}
					<option value="custom">Custom cron...</option>
				</select>
			</div>

			{#if showCustomInput}
			<div class="field">
				<label for="customCron">Cron expression</label>
				<input
					id="customCron"
					type="text"
					bind:value={customCron}
					placeholder="0 */6 * * *"
					on:input={() => hasUnsavedChanges = true}
				/>
			</div>
			{/if}

			<div class="field">
				<label for="maxCloud">Max cloud cover: {localMaxCloud}%</label>
				<input
					id="maxCloud"
					type="range"
					min="5"
					max="80"
					step="5"
					value={localMaxCloud}
					on:input={handleCloudChange}
				/>
				<div class="range-labels">
					<span>5%</span>
					<span>80%</span>
				</div>
			</div>

			{#if hasUnsavedChanges}
			<button class="btn btn-primary" on:click={handleSave} disabled={$scheduleSaving}>
				{$scheduleSaving ? 'Saving...' : 'Save Schedule'}
			</button>
			{/if}

			{#if $scheduleConfig.processingSchedule}
			<button
				class="btn btn-toggle"
				class:enabled={$scheduleConfig.processingEnabled}
				on:click={handleToggleEnabled}
				disabled={$scheduleSaving}
			>
				{$scheduleConfig.processingEnabled ? 'Pause Scheduling' : 'Enable Scheduling'}
			</button>
			{/if}

			{#if $scheduleError}
			<div class="error-msg">{$scheduleError}</div>
			{/if}
		</div>

		<!-- Status Info -->
		<div class="section">
			<div class="section-title">Status</div>
			<div class="info-grid">
				<div class="info-item">
					<span class="info-label">Schedule</span>
					<span class="info-value">{describeCron($scheduleConfig.processingSchedule)}</span>
				</div>
				<div class="info-item">
					<span class="info-label">Last checked</span>
					<span class="info-value">{timeAgo($scheduleConfig.lastCheckedAt)}</span>
				</div>
				<div class="info-item">
					<span class="info-label">Last processed</span>
					<span class="info-value">{timeAgo($scheduleConfig.lastProcessedAt)}</span>
				</div>
			</div>
		</div>

		<!-- Recent Runs -->
		{#if $scheduledRuns.length > 0}
		<div class="section">
			<div class="section-title">Recent Runs</div>
			<div class="run-list">
				{#each $scheduledRuns as run}
				<div class="run-item">
					<span class="run-date">{new Date(run.createdAt).toLocaleDateString()}</span>
					<span class="run-badge {getStatusBadgeClass(run.statusName)}">{run.statusName}</span>
					<span class="run-stats">
						{run.changePolygonCount} changes, {run.riskEventCount} risks
					</span>
				</div>
				{/each}
			</div>
		</div>
		{/if}
	</div>
	{/if}
</div>
{/if}

<style>
	.panel {
		background: var(--color-surface);
		border: 1px solid var(--color-border);
		border-radius: var(--radius-md);
		overflow: hidden;
	}

	.panel-header {
		width: 100%;
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 0.75rem 1rem;
		background: none;
		border: none;
		cursor: pointer;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--color-text);
	}

	.panel-header:hover {
		background: var(--color-bg);
	}

	.panel-title {
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

	.status-badge {
		font-size: 0.625rem;
		font-weight: 600;
		padding: 0.125rem 0.375rem;
		border-radius: var(--radius-sm);
		text-transform: uppercase;
		background: var(--color-bg);
		color: var(--color-text-muted);
	}

	.status-badge.active {
		background: #dcfce7;
		color: #166534;
	}

	.status-badge.paused {
		background: #fef3c7;
		color: #92400e;
	}

	.panel-body {
		padding: 0 1rem 1rem;
	}

	.section {
		margin-bottom: 1rem;
	}

	.section:last-child {
		margin-bottom: 0;
	}

	.section-title {
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--color-text-muted);
		margin-bottom: 0.5rem;
	}

	.field {
		margin-bottom: 0.75rem;
	}

	.field label {
		display: block;
		font-size: 0.75rem;
		color: var(--color-text-muted);
		margin-bottom: 0.25rem;
	}

	.field select,
	.field input[type="text"] {
		width: 100%;
		padding: 0.375rem 0.5rem;
		font-size: 0.75rem;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		background: var(--color-surface);
		color: var(--color-text);
	}

	.field input[type="range"] {
		width: 100%;
		margin-top: 0.25rem;
	}

	.range-labels {
		display: flex;
		justify-content: space-between;
		font-size: 0.625rem;
		color: var(--color-text-muted);
	}

	.btn {
		width: 100%;
		padding: 0.5rem;
		font-size: 0.75rem;
		font-weight: 500;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-sm);
		cursor: pointer;
		margin-top: 0.5rem;
	}

	.btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-primary {
		background: var(--color-primary);
		color: white;
		border-color: var(--color-primary);
	}

	.btn-primary:hover:not(:disabled) {
		opacity: 0.9;
	}

	.btn-toggle {
		background: var(--color-surface);
		color: var(--color-text);
	}

	.btn-toggle.enabled {
		color: var(--color-warning);
		border-color: var(--color-warning);
	}

	.btn-toggle:hover:not(:disabled) {
		background: var(--color-bg);
	}

	.error-msg {
		margin-top: 0.5rem;
		padding: 0.375rem 0.5rem;
		font-size: 0.6875rem;
		color: var(--color-danger);
		background: #fef2f2;
		border-radius: var(--radius-sm);
	}

	.info-grid {
		display: grid;
		gap: 0.5rem;
	}

	.info-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		font-size: 0.75rem;
	}

	.info-label {
		color: var(--color-text-muted);
	}

	.info-value {
		color: var(--color-text);
		font-weight: 500;
	}

	.run-list {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.run-item {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.375rem 0;
		font-size: 0.6875rem;
		border-bottom: 1px solid var(--color-border);
	}

	.run-item:last-child {
		border-bottom: none;
	}

	.run-date {
		color: var(--color-text-muted);
		min-width: 5rem;
	}

	.run-badge {
		padding: 0.0625rem 0.25rem;
		border-radius: var(--radius-sm);
		font-size: 0.5625rem;
		font-weight: 600;
		text-transform: uppercase;
	}

	.badge-success {
		background: #dcfce7;
		color: #166534;
	}

	.badge-danger {
		background: #fef2f2;
		color: #991b1b;
	}

	.badge-muted {
		background: var(--color-bg);
		color: var(--color-text-muted);
	}

	.badge-active {
		background: #dbeafe;
		color: #1e40af;
	}

	.run-stats {
		color: var(--color-text-muted);
		margin-left: auto;
	}
</style>
