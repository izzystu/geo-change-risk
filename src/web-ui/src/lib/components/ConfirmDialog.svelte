<script lang="ts">
    export let open = false;
    export let title = 'Confirm';
    export let message = 'Are you sure?';
    export let confirmLabel = 'Confirm';
    export let cancelLabel = 'Cancel';
    export let onConfirm: () => void;
    export let onCancel: () => void = () => { open = false; };
    export let destructive = false;
</script>

{#if open}
<div class="dialog-overlay" on:click={onCancel} role="presentation">
    <div class="dialog" on:click|stopPropagation role="dialog">
        <h3>{title}</h3>
        <div class="message">{@html message}</div>
        <div class="actions">
            <button class="cancel-btn" on:click={onCancel}>{cancelLabel}</button>
            <button class="confirm-btn" class:destructive on:click={onConfirm}>{confirmLabel}</button>
        </div>
    </div>
</div>
{/if}

<style>
    .dialog-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
    }
    .dialog {
        background: var(--color-surface, white);
        border-radius: 8px;
        padding: 1.5rem;
        max-width: 400px;
        width: 90%;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }
    h3 { margin: 0 0 1rem 0; font-size: 1.1rem; color: var(--color-text, #333); }
    .message { margin-bottom: 1.5rem; font-size: 0.875rem; color: var(--color-text-muted, #666); line-height: 1.5; }
    .actions { display: flex; gap: 0.5rem; justify-content: flex-end; }
    button { padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; font-size: 0.875rem; }
    .cancel-btn { background: transparent; border: 1px solid var(--color-border, #ccc); color: var(--color-text, #333); }
    .cancel-btn:hover { background: var(--color-bg, #f5f5f5); }
    .confirm-btn { background: var(--color-primary, #3b82f6); color: white; border: none; }
    .confirm-btn:hover { opacity: 0.9; }
    .confirm-btn.destructive { background: #ef4444; }
</style>
