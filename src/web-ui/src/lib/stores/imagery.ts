import { writable, derived } from 'svelte/store';
import type { ImagerySceneDetail } from '$lib/services/api';

// Scene details with presigned URLs
export const beforeSceneDetail = writable<ImagerySceneDetail | null>(null);
export const afterSceneDetail = writable<ImagerySceneDetail | null>(null);

// Layer visibility
export const showBeforeImagery = writable(false);
export const showAfterImagery = writable(false);

// Opacity controls (0-1)
export const imageryOpacity = writable(0.7);

// Loading states
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

// Reset imagery state when run changes
export function resetImageryState() {
    beforeSceneDetail.set(null);
    afterSceneDetail.set(null);
    showBeforeImagery.set(false);
    showAfterImagery.set(false);
    imageryError.set(null);
}
