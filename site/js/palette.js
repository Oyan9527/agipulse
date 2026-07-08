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

export function categoryColor(cat) {
  return CATEGORY_COLORS[cat] || FALLBACK_COLOR;
}
