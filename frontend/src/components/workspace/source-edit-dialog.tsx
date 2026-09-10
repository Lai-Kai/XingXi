"use client";

import { useEffect, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  updateSourceDocument,
  type SourceDocumentStatus,
  type SourceDocumentSummary,
  type SourceLevel,
  type SourceType,
} from "@/core/source-files/api";

export function SourceEditDialog({
  source,
  open,
  onOpenChange,
  onSaved,
}: {
  source: SourceDocumentSummary;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: (source: SourceDocumentSummary) => void;
}) {
  const [draft, setDraft] = useState(source);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setDraft(source), [source]);

  const fieldClass = "h-10 rounded-md border border-[#d2dddf] bg-white px-3 text-sm outline-none focus:border-[#6ea7af]";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>编辑资料信息</DialogTitle>
          <DialogDescription>修改来源元数据不会覆盖已上传的原始文件。</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="grid gap-2 text-sm sm:col-span-2"><span>资料名称</span><input value={draft.title} onChange={(event) => setDraft({ ...draft, title: event.target.value })} className={fieldClass} /></label>
          <label className="grid gap-2 text-sm"><span>版本 / 年代</span><input value={draft.edition} onChange={(event) => setDraft({ ...draft, edition: event.target.value })} className={fieldClass} /></label>
          <label className="grid gap-2 text-sm"><span>收藏机构</span><input value={draft.source_institution} onChange={(event) => setDraft({ ...draft, source_institution: event.target.value })} className={fieldClass} /></label>
          <label className="grid gap-2 text-sm"><span>资料类型</span><select value={draft.source_type} onChange={(event) => setDraft({ ...draft, source_type: event.target.value as SourceType, source_type_label: event.target.value === "other" ? draft.source_type_label : null })} className={fieldClass}><option value="gazetteer">地方志</option><option value="inscription">碑刻</option><option value="archive">档案</option><option value="heritage_record">文保记录</option><option value="scholarly_work">研究著作</option><option value="oral_history">口述史</option><option value="web">网络资料</option><option value="inference">推断资料</option><option value="other">其他资料</option></select></label>
          {draft.source_type === "other" && <label className="grid gap-2 text-sm"><span>自定义资料类型</span><input required maxLength={100} value={draft.source_type_label ?? ""} onChange={(event) => setDraft({ ...draft, source_type_label: event.target.value })} placeholder="例如：家谱、报刊、书信、照片集" className={fieldClass} /></label>}
          <label className="grid gap-2 text-sm"><span>来源等级</span><select value={draft.source_level} onChange={(event) => setDraft({ ...draft, source_level: event.target.value as SourceLevel })} className={fieldClass}>{["A", "B", "C", "D", "E", "U"].map((level) => <option key={level} value={level}>{level === "U" ? "U（待评定）" : level}</option>)}</select></label>
          <label className="grid gap-2 text-sm"><span>权利持有人</span><input value={draft.holder} onChange={(event) => setDraft({ ...draft, holder: event.target.value })} className={fieldClass} /></label>
          <label className="grid gap-2 text-sm"><span>资料状态</span><select value={draft.status} onChange={(event) => setDraft({ ...draft, status: event.target.value as SourceDocumentStatus })} className={fieldClass}><option value="registered">已登记</option><option value="archived">已归档</option></select></label>
        </div>
        {error && <p className="text-sm text-red-700">{error}</p>}
        <DialogFooter>
          <button type="button" onClick={() => onOpenChange(false)} className="h-9 rounded-md border px-4 text-sm">取消</button>
          <button type="button" disabled={saving || !draft.title.trim() || !draft.edition.trim() || (draft.source_type === "other" && !draft.source_type_label?.trim())} onClick={async () => { setSaving(true); setError(null); try { const updated = await updateSourceDocument(source.id, { title: draft.title.trim(), edition: draft.edition.trim(), source_institution: draft.source_institution.trim(), source_type: draft.source_type, source_type_label: draft.source_type === "other" ? draft.source_type_label?.trim() : null, source_level: draft.source_level, holder: draft.holder.trim(), status: draft.status }); onSaved(updated); onOpenChange(false); } catch (saveError) { setError(saveError instanceof Error ? saveError.message : "无法保存资料信息"); } finally { setSaving(false); } }} className="h-9 rounded-md bg-[#276f79] px-4 text-sm text-white disabled:opacity-40">{saving ? "保存中…" : "保存修改"}</button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
