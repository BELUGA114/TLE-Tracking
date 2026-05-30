import { createRouter, createWebHistory } from "vue-router"
import Dashboard from "../views/Dashboard.vue"

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "dashboard", component: Dashboard },
    { path: "/history", name: "history", component: () => import("../views/History.vue") },
    { path: "/decay", name: "decay", component: () => import("../views/DecayStatus.vue") },
    { path: "/satellite/:noradId", name: "satellite", component: () => import("../views/SatelliteDetail.vue") },
  ],
})

export default router
