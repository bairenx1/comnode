import type { AppMode } from "./types";

export const modeToWorkflowId: Record<string, string> = {
  t2i: "txt2img",
  i2i: "img2img",
  i2v: "unsloth_flowers",
  face: "img2img",
  clothes: "img2img",
  inpaint: "img2img",
};

export const modeNameMap: Record<string, string> = {
  t2i: "文生图",
  i2i: "图生图",
  i2v: "图生视频",
  face: "模型换脸",
  clothes: "电商换衣",
  inpaint: "局部重绘",
};

export interface WorkflowInfo {
  workflow_id: string;
  name: string;
  category: string;
  ui_schema: { fields: { name: string; type: string; description?: string; role?: string; label?: string }[] };
  workflow_file: string;
  mapping_file: string;
}

export interface QueueResult {
  prompt_id: string;
  number: number;
  node_errors: Record<string, unknown>;
  request: unknown;
}

export interface AssetItem {
  id: string;
  name: string;
  hash: string;
  tags: string[];
  preview_url?: string;
  url?: string;
  created_at?: string;
}

export interface WsInfo {
  ws_url: string;
  base_url: string;
  comfy_base_url?: string;
}

export interface JobParams {
  prompt: string;
  negative_prompt?: string;
  width?: number;
  height?: number;
  steps?: number;
  cfg?: number;
  seed?: number;
  denoise?: number;
  frame_count?: number;
  fps?: number;
  motion_bucket_id?: number;
  augmentation_level?: number;
  image_asset_hash?: string;
  target_asset_hash?: string;
  video_asset_hash?: string;
  [key: string]: unknown;
}

export interface QueueJob {
  params: JobParams;
  asset_hashes?: Record<string, string>;
}

class ComfyApiClient {
  private baseUrl = window.location.origin;

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const url = this.baseUrl + path;
    const resp = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!resp.ok) {
      const errBody = await resp.text();
      throw new Error("API " + resp.status + ": " + errBody);
    }
    return resp.json() as Promise<T>;
  }

  async health() { return this.request<{ok: boolean; comfy_base_url: string}>("/api/health"); }

  async workflows() { return this.request<{workflows: WorkflowInfo[]}>("/api/workflows"); }

  async queueBatch(workflowId: string, jobs: QueueJob[], clientId?: string) {
    return this.request<{client_id: string; queued: QueueResult[]}>("/api/queue/batch", {
      method: "POST",
      body: JSON.stringify({
        workflow_id: workflowId,
        jobs,
        client_id: clientId || crypto.randomUUID().replace(/-/g, ""),
      }),
    });
  }

  async queue() { return this.request<unknown>("/api/queue"); }

  async job(promptId: string) {
    return this.request<{job: unknown; history: {prompt_id: string; outputs?: Record<string, unknown>; status?: {completed: boolean; status_str?: string}} | null}>("/api/jobs/" + promptId);
  }

  async assets(query?: {limit?: number; offset?: number; order?: string}) {
    const params = new URLSearchParams();
    if (query?.limit) params.set("limit", String(query.limit));
    if (query?.offset) params.set("offset", String(query.offset));
    if (query?.order) params.set("order", query.order);
    const qs = params.toString();
    return this.request<{assets: AssetItem[]; total?: number}>("/api/assets" + (qs ? "?" + qs : ""));
  }

  async uploadAsset(file: File, tags?: string): Promise<AssetItem> {
    const form = new FormData();
    form.append("file", file);
    form.append("tags", tags || "input");
    const resp = await fetch(this.baseUrl + "/api/assets/upload", { method: "POST", body: form });
    if (!resp.ok) { const err = await resp.text(); throw new Error("Upload failed " + resp.status + ": " + err); }
    return resp.json() as Promise<AssetItem>;
  }

  async deleteAsset(assetId: string, deleteContent?: boolean) {
    const params = new URLSearchParams();
    if (deleteContent) params.set("delete_content", "1");
    const qs = params.toString();
    const resp = await fetch(this.baseUrl + "/api/assets/" + encodeURIComponent(assetId) + (qs ? "?" + qs : ""), { method: "DELETE" });
    if (!resp.ok) { const err = await resp.text(); throw new Error("Delete failed " + resp.status + ": " + err); }
    return resp.json();
  }

  getAssetDownloadUrl(assetId: string) {
    return this.baseUrl + "/api/assets/" + encodeURIComponent(assetId) + "/content";
  }

  async wsInfo() { return this.request<WsInfo>("/api/ws-info"); }
}

export const api = new ComfyApiClient();
