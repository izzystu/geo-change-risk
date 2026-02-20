import adapterAuto from '@sveltejs/adapter-auto';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

let adapter;
if (process.env.ADAPTER === 'static') {
	const adapterStatic = (await import('@sveltejs/adapter-static')).default;
	adapter = adapterStatic({ fallback: 'index.html' });
} else {
	adapter = adapterAuto();
}

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter
	}
};

export default config;
