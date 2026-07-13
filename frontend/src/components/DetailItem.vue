<template>
  <div class="detail-item" :class="{ wide }">
    <span class="detail-label">{{ label }}</span>
    <span class="detail-value">{{ value }}</span>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  value: string
  wide?: boolean
}>()
</script>

<style scoped>
.item {
  min-width: 0;
}
.wide {
  grid-column: span 2;
}
.label {
  font-family: var(--font-mono);
  font-size: 0.7rem;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-muted);
  margin-bottom: 0.15rem;
}
.value {
  font-family: var(--font-mono);
  font-size: 0.88rem;
  color: var(--color-text-primary);
  word-break: break-all;
}
</style>
