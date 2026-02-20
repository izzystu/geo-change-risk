<script lang="ts">
	import { RiskLevelColors, type RiskEvent, type RiskEventSummary } from '$lib/services/api';
	import { parseFactors, generateSuggestedAction, type ScoringFactor } from '$lib/utils/riskSummary';

	export let open = false;
	export let event: RiskEventSummary | null = null;
	export let detail: RiskEvent | null = null;
	export let onClose: () => void = () => { open = false; };

	$: factors = detail ? parseFactors(detail.scoringFactors) : [];
	$: suggestedAction = event ? generateSuggestedAction(event.riskLevelName, factors, event.assetTypeName) : '';
	$: landslideFactor = factors.find(f => f.reason_code?.startsWith('LANDSLIDE_') && f.reason_code !== 'LANDSLIDE_LOW_SLOPE');
	$: ndviFactor = factors.find(f => f.reason_code?.startsWith('NDVI_DROP_'));
	$: landCoverFactor = factors.find(f => f.reason_code?.startsWith('LANDCOVER_'));
	$: slopeFactor = factors.find(f => f.reason_code?.startsWith('SLOPE_'));
	$: distanceFactor = factors.find(f => f.name === 'Distance');
	$: criticalityFactor = factors.find(f => f.reason_code?.startsWith('CRITICALITY_'));

	function formatDistance(meters: number): string {
		if (meters < 1000) return `${Math.round(meters)}m`;
		return `${(meters / 1000).toFixed(1)}km`;
	}

	function getNdviLabel(code: string): string {
		const labels: Record<string, string> = {
			NDVI_DROP_SEVERE: 'Severe vegetation loss',
			NDVI_DROP_STRONG: 'Significant vegetation loss',
			NDVI_DROP_MODERATE: 'Moderate vegetation loss',
			NDVI_DROP_MILD: 'Mild vegetation change',
		};
		return labels[code] ?? 'Vegetation change detected';
	}

	function extractLandCover(factor: ScoringFactor): string {
		const match = factor.details?.match(/^Land cover: (\S+)/);
		return match ? match[1] : 'Unknown';
	}
</script>

