import { writable, derived } from 'svelte/store';
import { AssetTypeLabels } from '$lib/services/api';

export interface LayerConfig {
	id: number;
	name: string;
	visible: boolean;
	color: string;
}

// Basemap options
export interface BasemapOption {
	id: string;
	name: string;
}

export const basemapOptions: BasemapOption[] = [
	{ id: 'satellite', name: 'Satellite' },
	{ id: 'hybrid', name: 'Hybrid' },
	{ id: 'topo-vector', name: 'Topographic' },
	{ id: 'streets-vector', name: 'Streets' },
	{ id: 'gray-vector', name: 'Light Gray' },
	{ id: 'dark-gray-vector', name: 'Dark Gray' },
	{ id: 'none', name: 'None' }
];

export const selectedBasemap = writable<string>('topo-vector');

// Default layer configurations (IDs match AssetType enum in C#)
const defaultLayers: LayerConfig[] = [
	{ id: 0, name: 'Transmission Lines', visible: true, color: '#f97316' },  // orange
	{ id: 1, name: 'Substations', visible: true, color: '#f59e0b' },         // amber
	{ id: 2, name: 'Gas Pipelines', visible: true, color: '#06b6d4' },       // cyan
	{ id: 3, name: 'Buildings', visible: true, color: '#6366f1' },           // indigo
	{ id: 4, name: 'Roads', visible: true, color: '#64748b' },               // gray
	{ id: 5, name: 'Fire Stations', visible: true, color: '#ef4444' },       // red
	{ id: 6, name: 'Hospitals', visible: true, color: '#ec4899' },           // pink
	{ id: 7, name: 'Schools', visible: true, color: '#8b5cf6' },             // purple
	{ id: 8, name: 'Water Infrastructure', visible: true, color: '#3b82f6' } // blue
];

export const layers = writable<LayerConfig[]>(defaultLayers);

// Derived store for visible asset types
export const visibleAssetTypes = derived(layers, ($layers) =>
	$layers.filter(l => l.visible).map(l => l.id)
);

// Toggle layer visibility
export function toggleLayer(id: number) {
	layers.update(current =>
		current.map(layer =>
			layer.id === id ? { ...layer, visible: !layer.visible } : layer
		)
	);
}

// Set all layers visible/hidden
export function setAllLayersVisible(visible: boolean) {
	layers.update(current =>
		current.map(layer => ({ ...layer, visible }))
	);
}
