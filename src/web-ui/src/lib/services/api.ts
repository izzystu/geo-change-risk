import { PUBLIC_API_URL } from '$env/static/public';

const API_BASE = PUBLIC_API_URL || 'http://localhost:5074';

export interface AreaOfInterestSummary {
	aoiId: string;
	name: string;
	assetCount: number;
}

export interface AreaOfInterest {
	aoiId: string;
	name: string;
	description?: string;
	boundingBox: [number, number, number, number]; // [minX, minY, maxX, maxY]
	center: [number, number];
	assetCount: number;
	createdAt: string;
	processingSchedule: string | null;
	processingEnabled: boolean;
	lastProcessedAt: string | null;
	defaultLookbackDays: number;
	maxCloudCover: number;
	lastCheckedAt: string | null;
}

export interface Asset {
	id: number;
	areaOfInterestId: number;
	name: string;
	assetType: number;
	criticality: number;
	geometry: GeoJSON.Geometry;
	properties?: Record<string, unknown>;
	sourceDataset?: string;
	sourceFeatureId?: string;
	createdAt: string;
	updatedAt: string;
}

export interface AssetGeoJSON {
	type: 'FeatureCollection';
	features: GeoJSON.Feature[];
}

export interface ImageryFile {
	fileName: string;
	objectPath: string;
	size: number;
	lastModified: string;
}

export interface ImageryScene {
	sceneId: string;
	aoiId: string;
	files: ImageryFile[];
	lastModified: string;
}

export interface ImageryFileWithUrl extends ImageryFile {
	presignedUrl: string;
}

export interface ImagerySceneDetail {
	sceneId: string;
	aoiId: string;
	bounds: [number, number, number, number];
	files: ImageryFileWithUrl[];
	/** Presigned URL for web display (PNG preferred over TIF) */
	displayUrl?: string;
	lastModified: string;
}

export interface ImageryUploadResult {
	objectPath: string;
	size: number;
	presignedUrl: string;
	message: string;
}

// Processing types
export interface ProcessingRunSummary {
	runId: string;
	aoiId: string;
	statusName: string;
	beforeDate: string;
	afterDate: string;
	createdAt: string;
	changePolygonCount: number;
	riskEventCount: number;
}

export interface ProcessingRun extends ProcessingRunSummary {
	status: number;
	beforeSceneId?: string;
	afterSceneId?: string;
	startedAt?: string;
	completedAt?: string;
	errorMessage?: string;
	metadata?: Record<string, unknown>;
	riskEventCount: number;
}

export interface CreateProcessingRunRequest {
	aoiId: string;
	beforeDate: string;
	afterDate: string;
	parameters?: Record<string, unknown>;
}

export interface UpdateAoiScheduleRequest {
	processingSchedule?: string | null;
	processingEnabled?: boolean;
	defaultLookbackDays?: number;
	maxCloudCover?: number;
}

// Risk event types
export interface RiskEventSummary {
	riskEventId: string;
	assetId: string;
	assetName: string;
	assetTypeName: string;
	riskScore: number;
	riskLevelName: string;
	distanceMeters: number;
	createdAt: string;
	isAcknowledged: boolean;
	isDismissed: boolean;
}

export interface RiskEvent extends RiskEventSummary {
	changePolygonId: string;
	riskLevel: number;
	scoringFactors?: Record<string, unknown>;
	notificationSentAt?: string;
	acknowledgedAt?: string;
	acknowledgedBy?: string;
	dismissedAt?: string;
	dismissedBy?: string;
	aoiId?: string;
	changeGeometry?: GeoJSON.Geometry;
	assetGeometry?: GeoJSON.Geometry;
}

export interface RiskEventStats {
	aoiId: string;
	totalEvents: number;
	unacknowledgedEvents: number;
	byRiskLevel: Record<string, number>;
}

export const RiskLevelColors: Record<string, string> = {
	'Low': '#22c55e',      // green
	'Medium': '#f59e0b',   // amber
	'High': '#f97316',     // orange
	'Critical': '#ef4444'  // red
};

export const AssetTypeLabels: Record<number, string> = {
	0: 'Transmission Line',
	1: 'Substation',
	2: 'Gas Pipeline',
	3: 'Building',
	4: 'Road',
	5: 'Fire Station',
	6: 'Hospital',
	7: 'School',
	8: 'Water Infrastructure',
	99: 'Other'
};

