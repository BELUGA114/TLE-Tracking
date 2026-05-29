<template>
  <aside class="sidebar">
    <h1>TLE-Tracking</h1>
    <nav>
      <router-link to="/" :class="{ active: $route.name === 'dashboard' }">仪表盘</router-link>
      <router-link to="/history" :class="{ active: $route.name === 'history' }">TLE 变化</router-link>
      <router-link to="/decay" :class="{ active: $route.name === 'decay' }">衰降状态</router-link>
    </nav>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 220px;
  background: #1e293b;
  padding: 1.5rem;
  border-right: 1px solid #334155;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
}
.sidebar h1 {
  font-size: 1.1rem;
  margin-bottom: 2rem;
  color: #38bdf8;
  text-align: center;
}
.sidebar nav {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.sidebar a {
  color: #94a3b8;
  text-decoration: none;
  padding: 0.5rem 0.75rem;
  border-radius: 6px;
  transition: all 0.15s;
}
.sidebar a:hover {
  background: #334155;
  color: #e2e8f0;
}
.sidebar a.active {
  background: #0ea5e9;
  color: #fff;
}
</style>
