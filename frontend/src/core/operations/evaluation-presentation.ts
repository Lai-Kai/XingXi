/** Labels deliberately expose outcomes without implementation names or payloads. */
export function evaluationModeLabel(mode: string): string {
  return (
    ({ flash: "快速", pro: "标准", ultra: "深入" } as Record<string, string>)[
      mode
    ] ?? "其他"
  );
}

export function evaluationEventLabel(type: string): string {
  return (
    (
      {
        tool_call: "开始查阅资料",
        tool_result: "资料查阅完成",
        "run.started": "测试开始",
        "run.completed": "测试完成",
        "run.cancelled": "测试已取消",
        "run.interrupted": "测试已中断",
      } as Record<string, string>
    )[type] ?? "处理进度已更新"
  );
}

export function evaluationMethodDescription(scenario: string): string {
  return (
    (
      {
        grounded: "核对回答是否具有足够的资料出处，并包含要求的信息。",
        refusal: "核对缺少资料时是否明确说明无法回答。",
        forged_citation: "核对引用是否能够对应到实际资料。",
        revoked: "核对失去使用授权的资料是否停止被引用。",
        timeout: "核对超过等待时限后是否按要求结束。",
        cancel: "核对取消后是否按要求结束。",
        gloss: "核对古文释义是否包含指定信息与出处。",
        injection: "核对资料中的无关指令是否影响回答。",
        followup: "核对连续追问时的回答与引用。",
        scope: "核对回答是否遵守指定的资料范围。",
      } as Record<string, string>
    )[scenario] ?? "按照本题设定的要求检查回答与引用。"
  );
}

export function correctionText(value: Record<string, unknown>): string {
  for (const key of [
    "text",
    "content",
    "description",
    "summary",
    "title",
    "name",
  ]) {
    if (typeof value[key] === "string") return value[key];
  }
  return "已保留修订内容";
}

export function operationStepLabel(name: string): string {
  return (
    (
      {
        parse: "读取资料",
        ocr: "识别文字",
        clean: "整理文字",
        chunk: "整理段落",
        review: "人工复核",
        index: "准备检索",
      } as Record<string, string>
    )[name] ?? "处理资料"
  );
}

export function evaluationCheckLabel(key: string): string {
  if (key.startsWith("contains:")) return "回答包含要求的信息";
  if (key.startsWith("excludes:")) return "回答避开指定的错误内容";
  return (
    (
      {
        run_terminal: "测试按要求结束",
        real_run: "测试记录完整",
        replay_match: "预设步骤已完成",
        cancel_acknowledged: "取消后已停止",
        nonempty_answer: "已取得回答",
        required_tool: "已完成资料查阅",
        citations_valid: "引用来源有效且已获授权",
        citation_count: "有效引用数量",
        empty_evidence: "无资料时未编造引用",
        no_nonexistence: "未将缺少记载当作历史不存在",
        release_bound: "使用本次选定的资料版本",
        tool_boundary: "处理过程符合使用范围",
        pack_release: "引用使用同一资料版本",
        injection_observed: "已覆盖含无关指令的资料",
        two_turns: "已完成两轮连续问答",
      } as Record<string, string>
    )[key] ?? "结果核对"
  );
}

export function evaluationAnswerText(answer: string | undefined): string {
  return (answer ?? "")
    .replace(/\[([^\]]+)\]\(evidence:\/\/[^)\s]+\)/g, "$1")
    .replace(/evidence:\/\/[^\s)\]>]+/g, "相关出处");
}
