/**
 * 数值显示格式化工具。
 *
 * 后端已在 merge_raw_elements 中把 OMM 数值字段规范成 number，
 * 此处再做一道防御：任一字段类型异常（如残留字符串）也只让该字段
 * 显示占位符，不会因 string 没有 .toFixed 而让整个组件渲染崩溃。
 */

/** 将可能为 number / string / null 的值安全转为 number，失败返回 null。 */
export function toNum(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null
  if (typeof value === "string") {
    const n = Number(value)
    return value.trim() !== "" && Number.isFinite(n) ? n : null
  }
  return null
}

/** 定点格式化，非数值返回占位符。 */
export function fixed(value: unknown, digits: number, placeholder = "-"): string {
  const n = toNum(value)
  return n === null ? placeholder : n.toFixed(digits)
}

/** 科学计数格式化，非数值返回占位符。 */
export function expo(value: unknown, digits: number, placeholder = "-"): string {
  const n = toNum(value)
  return n === null ? placeholder : n.toExponential(digits)
}
