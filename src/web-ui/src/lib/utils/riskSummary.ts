/**
 * Utilities for parsing risk scoring factors and generating
 * human-readable summaries and suggested actions.
 */

export interface ScoringFactor {
	name: string;
	points: number;
	max_points: number;
	reason_code: string;
	details: string;
}

/**
 * Extract the factors array from the scoringFactors JSON blob.
 */
export function parseFactors(scoringFactors: Record<string, unknown> | undefined): ScoringFactor[] {
	if (!scoringFactors) return [];
	const factors = scoringFactors.factors as ScoringFactor[] | undefined;
	return factors ?? [];
}

const NDVI_SEVERITY: Record<string, string> = {
	NDVI_DROP_SEVERE: 'Severe vegetation loss',
	NDVI_DROP_STRONG: 'Significant vegetation loss',
	NDVI_DROP_MODERATE: 'Moderate vegetation loss',
	NDVI_DROP_MILD: 'Mild vegetation change'
};

/**
 * Generate a 1-2 sentence natural-language summary of the risk event.
 */
export function generateSummary(
	factors: ScoringFactor[],
	assetName: string,
	riskLevel: string
): string {
	const ndviFactor = factors.find(f => f.reason_code?.startsWith('NDVI_DROP_'));
	const distFactor = factors.find(f => f.name === 'Distance');
	const slopeFactor = factors.find(f => f.reason_code?.startsWith('SLOPE_'));

	const ndviText = ndviFactor ? (NDVI_SEVERITY[ndviFactor.reason_code] ?? 'Vegetation change') : 'Change';

	// Extract distance value from details like "Distance: 350m"
	let distText = '';
	if (distFactor?.details) {
		const match = distFactor.details.match(/Distance:\s*([\d,.]+)m/);
		if (match) {
			distText = ` ${match[1]}m from`;
		} else {
			distText = ' near';
		}
	} else {
		distText = ' near';
	}

	let summary = `${ndviText} detected${distText} ${assetName}.`;

	// Add slope context if upslope
	if (slopeFactor?.reason_code === 'SLOPE_UPSLOPE') {
		summary += ' Change is upslope, increasing debris/erosion risk.';
	}

	return summary;
}

/**
 * Generate a suggested action based on risk level and scoring factors.
 */
export function generateSuggestedAction(
	riskLevel: string,
	factors: ScoringFactor[],
	assetTypeName: string
): string {
	const slopeFactor = factors.find(f => f.reason_code?.startsWith('SLOPE_'));
	const isUpslope = slopeFactor?.reason_code === 'SLOPE_UPSLOPE';

	let action: string;
	switch (riskLevel) {
		case 'Critical':
			action = `Immediate site inspection recommended. Consider protective measures for ${assetTypeName}.`;
			break;
		case 'High':
			action = `Schedule site inspection within 48 hours. Monitor for further changes near ${assetTypeName}.`;
			break;
		case 'Medium':
			action = `Flag for review during next scheduled inspection of ${assetTypeName}.`;
			break;
		default:
			action = 'No immediate action required. Continue routine monitoring.';
			break;
	}

	if (isUpslope && (riskLevel === 'Critical' || riskLevel === 'High')) {
		action += ' Upslope position warrants priority attention for slope stability.';
	}

	return action;
}

/**
 * Return a CSS color for a factor's mini bar chart based on its
 * points/max_points ratio. Multiplier factors (max_points === 0) get gray.
 */
export function getFactorBarColor(factor: ScoringFactor): string {
	if (factor.max_points === 0) return '#6b7280'; // gray for multipliers

	const ratio = factor.points / factor.max_points;
	if (ratio >= 0.75) return '#ef4444'; // red
	if (ratio >= 0.5) return '#f97316';  // orange
	if (ratio >= 0.25) return '#f59e0b'; // amber
	return '#22c55e';                     // green
}