{#if open && event}
<div class="dialog-overlay" on:click={onClose} role="presentation">
	<div class="dialog" on:click|stopPropagation role="dialog">
		<div class="dialog-header">
			<h3>Take Action</h3>
			<button class="close-x" on:click={onClose}>&times;</button>
		</div>

		<div class="event-identity">
			<span
				class="risk-badge"
				style="background-color: {RiskLevelColors[event.riskLevelName]}"
			>
				{event.riskScore}
			</span>
			<div class="identity-text">
				<span class="asset-name">{event.assetName}</span>
				<span class="asset-meta">{event.assetTypeName} &middot; {formatDistance(event.distanceMeters)} away</span>
			</div>
		</div>

		{#if detail}
			<div class="findings">
				<h4>Key Findings</h4>

				{#if landslideFactor}
					<div class="finding finding-critical">
						<span class="finding-icon">&#x26A0;</span>
						<div class="finding-text">
							<strong>Landslide debris detected</strong>
							<span class="finding-detail">{landslideFactor.details}</span>
						</div>
					</div>
				{/if}

				{#if ndviFactor}
					<div class="finding finding-warn">
						<span class="finding-icon">&#x25CF;</span>
						<div class="finding-text">
							<strong>{getNdviLabel(ndviFactor.reason_code)}</strong>
							<span class="finding-detail">{ndviFactor.details}</span>
						</div>
					</div>
				{/if}

				{#if slopeFactor}
					<div class="finding finding-info">
						<span class="finding-icon">&#x25B2;</span>
						<div class="finding-text">
							<strong>Terrain</strong>
							<span class="finding-detail">{slopeFactor.details}</span>
						</div>
					</div>
				{/if}

				{#if landCoverFactor}
					<div class="finding finding-info">
						<span class="finding-icon">&#x25CB;</span>
						<div class="finding-text">
							<strong>Land cover: {extractLandCover(landCoverFactor)}</strong>
							<span class="finding-detail">{landCoverFactor.details}</span>
						</div>
					</div>
				{/if}

				{#if criticalityFactor}
					<div class="finding finding-info">
						<span class="finding-icon">&#x2605;</span>
						<div class="finding-text">
							<strong>Asset criticality</strong>
							<span class="finding-detail">{criticalityFactor.details}</span>
						</div>
					</div>
				{/if}
			</div>

			<div class="scoring-summary">
				<h4>Score Breakdown</h4>
				<div class="factor-bars">
					{#each factors as factor}
						<div class="factor-row">
							<span class="factor-name">{factor.name}</span>
							{#if factor.max_points > 0}
								<div class="factor-bar-track">
									<div
										class="factor-bar-fill"
										style="width: {Math.min(100, (factor.points / factor.max_points) * 100)}%"
									></div>
								</div>
								<span class="factor-pts">{factor.points}/{factor.max_points}</span>
							{:else}
								<span class="factor-detail-text">{factor.details}</span>
							{/if}
						</div>
					{/each}
				</div>
			</div>
		{:else}
			<div class="loading-detail">Loading event details...</div>
		{/if}

		<div class="recommended-action">
			<h4>Recommended Action</h4>
			<p>{suggestedAction}</p>
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
		padding: 1.25rem;
		max-width: 520px;
		width: 90%;
		max-height: 92vh;
		overflow-y: auto;
		box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.dialog-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.dialog-header h3 {
		margin: 0;
		font-size: 1.1rem;
		color: var(--color-text, #333);
	}

	.close-x {
		background: none;
		border: none;
		font-size: 1.25rem;
		cursor: pointer;
		color: var(--color-text-muted, #999);
		padding: 0.25rem;
		line-height: 1;
	}

	.close-x:hover {
		color: var(--color-text, #333);
	}

	.event-identity {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.75rem;
		background: var(--color-bg, #f9fafb);
		border-radius: 6px;
	}

	.risk-badge {
		font-size: 1rem;
		padding: 0.25rem 0.5rem;
		border-radius: 4px;
		color: white;
		font-weight: 700;
		min-width: 2.25rem;
		text-align: center;
	}

	.identity-text {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.asset-name {
		font-size: 0.9375rem;
		font-weight: 600;
		color: var(--color-text, #333);
	}

	.asset-meta {
		font-size: 0.75rem;
		color: var(--color-text-muted, #666);
	}

	.findings {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.findings h4, .scoring-summary h4, .recommended-action h4 {
		margin: 0;
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--color-text, #333);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.finding {
		display: flex;
		gap: 0.5rem;
		padding: 0.5rem 0.625rem;
		border-radius: 4px;
		border-left: 3px solid transparent;
	}

	.finding-critical {
		background: #fef2f2;
		border-left-color: #ef4444;
	}

	.finding-warn {
		background: #fffbeb;
		border-left-color: #f59e0b;
	}

	.finding-info {
		background: var(--color-bg, #f9fafb);
		border-left-color: var(--color-border, #e5e7eb);
	}

	.finding-icon {
		flex-shrink: 0;
		font-size: 0.875rem;
		line-height: 1.4;
	}

	.finding-critical .finding-icon {
		color: #ef4444;
	}

	.finding-warn .finding-icon {
		color: #f59e0b;
	}

	.finding-info .finding-icon {
		color: var(--color-text-muted, #999);
	}

	.finding-text {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
		font-size: 0.8125rem;
		line-height: 1.4;
	}

	.finding-text strong {
		color: var(--color-text, #333);
	}

	.finding-detail {
		font-size: 0.75rem;
		color: var(--color-text-muted, #666);
	}

	.scoring-summary {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.factor-bars {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.factor-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.75rem;
	}

	.factor-name {
		min-width: 6.5rem;
		color: var(--color-text-muted, #666);
		flex-shrink: 0;
	}

	.factor-bar-track {
		flex: 1;
		height: 0.375rem;
		background: var(--color-border, #e5e7eb);
		border-radius: 2px;
		overflow: hidden;
	}

	.factor-bar-fill {
		height: 100%;
		border-radius: 2px;
		background: var(--color-primary, #3b82f6);
	}

	.factor-pts {
		min-width: 2.5rem;
		text-align: right;
		color: var(--color-text-muted, #666);
		font-size: 0.6875rem;
	}

	.factor-detail-text {
		flex: 1;
		color: var(--color-text-muted, #666);
		font-size: 0.6875rem;
	}

	.loading-detail {
		font-size: 0.8125rem;
		color: var(--color-text-muted, #666);
		font-style: italic;
		padding: 0.5rem 0;
	}

	.recommended-action {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		padding: 0.75rem;
		background: #eff6ff;
		border-radius: 6px;
		border-left: 3px solid var(--color-primary, #3b82f6);
	}

	.recommended-action p {
		margin: 0;
		font-size: 0.8125rem;
		color: var(--color-text, #333);
		line-height: 1.5;
	}

	.actions {
		display: flex;
		gap: 0.5rem;
		justify-content: flex-end;
		padding-top: 0.25rem;
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
