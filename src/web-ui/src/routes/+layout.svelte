<script>
	import '../app.css';
	import '@arcgis/core/assets/esri/themes/light/main.css';
	import LoginGate from '$lib/components/LoginGate.svelte';
</script>

<LoginGate>
	<slot />
</LoginGate>
