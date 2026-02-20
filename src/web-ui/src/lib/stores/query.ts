import { writable } from 'svelte/store';
import type { NaturalLanguageQueryResponse, QueryPlan } from '$lib/services/api';

// Current query text input
export const queryText = writable('');

// Most recent query response
export const queryResponse = writable<NaturalLanguageQueryResponse | null>(null);

// Loading state
export const queryLoading = writable(false);

// LLM service availability
export const llmAvailable = writable<boolean | null>(null);

// Error message
export const queryError = writable<string | null>(null);

// Query history (most recent first)
export const queryHistory = writable<string[]>([]);

// Risk event IDs from a query result, used to filter the RiskEventsPanel
export const queryResultEventIds = writable<Set<string> | null>(null);
