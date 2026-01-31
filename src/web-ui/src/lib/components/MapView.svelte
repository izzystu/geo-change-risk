<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { selectedAoi, zoomToAoiTrigger } from '$lib/stores/aoi';
	import { layers, selectedBasemap } from '$lib/stores/layers';
	import {
		showBeforeImagery,
		showAfterImagery,
		beforeSceneDetail,
		afterSceneDetail,
		imageryOpacity
	} from '$lib/stores/imagery';
	import {
		selectedRunId,
		changePolygonsGeoJson,
		showChangePolygons
	} from '$lib/stores/processing';
	import { api, type RiskEvent } from '$lib/services/api';

	let mapContainer: HTMLDivElement;
	let map: __esri.Map | null = null;
	let mapView: __esri.MapView | null = null;
	let mapReady = false;
	let assetLayers: Map<number, __esri.GeoJSONLayer> = new Map();
	let beforeImageryLayer: __esri.MediaLayer | null = null;
	let afterImageryLayer: __esri.MediaLayer | null = null;
	let changePolygonLayer: __esri.GeoJSONLayer | null = null;

	// Track current AOI to detect changes
	let currentAoiId: string | null = null;
	let currentRunId: string | null = null;

	onMount(async () => {
		const [
			{ default: Map },
			{ default: MapView }
		] = await Promise.all([
			import('@arcgis/core/Map'),
			import('@arcgis/core/views/MapView')
		]);

		map = new Map({
			basemap: $selectedBasemap === 'none' ? undefined : $selectedBasemap
		});

		mapView = new MapView({
			container: mapContainer,
			map,
			center: [-121.62, 39.76],
			zoom: 12
		});

		await mapView.when();
		mapReady = true;

		// If AOI was already selected before map was ready, load it now
		if ($selectedAoi && $selectedAoi.aoiId !== currentAoiId) {
			currentAoiId = $selectedAoi.aoiId;
			zoomToAoi($selectedAoi);
			loadAssets($selectedAoi.aoiId);
		}
	});

	onDestroy(() => {
		if (mapView) {
			mapView.destroy();
			mapView = null;
			map = null;
		}
	});

	// React to AOI changes (only when map is ready)
	$: if ($selectedAoi && mapReady && $selectedAoi.aoiId !== currentAoiId) {
		currentAoiId = $selectedAoi.aoiId;
		zoomToAoi($selectedAoi);
		loadAssets($selectedAoi.aoiId);
	}

	// React to layer visibility changes
	$: updateLayerVisibility($layers);

	// React to basemap changes
	$: if (map && mapReady) {
		updateBasemap($selectedBasemap);
	}

	// React to zoom-to-AOI requests
	$: if ($zoomToAoiTrigger && mapReady && $selectedAoi) {
		zoomToAoi($selectedAoi);
	}

	// React to before imagery changes
	$: if (mapReady) {
		updateBeforeImagery($showBeforeImagery, $beforeSceneDetail, $imageryOpacity);
	}

	// React to after imagery changes
	$: if (mapReady) {
		updateAfterImagery($showAfterImagery, $afterSceneDetail, $imageryOpacity);
	}

	// React to opacity changes
	$: if (mapReady) {
		updateImageryOpacity($imageryOpacity);
	}

	// React to processing run selection changes - load change polygons
	$: if (mapReady && $selectedRunId !== currentRunId) {
		currentRunId = $selectedRunId;
		loadChangePolygons($selectedRunId);
	}

	// React to change polygon visibility toggle
	$: if (changePolygonLayer) {
		changePolygonLayer.visible = $showChangePolygons;
	}

	function updateBasemap(basemapId: string) {
		if (!map) return;
		if (basemapId === 'none') {
			map.basemap = null as any;
		} else {
			map.basemap = basemapId as any;
		}
	}

	async function zoomToAoi(aoi: typeof $selectedAoi) {
		if (!mapView || !aoi || !aoi.boundingBox) return;

		const { default: Extent } = await import('@arcgis/core/geometry/Extent');
		const [minX, minY, maxX, maxY] = aoi.boundingBox;

		const extent = new Extent({
			xmin: minX,
			ymin: minY,
			xmax: maxX,
			ymax: maxY,
			spatialReference: { wkid: 4326 }
		});

		mapView.goTo(extent.expand(1.1));
	}

	async function loadAssets(aoiId: string) {
		if (!mapView) return;

		const { default: GeoJSONLayer } = await import('@arcgis/core/layers/GeoJSONLayer');

		// Remove existing layers
		assetLayers.forEach(layer => mapView!.map.remove(layer));
		assetLayers.clear();

		try {
			const geojson = await api.getAssetsGeoJSON(aoiId);

			// Group features by asset type
			const featuresByType = new Map<number, any[]>();
			for (const feature of geojson.features) {
				const assetType = feature.properties?.assetType ?? 9;
				if (!featuresByType.has(assetType)) {
					featuresByType.set(assetType, []);
				}
				featuresByType.get(assetType)!.push(feature);
			}

			// Create a layer for each asset type
			for (const [assetType, features] of featuresByType) {
				const layerConfig = $layers.find(l => l.id === assetType);
				const color = layerConfig?.color ?? '#94a3b8';
				const visible = layerConfig?.visible ?? true;

				const typeGeojson = {
					type: 'FeatureCollection',
					features
				};

				const blob = new Blob([JSON.stringify(typeGeojson)], { type: 'application/json' });
				const url = URL.createObjectURL(blob);

				const geomType = detectGeometryType(features);
				const layer = new GeoJSONLayer({
					url,
					title: layerConfig?.name ?? `Type ${assetType}`,
					visible,
					outFields: ['*'],
					renderer: createRenderer(color, geomType),
					popupTemplate: {
						title: '{name}',
						content: [
							{
								type: 'fields',
								fieldInfos: [
									{ fieldName: 'assetTypeName', label: 'Type' },
									{ fieldName: 'criticalityName', label: 'Criticality' },
									{ fieldName: 'sourceDataset', label: 'Source' }
								]
							}
						]
					}
				});

				assetLayers.set(assetType, layer);
				mapView.map.add(layer);
			}

			console.log(`Loaded ${featuresByType.size} layer groups with ${geojson.features.length} total features`);
		} catch (error) {
			console.error('Failed to load assets:', error);
		}
	}

	function createRenderer(color: string, geometryType: string): any {
		if (geometryType === 'Point' || geometryType === 'MultiPoint') {
			return {
				type: 'simple',
				symbol: {
					type: 'simple-marker',
					color: color,
					size: 8,
					outline: { color: 'white', width: 1 }
				}
			};
		} else if (geometryType === 'LineString' || geometryType === 'MultiLineString') {
			return {
				type: 'simple',
				symbol: {
					type: 'simple-line',
					color: color,
					width: 2
				}
			};
		} else {
			// Polygon
			return {
				type: 'simple',
				symbol: {
					type: 'simple-fill',
					color: hexToRgba(color, 0.5),
					outline: { color: color, width: 1 }
				}
			};
		}
	}

	function detectGeometryType(features: any[]): string {
		for (const f of features) {
			if (f.geometry?.type) {
				return f.geometry.type;
			}
		}
		return 'Polygon';
	}

	function hexToRgba(hex: string, alpha: number): number[] {
		const r = parseInt(hex.slice(1, 3), 16);
		const g = parseInt(hex.slice(3, 5), 16);
		const b = parseInt(hex.slice(5, 7), 16);
		return [r, g, b, alpha * 255];
	}

	function updateLayerVisibility(layerConfigs: typeof $layers) {
		for (const config of layerConfigs) {
			const layer = assetLayers.get(config.id);
			if (layer) {
				layer.visible = config.visible;
			}
		}
	}

	async function updateBeforeImagery(
		show: boolean,
		sceneDetail: typeof $beforeSceneDetail,
		opacity: number
	) {
		if (!map) return;

		// Remove existing layer if not showing or no detail
		if (!show || !sceneDetail) {
			if (beforeImageryLayer) {
				map.remove(beforeImageryLayer);
				beforeImageryLayer = null;
			}
			return;
		}

		// Use displayUrl which prefers PNG (web-compatible) over TIF
		if (!sceneDetail.displayUrl) return;

		await createOrUpdateImageryLayer('before', sceneDetail.displayUrl, sceneDetail.bounds, opacity);
	}

	async function updateAfterImagery(
		show: boolean,
		sceneDetail: typeof $afterSceneDetail,
		opacity: number
	) {
		if (!map) return;

		// Remove existing layer if not showing or no detail
		if (!show || !sceneDetail) {
			if (afterImageryLayer) {
				map.remove(afterImageryLayer);
				afterImageryLayer = null;
			}
			return;
		}

		// Use displayUrl which prefers PNG (web-compatible) over TIF
		if (!sceneDetail.displayUrl) return;

		await createOrUpdateImageryLayer('after', sceneDetail.displayUrl, sceneDetail.bounds, opacity);
	}

	async function createOrUpdateImageryLayer(
		type: 'before' | 'after',
		url: string,
		bounds: [number, number, number, number],
		opacity: number
	) {
		if (!map) return;

		const { default: MediaLayer } = await import('@arcgis/core/layers/MediaLayer');
		const { default: ImageElement } = await import('@arcgis/core/layers/support/ImageElement');
		const { default: ExtentAndRotationGeoreference } = await import('@arcgis/core/layers/support/ExtentAndRotationGeoreference');
		const { default: Extent } = await import('@arcgis/core/geometry/Extent');

		const [minX, minY, maxX, maxY] = bounds;
		const extent = new Extent({
			xmin: minX,
			ymin: minY,
			xmax: maxX,
			ymax: maxY,
			spatialReference: { wkid: 4326 }
		});

		const imageElement = new ImageElement({
			image: url,
			georeference: new ExtentAndRotationGeoreference({
				extent: extent
			})
		});

		const existingLayer = type === 'before' ? beforeImageryLayer : afterImageryLayer;

		if (existingLayer) {
			// Update existing layer
			existingLayer.source.elements.removeAll();
			existingLayer.source.elements.add(imageElement);
			existingLayer.opacity = opacity;
		} else {
			// Create new layer
			const layer = new MediaLayer({
				source: [imageElement],
				title: type === 'before' ? 'Before Imagery' : 'After Imagery',
				opacity: opacity
			});

			// Add at bottom of layer stack (index 0)
			map.add(layer, 0);

			if (type === 'before') {
				beforeImageryLayer = layer;
			} else {
				afterImageryLayer = layer;
			}
		}
	}

	function updateImageryOpacity(opacity: number) {
		if (beforeImageryLayer) {
			beforeImageryLayer.opacity = opacity;
		}
		if (afterImageryLayer) {
			afterImageryLayer.opacity = opacity;
		}
	}

	async function loadChangePolygons(runId: string | null) {
		if (!mapView || !map) return;

		// Remove existing change polygon layer
		if (changePolygonLayer) {
			map.remove(changePolygonLayer);
			changePolygonLayer = null;
		}

		// Clear store if no run selected
		if (!runId) {
			changePolygonsGeoJson.set(null);
			return;
		}

		try {
			const geojson = await api.getRunChangesGeoJson(runId);
			changePolygonsGeoJson.set(geojson);

			if (!geojson.features || geojson.features.length === 0) {
				console.log('No change polygons for run', runId);
				return;
			}

			const { default: GeoJSONLayer } = await import('@arcgis/core/layers/GeoJSONLayer');

			// Create blob URL for the GeoJSON
			const blob = new Blob([JSON.stringify(geojson)], { type: 'application/json' });
			const url = URL.createObjectURL(blob);

			// Create layer with class breaks renderer based on NDVI drop severity
			changePolygonLayer = new GeoJSONLayer({
				url,
				title: 'Change Polygons',
				visible: $showChangePolygons,
				outFields: ['*'],
				renderer: createChangePolygonRenderer(),
				popupTemplate: {
					title: 'Change Polygon',
					content: [
						{
							type: 'fields',
							fieldInfos: [
								{ fieldName: 'changePolygonId', label: 'ID' },
								{ fieldName: 'areaSqMeters', label: 'Area (m²)', format: { digitSeparator: true, places: 0 } },
								{ fieldName: 'ndviDropMean', label: 'NDVI Drop (Mean)', format: { places: 3 } },
								{ fieldName: 'ndviDropMax', label: 'NDVI Drop (Max)', format: { places: 3 } },
								{ fieldName: 'changeTypeName', label: 'Change Type' },
								{ fieldName: 'detectedAt', label: 'Detected At' }
							]
						}
					]
				}
			});

			// Add layer above imagery but below assets
			map.add(changePolygonLayer, 1);
			console.log(`Loaded ${geojson.features.length} change polygons for run ${runId}`);
		} catch (error) {
			console.error('Failed to load change polygons:', error);
			changePolygonsGeoJson.set(null);
		}
	}

	function createChangePolygonRenderer(): any {
		// Class breaks renderer based on ndviDropMean
		// More negative = more severe vegetation loss
		return {
			type: 'class-breaks',
			field: 'ndviDropMean',
			classBreakInfos: [
				{
					minValue: -1,
					maxValue: -0.4,
					symbol: {
						type: 'simple-fill',
						color: [220, 38, 38, 180], // red - severe
						outline: { color: [185, 28, 28, 255], width: 1 }
					},
					label: 'Severe (< -0.4)'
				},
				{
					minValue: -0.4,
					maxValue: -0.3,
					symbol: {
						type: 'simple-fill',
						color: [249, 115, 22, 160], // orange - strong
						outline: { color: [234, 88, 12, 255], width: 1 }
					},
					label: 'Strong (-0.4 to -0.3)'
				},
				{
					minValue: -0.3,
					maxValue: -0.2,
					symbol: {
						type: 'simple-fill',
						color: [250, 204, 21, 140], // yellow - moderate
						outline: { color: [202, 138, 4, 255], width: 1 }
					},
					label: 'Moderate (-0.3 to -0.2)'
				},
				{
					minValue: -0.2,
					maxValue: 0,
					symbol: {
						type: 'simple-fill',
						color: [254, 240, 138, 120], // light yellow - mild
						outline: { color: [202, 138, 4, 200], width: 1 }
					},
					label: 'Mild (> -0.2)'
				}
			]
		};
	}

	// Exported function to zoom to a risk event's change geometry
	export async function zoomToRiskEvent(eventId: string): Promise<void> {
		if (!mapView || !mapReady) return;

		try {
			// Fetch full event details including geometry
			const event = await api.getRiskEvent(eventId);

			if (!event.changeGeometry) {
				console.warn('Risk event has no change geometry');
				return;
			}

			const { default: Polygon } = await import('@arcgis/core/geometry/Polygon');
			const { default: Point } = await import('@arcgis/core/geometry/Point');

			let target: __esri.Geometry;

			if (event.changeGeometry.type === 'Polygon') {
				target = new Polygon({
					rings: event.changeGeometry.coordinates as number[][][],
					spatialReference: { wkid: 4326 }
				});
			} else if (event.changeGeometry.type === 'MultiPolygon') {
				// For MultiPolygon, flatten to rings
				const rings = (event.changeGeometry.coordinates as number[][][][]).flat();
				target = new Polygon({
					rings: rings,
					spatialReference: { wkid: 4326 }
				});
			} else if (event.changeGeometry.type === 'Point') {
				const coords = event.changeGeometry.coordinates as number[];
				target = new Point({
					x: coords[0],
					y: coords[1],
					spatialReference: { wkid: 4326 }
				});
			} else {
				console.warn('Unsupported geometry type:', event.changeGeometry.type);
				return;
			}

			// Zoom to the geometry with some padding
			await mapView.goTo({
				target: target,
				zoom: target.type === 'point' ? 16 : undefined
			}, {
				duration: 500
			});

			// Expand extent slightly if it's a polygon
			if (target.type === 'polygon' && target.extent) {
				await mapView.goTo(target.extent.expand(1.5), { duration: 300 });
			}
		} catch (error) {
			console.error('Failed to zoom to risk event:', error);
		}
	}
</script>

<div bind:this={mapContainer} class="map-container"></div>

<style>
	.map-container {
		width: 100%;
		height: 100%;
		background: #1a1a2e;
	}
</style>
