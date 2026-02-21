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
	let assetLayers: Map<number, __esri.GeoJSONLayer[]> = new Map();
	let beforeImageryLayer: __esri.MediaLayer | null = null;
	let afterImageryLayer: __esri.MediaLayer | null = null;
	let changePolygonLayer: __esri.GeoJSONLayer | null = null;
	let highlightLayer: __esri.GraphicsLayer | null = null;
	let queryResultsLayer: __esri.GeoJSONLayer | null = null;

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

		const { default: GraphicsLayer } = await import('@arcgis/core/layers/GraphicsLayer');
		highlightLayer = new GraphicsLayer({ title: 'Selection Highlight' });
		map.add(highlightLayer);

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
		assetLayers.forEach(layers => layers.forEach(layer => mapView?.map?.remove(layer)));
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

			// Create a layer for each asset type, splitting mixed geometry types
			for (const [assetType, features] of featuresByType) {
				const layerConfig = $layers.find(l => l.id === assetType);
				const color = layerConfig?.color ?? '#94a3b8';
				const visible = layerConfig?.visible ?? true;
				const baseName = layerConfig?.name ?? `Type ${assetType}`;

				// Sub-group by geometry category so each layer gets the right renderer
				const byGeomCategory = new Map<string, any[]>();
				for (const feature of features) {
					const gt = feature.geometry?.type ?? 'Polygon';
					const category = gt.includes('Point') ? 'Point'
						: gt.includes('Line') ? 'LineString'
						: 'Polygon';
					if (!byGeomCategory.has(category)) {
						byGeomCategory.set(category, []);
					}
					byGeomCategory.get(category)!.push(feature);
				}

				const sublayers: __esri.GeoJSONLayer[] = [];
				const hasMixed = byGeomCategory.size > 1;

				for (const [geomCategory, geomFeatures] of byGeomCategory) {
					const typeGeojson = {
						type: 'FeatureCollection',
						features: geomFeatures
					};

					const blob = new Blob([JSON.stringify(typeGeojson)], { type: 'application/json' });
					const url = URL.createObjectURL(blob);

					const layer = new GeoJSONLayer({
						url,
						title: hasMixed ? `${baseName} (${geomCategory}s)` : baseName,
						visible,
						outFields: ['*'],
						renderer: createRenderer(color, geomCategory),
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

					sublayers.push(layer);
					mapView!.map!.add(layer);
				}

				assetLayers.set(assetType, sublayers);
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

	function hexToRgba(hex: string, alpha: number): number[] {
		const r = parseInt(hex.slice(1, 3), 16);
		const g = parseInt(hex.slice(3, 5), 16);
		const b = parseInt(hex.slice(5, 7), 16);
		return [r, g, b, alpha * 255];
	}

	function updateLayerVisibility(layerConfigs: typeof $layers) {
		for (const config of layerConfigs) {
			const layers = assetLayers.get(config.id);
			if (layers) {
				layers.forEach(layer => layer.visible = config.visible);
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
			const source = existingLayer.source as __esri.LocalMediaElementSource;
			source.elements.removeAll();
			source.elements.add(imageElement);
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

	// Minimum zoom level when viewing risk events (prevents zooming too far out)
	const MIN_RISK_EVENT_ZOOM = 14;

	export function clearHighlights(): void {
		highlightLayer?.removeAll();
	}

	export async function showQueryResults(geoJson: GeoJSON.FeatureCollection | null): Promise<void> {
		if (!map || !mapView || !mapReady) return;

		// Remove existing query results layer
		if (queryResultsLayer) {
			map.remove(queryResultsLayer);
			queryResultsLayer = null;
		}

		if (!geoJson || !geoJson.features || geoJson.features.length === 0) return;

		const { default: GeoJSONLayer } = await import('@arcgis/core/layers/GeoJSONLayer');

		const blob = new Blob([JSON.stringify(geoJson)], { type: 'application/json' });
		const url = URL.createObjectURL(blob);

		queryResultsLayer = new GeoJSONLayer({
			url,
			title: 'Query Results',
			visible: true,
			outFields: ['*'],
			renderer: {
				type: 'simple',
				symbol: {
					type: 'simple-fill',
					color: [0, 188, 212, 140], // cyan/teal
					outline: { color: [0, 150, 170, 255], width: 2 }
				}
			} as any,
			popupTemplate: {
				title: 'Query Result',
				content: [
					{
						type: 'fields',
						fieldInfos: [
							{ fieldName: 'riskScore', label: 'Risk Score' },
							{ fieldName: 'riskLevelName', label: 'Risk Level' },
							{ fieldName: 'assetName', label: 'Asset' },
							{ fieldName: 'assetTypeName', label: 'Asset Type' },
							{ fieldName: 'changeTypeName', label: 'Change Type' },
							{ fieldName: 'areaSqMeters', label: 'Area (m2)' },
							{ fieldName: 'name', label: 'Name' },
							{ fieldName: 'criticalityName', label: 'Criticality' }
						]
					}
				]
			}
		});

		map.add(queryResultsLayer);

		// Zoom to the extent of results
		try {
			await queryResultsLayer.when();
			const extent = await queryResultsLayer.queryExtent();
			if (extent?.extent) {
				await mapView.goTo(extent.extent.expand(1.3), { duration: 500 });
			}
		} catch (err) {
			console.warn('Could not zoom to query results:', err);
		}
	}

	// Exported function to zoom to a risk event, keeping the asset visible
	export async function zoomToRiskEvent(eventId: string): Promise<void> {
		if (!mapView || !mapReady) return;

		try {
			const event = await api.getRiskEvent(eventId);

			if (!event.changeGeometry) {
				console.warn('Risk event has no change geometry');
				return;
			}

			const { default: Polygon } = await import('@arcgis/core/geometry/Polygon');
			const { default: Point } = await import('@arcgis/core/geometry/Point');

			// Build change geometry
			let changeTarget: __esri.Geometry;

			if (event.changeGeometry.type === 'Polygon') {
				changeTarget = new Polygon({
					rings: event.changeGeometry.coordinates as number[][][],
					spatialReference: { wkid: 4326 }
				});
			} else if (event.changeGeometry.type === 'MultiPolygon') {
				const rings = (event.changeGeometry.coordinates as number[][][][]).flat();
				changeTarget = new Polygon({
					rings: rings,
					spatialReference: { wkid: 4326 }
				});
			} else if (event.changeGeometry.type === 'Point') {
				const coords = event.changeGeometry.coordinates as number[];
				changeTarget = new Point({
					x: coords[0],
					y: coords[1],
					spatialReference: { wkid: 4326 }
				});
			} else {
				console.warn('Unsupported geometry type:', event.changeGeometry.type);
				return;
			}

			// Build asset geometry if available
			// Resolve an asset point closest to the change for zoom framing.
			// For LineStrings (roads, pipelines), use the nearest vertex to the
			// change centroid rather than the full geometry extent.
			let assetPoint: __esri.Point | null = null;
			const changeCentroid = changeTarget.type === 'point'
				? changeTarget as __esri.Point
				: (changeTarget as __esri.Polygon).centroid!;

			if (event.assetGeometry) {
				if (event.assetGeometry.type === 'Point') {
					const coords = event.assetGeometry.coordinates as number[];
					assetPoint = new Point({
						x: coords[0],
						y: coords[1],
						spatialReference: { wkid: 4326 }
					});
				} else if (event.assetGeometry.type === 'LineString' || event.assetGeometry.type === 'MultiLineString') {
					// Find the vertex nearest to the change centroid
					const allCoords = event.assetGeometry.type === 'MultiLineString'
						? (event.assetGeometry.coordinates as number[][][]).flat()
						: event.assetGeometry.coordinates as number[][];
					let bestDist = Infinity;
					let bestCoord = allCoords[0];
					for (const coord of allCoords) {
						const dx = coord[0] - changeCentroid.x;
						const dy = coord[1] - changeCentroid.y;
						const d = dx * dx + dy * dy;
						if (d < bestDist) {
							bestDist = d;
							bestCoord = coord;
						}
					}
					assetPoint = new Point({
						x: bestCoord[0],
						y: bestCoord[1],
						spatialReference: { wkid: 4326 }
					});
				} else if (event.assetGeometry.type === 'Polygon' || event.assetGeometry.type === 'MultiPolygon') {
					const assetPoly = new Polygon({
						rings: event.assetGeometry.type === 'MultiPolygon'
							? (event.assetGeometry.coordinates as number[][][][]).flat()
							: event.assetGeometry.coordinates as number[][][],
						spatialReference: { wkid: 4326 }
					});
					assetPoint = assetPoly.centroid ?? null;
				}
			}

			// Determine zoom target
			if (changeTarget.type === 'point') {
				await mapView.goTo({
					target: changeTarget,
					zoom: 16
				}, { duration: 500 });
			} else if (assetPoint) {
				// Build a tight extent around the change centroid and the asset point
				const { default: Extent } = await import('@arcgis/core/geometry/Extent');
				const combined = new Extent({
					xmin: Math.min(changeCentroid.x, assetPoint.x),
					ymin: Math.min(changeCentroid.y, assetPoint.y),
					xmax: Math.max(changeCentroid.x, assetPoint.x),
					ymax: Math.max(changeCentroid.y, assetPoint.y),
					spatialReference: { wkid: 4326 }
				});
				const padded = combined.expand(2.0);

				await mapView.goTo(padded, { duration: 500 });

				if (mapView.zoom < MIN_RISK_EVENT_ZOOM) {
					await mapView.goTo({
						target: assetPoint,
						zoom: MIN_RISK_EVENT_ZOOM
					}, { duration: 300 });
				}
			} else if (changeTarget.extent) {
				await mapView.goTo(changeTarget.extent.expand(1.3), { duration: 500 });

				if (mapView.zoom < MIN_RISK_EVENT_ZOOM) {
					await mapView.goTo({
						target: changeCentroid,
						zoom: MIN_RISK_EVENT_ZOOM
					}, { duration: 300 });
				}
			}

			// Draw selection highlights
			if (highlightLayer && map) {
				highlightLayer.removeAll();
				// Move highlight layer to top of stack so it draws above
				// change polygons and asset layers
				map.reorder(highlightLayer, map.layers.length - 1);

				const { default: Graphic } = await import('@arcgis/core/Graphic');

				// Highlight change polygon
				if (changeTarget.type === 'polygon') {
					highlightLayer.add(new Graphic({
						geometry: changeTarget,
						symbol: {
							type: 'simple-fill',
							style: 'diagonal-cross',
							color: [0, 255, 255, 180],
							outline: { color: [0, 255, 255], width: 3, style: 'solid' }
						} as any
					}));
				}

				// Highlight full asset geometry
				if (event.assetGeometry) {
					const { default: Polyline } = await import('@arcgis/core/geometry/Polyline');

					let assetHighlightGeom: __esri.Geometry | null = null;
					let assetHighlightSymbol: any = null;

					if (event.assetGeometry.type === 'Point') {
						assetHighlightGeom = new Point({
							x: (event.assetGeometry.coordinates as number[])[0],
							y: (event.assetGeometry.coordinates as number[])[1],
							spatialReference: { wkid: 4326 }
						});
						assetHighlightSymbol = {
							type: 'simple-marker',
							color: [255, 255, 0, 200],
							size: 14,
							outline: { color: [255, 255, 0], width: 2 }
						};
					} else if (event.assetGeometry.type === 'LineString' || event.assetGeometry.type === 'MultiLineString') {
						const paths = event.assetGeometry.type === 'MultiLineString'
							? event.assetGeometry.coordinates as number[][][]
							: [event.assetGeometry.coordinates as number[][]];
						assetHighlightGeom = new Polyline({
							paths,
							spatialReference: { wkid: 4326 }
						});
						assetHighlightSymbol = {
							type: 'simple-line',
							color: [255, 255, 0],
							width: 4
						};
					} else if (event.assetGeometry.type === 'Polygon' || event.assetGeometry.type === 'MultiPolygon') {
						const rings = event.assetGeometry.type === 'MultiPolygon'
							? (event.assetGeometry.coordinates as number[][][][]).flat()
							: event.assetGeometry.coordinates as number[][][];
						assetHighlightGeom = new Polygon({
							rings,
							spatialReference: { wkid: 4326 }
						});
						assetHighlightSymbol = {
							type: 'simple-fill',
							color: [255, 255, 0, 40],
							outline: { color: [255, 255, 0], width: 3, style: 'solid' }
						};
					}

					if (assetHighlightGeom && assetHighlightSymbol) {
						highlightLayer.add(new Graphic({
							geometry: assetHighlightGeom,
							symbol: assetHighlightSymbol
						}));
					}
				}
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
