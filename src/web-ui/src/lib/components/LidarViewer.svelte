<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		selectedLidarSource,
		showLidarViewer,
		viewingPolygonId,
	} from '$lib/stores/lidar';

	let container: HTMLDivElement;
	let renderer: any;
	let scene: any;
	let camera: any;
	let controls: any;
	let terrainMesh: any;
	let animationId: number;
	let initialized = false;
	let loading = false;
	let loadError = '';
	let pointCount = 0;

	// Load new source when selection changes
	$: sourceUrl = $selectedLidarSource?.dtmUrl || $selectedLidarSource?.dsmUrl;
	$: if (initialized && sourceUrl && $showLidarViewer) {
		loadTerrain(sourceUrl);
	}

	onMount(() => {
		let observer: ResizeObserver | null = null;

		(async () => {
		const THREE = await import('three');
		const { OrbitControls } = await import('three/examples/jsm/controls/OrbitControls.js');

		scene = new THREE.Scene();
		scene.background = new THREE.Color(0x1a1a2e);

		camera = new THREE.PerspectiveCamera(60, container.clientWidth / container.clientHeight, 1, 50000);
		camera.position.set(0, 500, 800);

		renderer = new THREE.WebGLRenderer({ antialias: true });
		renderer.setSize(container.clientWidth, container.clientHeight);
		renderer.setPixelRatio(window.devicePixelRatio);
		container.appendChild(renderer.domElement);

		controls = new OrbitControls(camera, renderer.domElement);
		controls.enableDamping = true;
		controls.dampingFactor = 0.1;
		controls.screenSpacePanning = true;
		controls.maxPolarAngle = Math.PI * 0.85;

		// Lighting for terrain mesh
		const ambient = new THREE.AmbientLight(0xffffff, 0.4);
		scene.add(ambient);
		const directional = new THREE.DirectionalLight(0xffffff, 0.8);
		directional.position.set(1, 2, 1);
		scene.add(directional);

		initialized = true;

		function animate() {
			animationId = requestAnimationFrame(animate);
			controls.update();
			renderer.render(scene, camera);
		}
		animate();

		observer = new ResizeObserver(() => {
			if (!container) return;
			const w = container.clientWidth;
			const h = container.clientHeight;
			camera.aspect = w / h;
			camera.updateProjectionMatrix();
			renderer.setSize(w, h);
		});
		observer.observe(container);

		if (sourceUrl) {
			loadTerrain(sourceUrl);
		}
		})();

		return () => observer?.disconnect();
	});

	onDestroy(() => {
		if (animationId) cancelAnimationFrame(animationId);
		if (renderer) {
			renderer.dispose();
			renderer.domElement?.remove();
		}
		disposeTerrain();
	});

	function disposeTerrain() {
		if (terrainMesh) {
			scene?.remove(terrainMesh);
			terrainMesh.geometry?.dispose();
			terrainMesh.material?.dispose();
			terrainMesh = null;
		}
	}

	async function loadTerrain(url: string) {
		if (!initialized || loading) return;
		loading = true;
		loadError = '';
		pointCount = 0;

		const THREE = await import('three');
		disposeTerrain();

		try {
			// Fetch the GeoTIFF and parse it
			const { fromUrl } = await import('geotiff');
			const tiff = await fromUrl(url);
			const image = await tiff.getImage();
			const rasters = await image.readRasters();
			const data = rasters[0] as Float32Array | Float64Array;

			const width = image.getWidth();
			const height = image.getHeight();
			const nodata = -9999;

			// Find elevation range (excluding nodata)
			let minZ = Infinity, maxZ = -Infinity;
			for (let i = 0; i < data.length; i++) {
				if (data[i] !== nodata && isFinite(data[i])) {
					if (data[i] < minZ) minZ = data[i];
					if (data[i] > maxZ) maxZ = data[i];
				}
			}
			const zRange = maxZ - minZ || 1;

			// Subsample large rasters — target ~500k vertices max for smooth rendering
			const maxDim = 700;
			const stepX = Math.max(1, Math.floor(width / maxDim));
			const stepY = Math.max(1, Math.floor(height / maxDim));
			const sampledW = Math.floor(width / stepX);
			const sampledH = Math.floor(height / stepY);

			// Build geometry as a grid of quads
			const geometry = new THREE.BufferGeometry();
			const positions: number[] = [];
			const colors: number[] = [];
			const indices: number[] = [];

			// Scale factor: map pixels to world units
			const scaleXY = 1.0; // 1 pixel = 1 meter at 1m resolution
			const verticalExaggeration = 1.5;
			const centerX = (sampledW * scaleXY) / 2;
			const centerZ = (sampledH * scaleXY) / 2;

			// Create vertices
			for (let row = 0; row < sampledH; row++) {
				for (let col = 0; col < sampledW; col++) {
					const srcRow = row * stepY;
					const srcCol = col * stepX;
					const idx = srcRow * width + srcCol;
					const elev = data[idx];

					const x = col * scaleXY - centerX;
					const z = row * scaleXY - centerZ;
					const y = (elev !== nodata && isFinite(elev))
						? (elev - minZ) * verticalExaggeration
						: 0;

					positions.push(x, y, -z);

					// Color by elevation
					const t = (elev !== nodata && isFinite(elev))
						? (elev - minZ) / zRange
						: 0;
					let r = 0.3, g = 0.3, b = 0.3;

					if (elev !== nodata && isFinite(elev)) {
						if (t < 0.2) {
							r = 0.2; g = 0.45 + t * 2; b = 0.15;
						} else if (t < 0.4) {
							r = 0.3 + (t - 0.2) * 2; g = 0.6; b = 0.1;
						} else if (t < 0.6) {
							r = 0.6 + (t - 0.4); g = 0.6 - (t - 0.4); b = 0.1;
						} else if (t < 0.8) {
							r = 0.7; g = 0.4 - (t - 0.6); b = 0.2 + (t - 0.6);
						} else {
							r = 0.85; g = 0.85; b = 0.85;
						}
					}

					colors.push(r, g, b);
				}
			}

			// Create triangle indices
			for (let row = 0; row < sampledH - 1; row++) {
				for (let col = 0; col < sampledW - 1; col++) {
					const topLeft = row * sampledW + col;
					const topRight = topLeft + 1;
					const bottomLeft = (row + 1) * sampledW + col;
					const bottomRight = bottomLeft + 1;

					// Check that none of the vertices are nodata
					const tl = data[(row * stepY) * width + (col * stepX)];
					const tr = data[(row * stepY) * width + ((col + 1) * stepX)];
					const bl = data[((row + 1) * stepY) * width + (col * stepX)];
					const br = data[((row + 1) * stepY) * width + ((col + 1) * stepX)];

					if (tl !== nodata && tr !== nodata && bl !== nodata && br !== nodata &&
						isFinite(tl) && isFinite(tr) && isFinite(bl) && isFinite(br)) {
						indices.push(topLeft, bottomLeft, topRight);
						indices.push(topRight, bottomLeft, bottomRight);
					}
				}
			}

			geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
			geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
			geometry.setIndex(indices);
			geometry.computeVertexNormals();

			const material = new THREE.MeshLambertMaterial({
				vertexColors: true,
				side: THREE.DoubleSide,
			});

			terrainMesh = new THREE.Mesh(geometry, material);
			scene.add(terrainMesh);

			// Fit camera
			geometry.computeBoundingSphere();
			if (geometry.boundingSphere) {
				const sphere = geometry.boundingSphere;
				const dist = sphere.radius * 1.8;
				camera.position.set(
					sphere.center.x + dist * 0.3,
					sphere.center.y + dist * 0.6,
					sphere.center.z + dist * 0.5,
				);
				controls.target.copy(sphere.center);
				camera.far = dist * 10;
				camera.updateProjectionMatrix();
				controls.update();
			}

			pointCount = Math.floor(positions.length / 3);
		} catch (err) {
			console.error('Failed to load terrain:', err);
			loadError = err instanceof Error ? err.message : 'Failed to load terrain data';
		} finally {
			loading = false;
		}
	}
