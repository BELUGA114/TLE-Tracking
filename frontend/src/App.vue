<template>
  <div class="layout">
    <Sidebar />
    <main class="main">
      <router-view v-slot="{ Component }">
        <Transition name="page-fade">
          <component :is="Component" />
        </Transition>
      </router-view>
    </main>
  </div>
</template>

<script setup lang="ts">
import Sidebar from "./components/Sidebar.vue"
</script>

<style scoped>
.layout {
  display: flex;
  min-height: 100vh;
}
.main {
  flex: 1;
  padding: var(--space-2xl);
  overflow-x: auto;
  animation: fadeIn var(--transition-normal);
}
</style>
