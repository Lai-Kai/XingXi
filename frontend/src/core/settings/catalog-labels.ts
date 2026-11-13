import type { Locale } from "@/core/i18n/locale";
import type { Skill } from "@/core/skills/type";

type CatalogLabel = { name: string; description: string };

const SKILL_LABELS: Record<string, CatalogLabel> = {
  "academic-paper-review": {
    name: "学术论文研读",
    description: "梳理论文的研究问题、方法、结论与局限。",
  },
  bootstrap: {
    name: "使用引导",
    description: "了解使用偏好，完成初次使用引导。",
  },
  "chart-visualization": {
    name: "图表可视化",
    description: "根据数据选择合适的图表并生成可视化结果。",
  },
  "code-documentation": {
    name: "说明文档整理",
    description: "编写或完善项目说明、使用指南与相关文档。",
  },
  "consulting-analysis": {
    name: "专题分析报告",
    description: "制定研究框架，结合已收集资料撰写专题分析报告。",
  },
  "data-analysis": {
    name: "数据分析",
    description: "分析表格数据，生成统计、汇总与图表。",
  },
  "deep-research": {
    name: "深度资料研究",
    description: "开展多轮资料查找、交叉核对与研究整理。",
  },
  "find-skills": {
    name: "查找研究能力",
    description: "根据任务需要查找可添加的研究能力。",
  },
  "frontend-design": {
    name: "界面设计",
    description: "设计和制作网页、交互组件与展示界面。",
  },
  "github-deep-research": {
    name: "项目资料研究",
    description: "查找和整理项目资料、历史记录与相关信息。",
  },
  "image-generation": {
    name: "图像生成",
    description: "根据文字描述或参考图制作图像。",
  },
  "music-generation": {
    name: "音乐生成",
    description: "根据需求生成音乐与配乐素材。",
  },
  "newsletter-generation": {
    name: "简报编写",
    description: "汇集多份资料，编写专题简报与内容摘要。",
  },
  "podcast-generation": {
    name: "播客制作",
    description: "把文字内容整理为双人对话式播客音频。",
  },
  "ppt-generation": {
    name: "演示文稿制作",
    description: "制作图文结合的演示文稿与讲解材料。",
  },
  "skill-creator": {
    name: "研究流程设计",
    description: "创建、修改和检查自定义研究流程。",
  },
  "skill-reviewer": {
    name: "研究流程检查",
    description: "检查研究流程的适用条件、资料、使用范围与核验依据。",
  },
  "surprise-me": {
    name: "创意探索",
    description: "组合已有能力，探索新的内容表达方式。",
  },
  "systematic-literature-review": {
    name: "系统文献综述",
    description: "围绕研究主题整理多篇论文、比较结论并汇总参考文献。",
  },
  "vercel-deploy": {
    name: "网站发布",
    description: "将网站发布为可访问的预览或正式页面。",
  },
  "video-generation": {
    name: "视频生成",
    description: "根据文字描述或参考素材制作视频。",
  },
  "web-design-guidelines": {
    name: "网页设计检查",
    description: "检查网页的交互、可访问性与设计规范。",
  },
};

const TOOL_LABELS: Record<string, CatalogLabel> = {
  github: {
    name: "项目资料查找",
    description: "查询和整理项目资料、问题与变更记录。",
  },
  postgres: {
    name: "结构化资料查询",
    description: "查询管理员授权的数据资料。",
  },
  filesystem: {
    name: "文件管理辅助功能",
    description: "访问管理员配置的文件与目录。",
  },
  fetch: {
    name: "网页读取辅助功能",
    description: "读取网页内容，辅助资料查找与整理。",
  },
  tavily: {
    name: "网络检索辅助功能",
    description: "通过已配置的检索服务查找网络资料。",
  },
  context7: {
    name: "参考资料查询",
    description: "查询相关参考文档和使用资料。",
  },
};

export function isProductSkill(skill: Pick<Skill, "name" | "category">) {
  return !(skill.category === "public" && skill.name === "claude-to-deerflow");
}

const ENGLISH_SKILL_NAMES: Record<string, string> = {
  "academic-paper-review": "Academic reading",
  bootstrap: "Getting started",
  "chart-visualization": "Charts and diagrams",
  "code-documentation": "Documentation writing",
  "consulting-analysis": "Research reports",
  "data-analysis": "Data analysis",
  "deep-research": "In-depth research",
  "find-skills": "Find research capabilities",
  "frontend-design": "Page design",
  "github-deep-research": "Project research",
  "image-generation": "Image creation",
  "music-generation": "Music creation",
  "newsletter-generation": "Newsletter writing",
  "podcast-generation": "Podcast creation",
  "ppt-generation": "Presentation creation",
  "skill-creator": "Workflow creation",
  "skill-reviewer": "Workflow review",
  "surprise-me": "Creative exploration",
  "systematic-literature-review": "Literature review",
  "vercel-deploy": "Website publishing",
  "video-generation": "Video creation",
  "web-design-guidelines": "Page review",
};

export function getSkillLabel(
  skill: Pick<Skill, "name" | "description" | "category">,
  locale: Locale,
  position?: number,
): CatalogLabel {
  // Custom titles and descriptions are authored by users; shipped package identities
  // and descriptions are implementation details and never serve as UI fallbacks.
  if (skill.category === "custom") return skill;
  if (locale === "zh-CN")
    return (
      SKILL_LABELS[skill.name] ?? {
        name: `扩展研究能力${position === undefined ? "" : ` ${position + 1}`}`,
        description: "辅助研究与内容整理，可按任务需要启用。",
      }
    );
  return {
    name:
      ENGLISH_SKILL_NAMES[skill.name] ??
      `Additional research capability${position === undefined ? "" : ` ${position + 1}`}`,
    description: "An optional capability for research and content preparation.",
  };
}

export function getToolLabel(
  name: string,
  _description: string,
  locale: Locale,
  position?: number,
): CatalogLabel {
  if (locale === "zh-CN")
    return (
      TOOL_LABELS[name] ?? {
        name: `扩展辅助功能${position === undefined ? "" : ` ${position + 1}`}`,
        description: "由管理员提供的辅助功能，可按研究需要启用。",
      }
    );
  const names: Record<string, string> = {
    github: "Project information",
    postgres: "Structured source lookup",
    filesystem: "File management",
    fetch: "Webpage reading",
    tavily: "Web search",
    context7: "Reference lookup",
  };
  return {
    name:
      names[name] ??
      `Additional feature${position === undefined ? "" : ` ${position + 1}`}`,
    description: "An optional feature provided by your administrator.",
  };
}

export function getMemoryCategoryLabel(
  category: string,
  locale: Locale,
): string {
  const labels: Record<string, string> = {
    context: "背景信息",
    preference: "偏好",
    fact: "事实",
    behavior: "行为",
    goal: "目标",
    skill: "能力",
    knowledge: "知识",
  };
  return locale === "zh-CN" ? (labels[category] ?? category) : category;
}