</script>

<div class="lidar-viewer" bind:this={container}>
	{#if !sourceUrl}
		<div class="viewer-placeholder">
			<p>Select a LIDAR source to view terrain in 3D</p>
			<p class="hint">DTM elevation data rendered as a 3D terrain mesh</p>
		</div>
	{:else if loading}
		<div class="viewer-placeholder">
			<p>Loading terrain data...</p>
			<div class="spinner"></div>
		</div>
	{:else if loadError}
		<div class="viewer-placeholder error">
			<p>Failed to load terrain</p>
			<p class="hint">{loadError}</p>
		</div>
	{:else if pointCount > 0}
		<div class="viewer-info">
			{pointCount.toLocaleString()} vertices
			{#if $viewingPolygonId}
				| Polygon: {$viewingPolygonId.slice(0, 8)}...
			{/if}
		</div>
	{/if}
</div>

<style>
	.lidar-viewer {
		width: 100%;
		height: 100%;
		position: relative;
		background: #1a1a2e;
		overflow: hidden;
	}

	.lidar-viewer :global(canvas) {
		display: block;
		width: 100% !important;
		height: 100% !important;
	}

	.viewer-placeholder {
		position: absolute;
		inset: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		color: #8888aa;
		font-size: 0.875rem;
		text-align: center;
		gap: 0.5rem;
	}

	.viewer-placeholder.error {
		color: #aa6666;
	}

	.viewer-placeholder .hint {
		font-size: 0.75rem;
		color: #666688;
	}

	.spinner {
		width: 24px;
		height: 24px;
		border: 2px solid #444466;
		border-top-color: #8888cc;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	.viewer-info {
		position: absolute;
		bottom: 0.5rem;
		right: 0.5rem;
		font-size: 0.625rem;
		color: #666688;
		background: rgba(26, 26, 46, 0.8);
		padding: 0.125rem 0.375rem;
		border-radius: 2px;
	}
</style>
