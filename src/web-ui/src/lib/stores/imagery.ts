import { writable, derived } from 'svelte/store';
import type { ImageryScene, ImagerySceneDetail } from '$lib/services/api';

// Available scenes for the current AOI
export const availableScenes = writable<ImageryScene[]>([]);

// Selected scenes for before/after comparison
export const selectedBeforeSceneId = writable<string | null>(null);
export const selectedAfterSceneId = writable<string | null>(null);

// Scene details with presigned URLs
export const beforeSceneDetail = writable<ImagerySceneDetail | null>(null);
export const afterSceneDetail = writable<ImagerySceneDetail | null>(null);

// Layer visibility
export const showBeforeImagery = writable(false);
export const showAfterImagery = writable(false);

// Opacity controls (0-1)
export const imageryOpacity = writable(0.7);

// Loading states
export const scenesLoading = writable(false);
export const sceneDetailLoading = writable(false);
export const imageryError = writable<string | null>(null);

// Derived: Current visible imagery URL (from before or after based on toggle)
// Uses displayUrl which prefers PNG (web-compatible) over TIF
export const activeImageryUrl = derived(
    [showBeforeImagery, showAfterImagery, beforeSceneDetail, afterSceneDetail],
    ([$showBefore, $showAfter, $before, $after]) => {
        if ($showAfter && $after) {
            return $after.displayUrl ?? null;
        }
        if ($showBefore && $before) {
            return $before.displayUrl ?? null;
        }
        return null;
    }
);

// Reset imagery state when AOI changes
export function resetImageryState() {
    availableScenes.set([]);
    selectedBeforeSceneId.set(null);
    selectedAfterSceneId.set(null);
    beforeSceneDetail.set(null);
    afterSceneDetail.set(null);
    showBeforeImagery.set(false);
    showAfterImagery.set(false);
    imageryError.set(null);
}