export const CriticalityLabels: Record<number, string> = {
	0: 'Low',
	1: 'Medium',
	2: 'High',
	3: 'Critical'
};

export const CriticalityColors: Record<number, string> = {
	0: '#22c55e', // green
	1: '#f59e0b', // amber
	2: '#f97316', // orange
	3: '#ef4444'  // red
};

function getAuthHeaders(): Record<string, string> {
	if (typeof localStorage === 'undefined') return {};
	const key = localStorage.getItem('georisk_api_key');
	if (key) return { 'X-Api-Key': key };
	return {};
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
	const response = await fetch(url, {
		...options,
		headers: {
			'Content-Type': 'application/json',
			...getAuthHeaders(),
			...options?.headers
		}
	});

	if (response.status === 401) {
		if (typeof window !== 'undefined') {
			window.dispatchEvent(new CustomEvent('georisk:unauthorized'));
		}
		throw new Error('Unauthorized — invalid or missing API key');
	}

	if (!response.ok) {
		throw new Error(`API error: ${response.status} ${response.statusText}`);
	}

	return response.json();
}

export const api = {
	// Health check
	async getHealth(): Promise<{ status: string; database: string }> {
		return fetchJson(`${API_BASE}/api/system/health`);
	},

	// Areas of Interest
	async getAreasOfInterest(): Promise<AreaOfInterestSummary[]> {
		return fetchJson(`${API_BASE}/api/areas-of-interest`);
	},

	async getAreaOfInterest(id: string): Promise<AreaOfInterest> {
		return fetchJson(`${API_BASE}/api/areas-of-interest/${id}`);
	},

	async updateAoiSchedule(aoiId: string, request: UpdateAoiScheduleRequest): Promise<AreaOfInterest> {
		return fetchJson(`${API_BASE}/api/areas-of-interest/${aoiId}/schedule`, {
			method: 'PUT',
			body: JSON.stringify(request)
		});
	},

	async getScheduledAois(): Promise<AreaOfInterestSummary[]> {
		return fetchJson(`${API_BASE}/api/areas-of-interest/scheduled`);
	},

	// Assets
	async getAssets(aoiId: string): Promise<Asset[]> {
		return fetchJson(`${API_BASE}/api/assets?aoiId=${aoiId}`);
	},

	async getAssetsGeoJSON(aoiId: string, assetTypes?: number[]): Promise<AssetGeoJSON> {
		let url = `${API_BASE}/api/assets/geojson?aoiId=${aoiId}`;
		if (assetTypes && assetTypes.length > 0) {
			url += `&assetTypes=${assetTypes.join(',')}`;
		}
		return fetchJson(url);
	},

	async getAsset(id: number): Promise<Asset> {
		return fetchJson(`${API_BASE}/api/assets/${id}`);
	},

	// Imagery
	async getImageryScenes(aoiId: string): Promise<ImageryScene[]> {
		return fetchJson(`${API_BASE}/api/imagery/${aoiId}`);
	},

	async getImageryScene(aoiId: string, sceneId: string): Promise<ImagerySceneDetail> {
		return fetchJson(`${API_BASE}/api/imagery/${aoiId}/${sceneId}`);
	},

	async uploadImagery(aoiId: string, sceneId: string, file: File, fileName?: string): Promise<ImageryUploadResult> {
		const formData = new FormData();
		formData.append('file', file);

		let url = `${API_BASE}/api/imagery/${aoiId}/upload?sceneId=${encodeURIComponent(sceneId)}`;
		if (fileName) {
			url += `&fileName=${encodeURIComponent(fileName)}`;
		}

		const response = await fetch(url, {
			method: 'POST',
			headers: getAuthHeaders(),
			body: formData
		});

		if (response.status === 401) {
			if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('georisk:unauthorized'));
			throw new Error('Unauthorized — invalid or missing API key');
		}

		if (!response.ok) {
			throw new Error(`Upload failed: ${response.status} ${response.statusText}`);
		}

		return response.json();
	},

	async deleteImageryScene(aoiId: string, sceneId: string): Promise<void> {
		const response = await fetch(`${API_BASE}/api/imagery/${aoiId}/${sceneId}`, {
			method: 'DELETE',
			headers: getAuthHeaders()
		});

		if (response.status === 401) {
			if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('georisk:unauthorized'));
			throw new Error('Unauthorized — invalid or missing API key');
		}

		if (!response.ok) {
			throw new Error(`Delete failed: ${response.status} ${response.statusText}`);
		}
	},

	// Processing runs
	async getProcessingRuns(aoiId: string): Promise<ProcessingRunSummary[]> {
		return fetchJson(`${API_BASE}/api/processing/runs?aoiId=${aoiId}`);
	},

	async getProcessingRun(runId: string): Promise<ProcessingRun> {
		return fetchJson(`${API_BASE}/api/processing/runs/${runId}`);
	},

	async createProcessingRun(request: CreateProcessingRunRequest): Promise<ProcessingRun> {
		return fetchJson(`${API_BASE}/api/processing/runs`, {
			method: 'POST',
			body: JSON.stringify(request)
		});
	},

	async getChangesGeoJSON(aoiId: string, runId?: string): Promise<AssetGeoJSON> {
		let url = `${API_BASE}/api/changes/geojson?aoiId=${aoiId}`;
		if (runId) {
			url += `&runId=${runId}`;
		}
		return fetchJson(url);
	},

	// Risk events
	async getRiskEvents(params: {
		aoiId?: string;
		runId?: string;
		minScore?: number;
		riskLevel?: number;
		limit?: number;
	} = {}): Promise<RiskEventSummary[]> {
		const searchParams = new URLSearchParams();
		if (params.aoiId) searchParams.set('aoiId', params.aoiId);
		if (params.runId) searchParams.set('runId', params.runId);
		if (params.minScore !== undefined) searchParams.set('minScore', params.minScore.toString());
		if (params.riskLevel !== undefined) searchParams.set('riskLevel', params.riskLevel.toString());
		if (params.limit) searchParams.set('limit', params.limit.toString());

		return fetchJson(`${API_BASE}/api/risk-events?${searchParams}`);
	},

	async getRiskEvent(id: string): Promise<RiskEvent> {
		return fetchJson(`${API_BASE}/api/risk-events/${id}`);
	},

	async getRiskEventsByAsset(assetId: string): Promise<RiskEventSummary[]> {
		return fetchJson(`${API_BASE}/api/risk-events/by-asset/${assetId}`);
	},

	async getUnacknowledgedEvents(aoiId?: string, minLevel?: number): Promise<RiskEventSummary[]> {
		const searchParams = new URLSearchParams();
		if (aoiId) searchParams.set('aoiId', aoiId);
		if (minLevel !== undefined) searchParams.set('minLevel', minLevel.toString());

		return fetchJson(`${API_BASE}/api/risk-events/unacknowledged?${searchParams}`);
	},

	async acknowledgeRiskEvent(id: string, acknowledgedBy: string, notes?: string): Promise<RiskEvent> {
		return fetchJson(`${API_BASE}/api/risk-events/${id}/acknowledge`, {
			method: 'POST',
			body: JSON.stringify({ acknowledgedBy, notes })
		});
	},

	async dismissRiskEvent(id: string, dismissedBy: string, reason?: string): Promise<RiskEvent> {
		return fetchJson(`${API_BASE}/api/risk-events/${id}/dismiss`, {
			method: 'POST',
			body: JSON.stringify({ dismissedBy, reason })
		});
	},

	async getRiskEventStats(aoiId: string): Promise<RiskEventStats> {
		return fetchJson(`${API_BASE}/api/risk-events/stats?aoiId=${aoiId}`);
	},

	// Delete processing run
	async deleteProcessingRun(runId: string): Promise<void> {
		const response = await fetch(`${API_BASE}/api/processing/runs/${runId}`, {
			method: 'DELETE',
			headers: getAuthHeaders()
		});

		if (response.status === 401) {
			if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('georisk:unauthorized'));
			throw new Error('Unauthorized — invalid or missing API key');
		}

		if (!response.ok) {
			throw new Error(`Delete failed: ${response.status} ${response.statusText}`);
		}
	},

	// Get change polygons GeoJSON for a specific run
	async getRunChangesGeoJson(runId: string): Promise<AssetGeoJSON> {
		return fetchJson(`${API_BASE}/api/processing/runs/${runId}/changes/geojson`);
	}
};
