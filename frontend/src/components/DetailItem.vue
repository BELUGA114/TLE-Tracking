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
.detail-item {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.detail-item.wide {
  grid-column: span 2;
}
.detail-label {
  font-size: 0.7rem;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.detail-value {
  font-size: 0.85rem;
  color: #e2e8f0;
  font-family: monospace;
  word-break: break-all;
}
</style>
