<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { api } from '$lib/services/api';

	let authenticated = false;
	let loading = true;
	let apiKey = '';
	let error = '';

	async function checkAuth() {
		try {
			await api.getHealth();
			authenticated = true;
		} catch (e: any) {
			if (e.message?.includes('Unauthorized')) {
				authenticated = false;
				if (typeof localStorage !== 'undefined') {
					localStorage.removeItem('georisk_api_key');
				}
			} else {
				// API might be down or no auth required
				authenticated = true;
			}
		}
		loading = false;
	}

	async function handleSubmit() {
		error = '';
		if (!apiKey.trim()) {
			error = 'Please enter an access key';
			return;
		}

		localStorage.setItem('georisk_api_key', apiKey.trim());

		try {
			await api.getHealth();
			authenticated = true;
		} catch {
			error = 'Invalid access key';
			localStorage.removeItem('georisk_api_key');
		}
	}

	function handleUnauthorized() {
		authenticated = false;
		localStorage.removeItem('georisk_api_key');
	}

	onMount(() => {
		checkAuth();
		window.addEventListener('georisk:unauthorized', handleUnauthorized);
	});

	onDestroy(() => {
		if (typeof window !== 'undefined') {
			window.removeEventListener('georisk:unauthorized', handleUnauthorized);
		}
	});
</script>

{#if loading}
	<div class="gate-container">
		<div class="gate-card">
			<p>Loading...</p>
		</div>
	</div>
{:else if authenticated}
	<slot />
{:else}
	<div class="gate-container">
		<div class="gate-card">
			<h1>Geo Change Risk</h1>
			<p class="subtitle">Geospatial Risk Intelligence Platform</p>

			<form on:submit|preventDefault={handleSubmit}>
				<label for="api-key">Demo Access Key</label>
				<input
					id="api-key"
					type="password"
					bind:value={apiKey}
					placeholder="Enter your access key"
					autocomplete="off"
				/>

				{#if error}
					<p class="error">{error}</p>
				{/if}

				<button type="submit">Sign In</button>
			</form>
		</div>
	</div>
{/if}

<style>
	.gate-container {
		display: flex;
		align-items: center;
		justify-content: center;
		min-height: 100vh;
		background: #0f172a;
		font-family: system-ui, -apple-system, sans-serif;
	}

	.gate-card {
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 12px;
		padding: 2.5rem;
		width: 100%;
		max-width: 400px;
		text-align: center;
		color: #e2e8f0;
	}

	h1 {
		margin: 0 0 0.25rem;
		font-size: 1.5rem;
		color: #f8fafc;
	}

	.subtitle {
		margin: 0 0 2rem;
		font-size: 0.875rem;
		color: #94a3b8;
	}

	form {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
		text-align: left;
	}

	label {
		font-size: 0.875rem;
		font-weight: 500;
		color: #94a3b8;
	}

	input {
		padding: 0.625rem 0.75rem;
		background: #0f172a;
		border: 1px solid #475569;
		border-radius: 6px;
		color: #f8fafc;
		font-size: 0.875rem;
	}

	input:focus {
		outline: none;
		border-color: #3b82f6;
		box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);
	}

	button {
		margin-top: 0.5rem;
		padding: 0.625rem;
		background: #3b82f6;
		color: white;
		border: none;
		border-radius: 6px;
		font-size: 0.875rem;
		font-weight: 500;
		cursor: pointer;
	}

	button:hover {
		background: #2563eb;
	}

	.error {
		color: #ef4444;
		font-size: 0.8125rem;
		margin: 0;
	}
</style>
