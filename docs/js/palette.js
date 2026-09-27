// 分类色板 —— 经 CVD/对比度/亮度带校验（dataviz validate_palette，dark #0b0e14 / light #f4f5f8 双模式通过）。
// 固定顺序分配，绝不按序循环重排；浅色模式对比度 WARN 的救济条款 = 色块旁始终有文字标签（本站满足）。
export const CATEGORY_ORDER = ["模型发布", "产品发布", "开源项目", "行业动态", "论文研究", "技巧与观点"];

export const CATEGORY_COLORS = {
  "模型发布": "#c97d18",
  "产品发布": "#189fb5",
  "开源项目": "#33a365",
  "行业动态": "#9a6ade",
  "论文研究": "#d15a85",
  "技巧与观点": "#5c85dd",
};

export const FALLBACK_COLOR = "#4a5468";

// 加深变体：用作小号文字色（数据色本身对比度不足 4.5:1，只作色点/图形）
export const CATEGORY_TEXT_COLORS = {
  "模型发布": "#8f5a12",
  "产品发布": "#10677c",
  "开源项目": "#227247",
  "行业动态": "#6f44ab",
  "论文研究": "#a13a60",
  "技巧与观点": "#3d5fae",
};

// 暗色提亮变体：上面那组"加深变体"是给浅色纸面用的，放到深底上只剩一团糊。
// 这组对 #0d1512 的对比度在 7.3~8.9:1，全部过 AA。
export const CATEGORY_TEXT_COLORS_DARK = {
  "模型发布": "#e0a24a",
  "产品发布": "#4fc2d8",
  "开源项目": "#5ec489",
  "行业动态": "#b794ea",
  "论文研究": "#e884a8",
  "技巧与观点": "#8aa9ea",
};

export const FALLBACK_COLOR_DARK = "#9aa6bd";

export function categoryColor(cat) {
  return CATEGORY_COLORS[cat] || FALLBACK_COLOR;
}

export function categoryTextColor(cat) {
  return CATEGORY_TEXT_COLORS[cat] || FALLBACK_COLOR;
}

export function categoryTextColorDark(cat) {
  return CATEGORY_TEXT_COLORS_DARK[cat] || FALLBACK_COLOR_DARK;
}

/* 给元素挂上两套分类文字色，交给 CSS 按主题挑一个。
   不直接写 style.color：那是内联样式，优先级最高，暗色规则盖不住它。 */
export function applyCategoryTextColor(el, cat) {
  el.classList.add("has-cat-text");
  el.style.setProperty("--cat-text", categoryTextColor(cat));
  el.style.setProperty("--cat-text-dark", categoryTextColorDark(cat));
}
