<template>
  <div class="layout">
    <Sidebar />
    <main class="main">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import Sidebar from "./components/Sidebar.vue"
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #0f172a;
  color: #e2e8f0;
  min-height: 100vh;
}
.layout {
  display: flex;
  min-height: 100vh;
}
.main {
  flex: 1;
  padding: 2rem;
  overflow-x: auto;
}
.page-title {
  font-size: 1.5rem;
  margin-bottom: 1.5rem;
  color: #f1f5f9;
}
.cards {
  display: grid;
  gap: 1rem;
  margin-bottom: 1.5rem;
}
.cards-2 {
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
}
.card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 1.25rem;
}
.card h3 {
  font-size: 0.9rem;
  color: #94a3b8;
  margin-bottom: 0.5rem;
}
.card .value {
  font-size: 1.8rem;
  font-weight: 600;
  color: #38bdf8;
}
.card .sub {
  font-size: 0.8rem;
  color: #64748b;
  margin-top: 0.25rem;
}
.table-wrap {
  overflow-x: auto;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}
th, td {
  text-align: left;
  padding: 0.6rem 0.75rem;
  border-bottom: 1px solid #334155;
}
th {
  color: #94a3b8;
  font-weight: 500;
  white-space: nowrap;
}
tr:hover {
  background: #1e293b;
}
.tag {
  display: inline-block;
  padding: 0.15rem 0.6rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
}
.tag-initial {
  background: #1e3a5f;
  color: #60a5fa;
}
.tag-correction {
  background: #1e3a2f;
  color: #4ade80;
}
.tag-maneuver {
  background: #3a1e1e;
  color: #f87171;
}
.total-badge {
  font-size: 0.85rem;
  color: #94a3b8;
  font-weight: 400;
}

/* Filter bar */
.filter-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
  padding: 0.75rem 1rem;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 8px;
}
.filter-label {
  font-size: 0.85rem;
  color: #94a3b8;
  white-space: nowrap;
}
.filter-all {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.85rem;
  color: #e2e8f0;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
}
.filter-all:hover {
  background: #334155;
}
.filter-chip {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 0.8rem;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  background: #0f172a;
  border: 1px solid #334155;
  transition: all 0.15s;
  color: #94a3b8;
}
.filter-chip:hover {
  border-color: #0ea5e9;
  color: #e2e8f0;
}
.filter-chip.active {
  border-color: #0ea5e9;
  color: #38bdf8;
}
.filter-chip input {
  display: none;
}

/* Record rows */
.record-row {
  cursor: pointer;
}
.record-row:hover td {
  background: rgba(148, 163, 184, 0.05);
}
.arrow {
  font-size: 0.7rem;
  color: #64748b;
}
.detail-row td {
  padding: 0 !important;
}
.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 1fr;
  gap: 0.75rem;
  padding: 0.75rem 1rem 0.75rem 3rem;
  background: #1e293b;
  border-bottom: 1px solid #334155;
}
</style>
