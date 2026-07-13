/**
 * CesiumBootstrapper — 封装 Cesium Viewer 初始化、token、imagery、错误诊断。
 * 所有副作用（DOM 操作、Cesium 全局状态）集中在此模块。
 */
import type * as Cesium from "cesium"

export interface BootResult {
  viewer: Cesium.Viewer
  Cesium: typeof Cesium
  /** 成功时为 undefined，用于判别式联合 */
  error?: undefined
}

interface BootError {
  viewer: null
  Cesium: null
  error: string
}

/** 类型守卫：区分 BootResult（成功）与 BootError（失败） */
export function isBootError(r: BootResult | BootError): r is BootError {
  return r.error !== undefined
}

/**
 * 诊断信息：在 Viewer 创建前后收集，出问题时打印到 console。
 */
interface Diagnostics {
  webglSupported: boolean
  canvasSize: { width: number; height: number } | null
  ionTokenSet: boolean
  imageryProviderType: string
}

function collectDiagnostics(container: HTMLElement, token: string): Diagnostics {
  const canvas = document.createElement("canvas")
  const gl =
    canvas.getContext("webgl2") ||
    canvas.getContext("webgl") ||
    (canvas.getContext("experimental-webgl") as WebGLRenderingContext | null)

  return {
    webglSupported: gl !== null,
    canvasSize: {
      width: container.clientWidth,
      height: container.clientHeight,
    },
    ionTokenSet: token.length > 0,
    imageryProviderType: token.length > 0 ? "Cesium Ion (Bing Maps)" : "OpenStreetMap (free)",
  }
}

export async function bootstrapCesium(container: HTMLElement): Promise<BootResult | BootError> {
  // 1. 读取 token
  const meta = import.meta as unknown as Record<string, unknown>
  const token: string =
    meta.env
      ? (meta.env as Record<string, string>).VITE_CESIUM_ION_TOKEN ?? ""
      : ""

  // 2. 诊断预检
  const diag = collectDiagnostics(container, token)
  console.log("[CesiumBootstrapper] 预检诊断:", JSON.stringify(diag, null, 2))

  if (!diag.webglSupported) {
    return {
      viewer: null,
      Cesium: null,
      error: "WebGL 不可用：浏览器或显卡不支持 WebGL，CesiumJS 无法渲染。请检查显卡驱动或尝试 Chrome/Edge。",
    }
  }

  if (diag.canvasSize && (diag.canvasSize.width === 0 || diag.canvasSize.height === 0)) {
    console.warn("[CesiumBootstrapper] 容器尺寸为零，Cesium canvas 可能不可见")
  }

  // 3. 动态加载 Cesium
  let CesiumModule: typeof Cesium
  try {
    CesiumModule = await import("cesium")
    await import("cesium/Build/Cesium/Widgets/widgets.css")
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return {
      viewer: null,
      Cesium: null,
      error: `CesiumJS 模块加载失败: ${msg}`,
    }
  }

  // 4. 设置 Ion token
  if (token) {
    CesiumModule.Ion.defaultAccessToken = token
  }

  // 5. 构建 imageryProvider Promise —— fromProviderAsync 要求 Promise<ImageryProvider>
  let imageryPromise: Promise<Cesium.ImageryProvider>
  if (token) {
    // 使用 Bing Maps Aerial with Labels（Ion asset ID 3）
    imageryPromise = CesiumModule.IonImageryProvider.fromAssetId(3)
  } else {
    // 回退：OpenStreetMap 免费瓦片，无需认证
    imageryPromise = Promise.resolve(
      new CesiumModule.OpenStreetMapImageryProvider({
        url: "https://tile.openstreetmap.org/",
        maximumLevel: 18,
      }),
    )
  }

  // 6. 创建 Viewer
  //    特性检测 morphTo3D（Cesium 1.141 中存在但未来版本可能移除）
  let viewer: Cesium.Viewer
  try {
    viewer = new CesiumModule.Viewer(container, {
      animation: false,
      timeline: false,
      geocoder: false,
      homeButton: true,
      sceneModePicker: false,
      baseLayerPicker: false,
      navigationHelpButton: false,
      infoBox: false,
      fullscreenButton: false,
      selectionIndicator: false,
      // 显式传入 imageryProvider，不依赖默认 Ion 行为
      baseLayer: CesiumModule.ImageryLayer.fromProviderAsync(imageryPromise),
      // 场景模式：直接指定 SCENE3D
      sceneMode: CesiumModule.SceneMode.SCENE3D,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return {
      viewer: null,
      Cesium: null,
      error: `Cesium Viewer 创建失败: ${msg}`,
    }
  }

  // 7. 场景配置
  viewer.scene.backgroundColor = CesiumModule.Color.fromCssColorString("#0b1526")
  viewer.scene.globe.baseColor = CesiumModule.Color.fromCssColorString("#1a2a40")

  // 安全设置 sceneMode（morphTo3D 存在则调用，否则忽略）
  viewer.scene.mode = CesiumModule.SceneMode.SCENE3D
  const sceneUnknown = viewer.scene as unknown as Record<string, unknown>
  if (typeof sceneUnknown.morphTo3D === "function") {
    ;(sceneUnknown.morphTo3D as (...args: unknown[]) => void)(0)
  }

  // 8. Camera 控制配置
  type CameraCtl = Cesium.ScreenSpaceCameraController & {
    invertZoom: boolean
    minimumZoomRate: number
    maximumZoomRate: number
  }
  const controller = viewer.scene.screenSpaceCameraController as CameraCtl
  controller.enableCollisionDetection = true
  controller.minimumZoomDistance = 500000
  controller.maximumZoomDistance = 100000000
  controller.invertZoom = true
  controller.minimumZoomRate = 5000
  controller.maximumZoomRate = 500000

  // 9. 渲染错误处理 —— 不吞错误
  viewer.scene.renderError.addEventListener((_scene: Cesium.Scene, err: Error) => {
    console.error("[Cesium] 渲染错误:", err.message, err.stack)
    // 不返回 true，让 Cesium 的默认错误弹窗显示
  })

  // 10. 初始视角
  viewer.camera.flyTo({
    destination: CesiumModule.Cartesian3.fromDegrees(116.4, 39.9, 25000000),
    duration: 0.5,
  })

  // 11. 注册 homeButton 飞到同样位置
  viewer.homeButton.viewModel.command.beforeExecute.addEventListener(() => {
    viewer.camera.flyTo({
      destination: CesiumModule.Cartesian3.fromDegrees(116.4, 39.9, 25000000),
      duration: 0.5,
    })
  })

  // 12. 最终诊断
  const finalCanvas = viewer.canvas as HTMLCanvasElement | null
  console.log("[CesiumBootstrapper] Viewer 创建完成:", {
    canvasSize: finalCanvas
      ? { width: finalCanvas.clientWidth, height: finalCanvas.clientHeight }
      : null,
    sceneMode: viewer.scene.mode,
    globeVisible: viewer.scene.globe?.show,
  })

  return { viewer, Cesium: CesiumModule }
}
