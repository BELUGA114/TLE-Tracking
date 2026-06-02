import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import { viteStaticCopy } from "vite-plugin-static-copy"

const CESIUM_SRC = "node_modules/cesium/Build/Cesium"

export default defineConfig({
  plugins: [
    vue(),
    viteStaticCopy({
      targets: [
        {
          src: `${CESIUM_SRC}/Workers/**`,
          dest: "cesium",
          rename: (_name, _ext, _fullPath) => ({ stripBase: 4 }),
        },
        {
          src: `${CESIUM_SRC}/Assets/**`,
          dest: "cesium",
          rename: (_name, _ext, _fullPath) => ({ stripBase: 4 }),
        },
        {
          src: `${CESIUM_SRC}/ThirdParty/**`,
          dest: "cesium",
          rename: (_name, _ext, _fullPath) => ({ stripBase: 4 }),
        },
        {
          src: `${CESIUM_SRC}/Widgets/**`,
          dest: "cesium",
          rename: (_name, _ext, _fullPath) => ({ stripBase: 4 }),
        },
      ],
    }),
  ],
  define: {
    CESIUM_BASE_URL: JSON.stringify("/cesium/"),
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
