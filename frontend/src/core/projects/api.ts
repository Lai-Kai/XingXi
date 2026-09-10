import { fetch } from "@/core/api/fetcher";
import { getBackendBaseURL } from "@/core/config";

export type ResearchProject = {
  id: string;
  name: string;
  archived: boolean;
  created_at: string;
  document_count?: number;
  updated_at?: string;
};

type RawResearchProject = Omit<ResearchProject, "archived"> & {
  archived: boolean | 0 | 1;
};

export type ResearchProjectDocument = {
  id: string;
  title: string;
  edition: string;
  source_type: string;
  source_level: string;
  source_institution: string;
  status: string;
  added_at: string;
};

export type ResearchRecordKind = "question" | "note" | "conclusion";

export type ResearchProjectRecord = {
  id: string;
  project_id: string;
  kind: ResearchRecordKind;
  content: string;
  created_by: string;
  created_at: string;
  updated_at: string;
};

async function errorMessage(response: Response) {
  const payload = (await response.json().catch(() => null)) as {
    detail?: string;
  } | null;
  return payload?.detail ?? "研究项目请求失败";
}

function normalizeResearchProject(
  project: RawResearchProject,
): ResearchProject {
  return {
    ...project,
    archived: project.archived === true || project.archived === 1,
  };
}

export async function listResearchProjects(): Promise<ResearchProject[]> {
  const response = await fetch(`${getBackendBaseURL()}/api/research-projects`);
  if (!response.ok) throw new Error(await errorMessage(response));
  const projects = (await response.json()) as RawResearchProject[];
  return projects.map(normalizeResearchProject);
}

export async function createResearchProject(
  name: string,
): Promise<ResearchProject> {
  const response = await fetch(`${getBackendBaseURL()}/api/research-projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return normalizeResearchProject(
    (await response.json()) as RawResearchProject,
  );
}

export async function getResearchProject(id: string): Promise<ResearchProject> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/research-projects/${encodeURIComponent(id)}`,
  );
  if (!response.ok) throw new Error(await errorMessage(response));
  return normalizeResearchProject(
    (await response.json()) as RawResearchProject,
  );
}

export async function renameResearchProject(
  id: string,
  name: string,
): Promise<ResearchProject> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/research-projects/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    },
  );
  if (!response.ok) throw new Error(await errorMessage(response));
  return normalizeResearchProject(
    (await response.json()) as RawResearchProject,
  );
}

export async function setResearchProjectArchived(
  id: string,
  archived: boolean,
): Promise<ResearchProject> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/research-projects/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ archived }),
    },
  );
  if (!response.ok) throw new Error(await errorMessage(response));
  return normalizeResearchProject(
    (await response.json()) as RawResearchProject,
  );
}

export async function addDocumentToResearchProject(
  projectId: string,
  documentId: string,
): Promise<void> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/research-projects/${encodeURIComponent(projectId)}/documents`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_id: documentId }),
    },
  );
  if (!response.ok) throw new Error(await errorMessage(response));
}

export async function listResearchProjectDocuments(
  projectId: string,
): Promise<ResearchProjectDocument[]> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/research-projects/${encodeURIComponent(projectId)}/documents`,
  );
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

export async function removeDocumentFromResearchProject(
  projectId: string,
  documentId: string,
): Promise<void> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/research-projects/${encodeURIComponent(projectId)}/documents/${encodeURIComponent(documentId)}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw new Error(await errorMessage(response));
}

export async function deleteResearchProject(projectId: string): Promise<void> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/research-projects/${encodeURIComponent(projectId)}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw new Error(await errorMessage(response));
}

export async function listResearchProjectRecords(
  projectId: string,
): Promise<ResearchProjectRecord[]> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/research-projects/${encodeURIComponent(projectId)}/records`,
  );
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

export async function createResearchProjectRecord(
  projectId: string,
  kind: ResearchRecordKind,
  content: string,
): Promise<ResearchProjectRecord> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/research-projects/${encodeURIComponent(projectId)}/records`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind, content }),
    },
  );
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

export async function deleteResearchProjectRecord(
  projectId: string,
  recordId: string,
): Promise<void> {
  const response = await fetch(
    `${getBackendBaseURL()}/api/research-projects/${encodeURIComponent(projectId)}/records/${encodeURIComponent(recordId)}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw new Error(await errorMessage(response));
}
