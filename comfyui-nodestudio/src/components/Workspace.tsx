// BUILD-GEN: 20202020
import React, { useState, useRef, useEffect, useCallback } from "react";
import { AppMode } from "../types";
import { api, modeToWorkflowId, modeNameMap, type JobParams, type QueueResult, type AssetItem } from "../api";
import {
  UploadCloud, Play, Settings2, Image as ImageIcon, Cpu, Download,
  Layers, Sparkles, RefreshCw, Dna, Maximize2, Share2, CheckCircle2,
  XCircle, Trash2, History, Plus, Minus, Library, ChevronLeft, ChevronRight,
  Eye, Bookmark, Star, Lock, LockOpen, Shuffle
} from "lucide-react";
interface Props {
  mode: AppMode;
  onSendToWorkflow: (mode: AppMode, imageUrl?: string) => void;
  pendingImageUrl: string | null;
  onClearPendingImage: () => void;
}
function getFieldsForMode(mode: string, bindings: Record<string, string>, workflows: {workflow_id: string; ui_schema: {fields: any[]}}[]) {
  const wid = bindings[mode];
  if (!wid) return null;
  const wf = workflows.find(w => w.workflow_id === wid);
  return wf?.ui_schema?.fields || null;
}
export function Workspace({ mode, onSendToWorkflow, pendingImageUrl, onClearPendingImage }: Props) {
  const [prompt, setPrompt] = useState("");
  const [customBindings, setCustomBindings] = useState<Record<string, string>>(() => {
    try { return JSON.parse(localStorage.getItem("ws_bindings") || "{}"); } catch { return {}; }
  });
  const [bindingMenuOpen, setBindingMenuOpen] = useState(false);
  const [workflowSchemas, setWorkflowSchemas] = useState<Record<string, {ui_schema: {fields: any[]}}>>({});
  const [workflowList, setWorkflowList] = useState<{workflow_id: string; name: string}[]>([]);
  const [negativePrompt, setNegativePrompt] = useState("");
  const [params, setParams] = useState<Record<string, any>>({});
  const [seedFixed, setSeedFixed] = useState(false);
  const [batchCount, setBatchCount] = useState(4);
  const [batchSettingsOpen, setBatchSettingsOpen] = useState(false);
  const batchSettingsRef = useRef<HTMLDivElement>(null);
  // 动态图片上传状态（按字段名索引，支持任意数量上传区）
  const [imageUploads, setImageUploads] = useState<Record<string, {file: File | null; preview: string | null; hash: string | null}>>({});
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStep, setProgressStep] = useState(0);
  const [progressTotal, setProgressTotal] = useState(0);
  const [statusText, setStatusText] = useState("");
  const [executingNode, setExecutingNode] = useState("");
  const [nodeProgress, setNodeProgress] = useState<Record<string, {name: string; state: string; value: number; max: number}>>({});
  const [result, setResult] = useState<{ url?: string; prompt_id?: string; outputs?: Record<string, unknown> } | null>(null);
  const [batchResults, setBatchResults] = useState<{ url: string; prompt_id: string }[]>([]);
  const [selectedBatchIndex, setSelectedBatchIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [queuedJobs, setQueuedJobs] = useState<QueueResult[]>([]);
  const [showSendMenu, setShowSendMenu] = useState(false);
  const [clientId] = useState(() => crypto.randomUUID().replace(/-/g, ""));
  const [gpuUsage, setGpuUsage] = useState(0);
  const [wsConnected, setWsConnected] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const uploadInputRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const [historyOpen, setHistoryOpen] = useState(false);
  const [generationHistory, setGenerationHistory] = useState<{url: string; prompt: string; mode: string; time: string}[]>(() => {
    try { return JSON.parse(localStorage.getItem("ws_history") || "[]"); } catch { return []; }
  });
  const [assetSaved, setAssetSaved] = useState(false);
  const [assetsList, setAssetsList] = useState<AssetItem[]>([]);
  const [assetsLoading, setAssetsLoading] = useState(false);
  const [assetsTotal, setAssetsTotal] = useState(0);
  const [assetsPage, setAssetsPage] = useState(0);
  const [savedPrompts, setSavedPrompts] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem("ws_saved_prompts") || "[]"); } catch { return []; }
  });
  const [promptCollectionOpen, setPromptCollectionOpen] = useState(false);
  const promptCollectionRef = useRef<HTMLDivElement>(null);
  const historyRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const expectedJobCountRef = useRef(0);
  const receivedJobCountRef = useRef(0);
  const activeWorkflowId = customBindings[mode] || modeToWorkflowId[mode] || null;
  const dynamicFields = activeWorkflowId && workflowSchemas[activeWorkflowId] ? workflowSchemas[activeWorkflowId].ui_schema.fields : null;
  const isGenMode = !["assets", "prompts", "settings"].includes(mode);
  // 基于工作流 schema 动态检测图片上传字段
  const imageFields = (dynamicFields || []).filter(f => f.role === 'image_upload' || f.name.endsWith('_asset_hash'));
  const showImageUpload = imageFields.length > 0;
  useEffect(() => {
    api.workflows().then(r => { setWorkflowList(r.workflows.map(w => ({workflow_id: w.workflow_id, name: w.name}))); const sm: Record<string, any> = {}; r.workflows.forEach(w => { sm[w.workflow_id] = {ui_schema: w.ui_schema}; }); setWorkflowSchemas(sm); }).catch(() => {});
  }, []);
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowSendMenu(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (batchSettingsRef.current && !batchSettingsRef.current.contains(event.target as Node)) {
        setBatchSettingsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);
  useEffect(() => {
    localStorage.setItem("ws_history", JSON.stringify(generationHistory));
  }, [generationHistory]);
  useEffect(() => {
    async function connectWs() {
      try {
        const info = await api.wsInfo();
        const ws = new WebSocket(info.ws_url + "?clientId=" + clientId);
        wsRef.current = ws;
        ws.onopen = () => setWsConnected(true);
        ws.onmessage = (evt) => {
          try {
            const msg = JSON.parse(evt.data);
            if (msg.type === "progress") {
              const pct = (msg.data.step / msg.data.max_step) * 100;
              setProgress(pct);
              setProgressStep(msg.data.step);
              setProgressTotal(msg.data.max_step);
              const nodeLabel = executingNode ? `[${executingNode}] ` : "";
              setStatusText(`${nodeLabel}采样迭代 ${msg.data.step}/${msg.data.max_step}`);
            } else if (msg.type === "progress_state") {
              // 各节点独立进度
              const nodesData = msg.data?.nodes || {};
              setNodeProgress((prev: any) => {
                const next = { ...prev };
                for (const [nid, info] of Object.entries(nodesData) as [string, any][]) {
                  next[nid] = {
                    name: info.display_node_name || info.display_node_id || nid,
                    state: info.state || "running",
                    value: info.value || 0,
                    max: info.max || 1,
                  };
                }
                return next;
              });
            } else if (msg.type === "executing") {
              const nodeName = msg.data.node;
              setExecutingNode(nodeName || "");
              if (nodeName) {
                setStatusText("执行节点: " + nodeName);
              } else {
                setStatusText("节点执行完毕, 等待输出...");
              }
            } else if (msg.type === "execution_start") {
              setStatusText("工作流开始执行...");
              setNodeProgress({});
            } else if (msg.type === "executed") {
              const nodeData = msg.data;
              if (nodeData?.output?.images && nodeData.output.images[0]) {
                const img = nodeData.output.images[0];
                const baseUrl = "http://" + window.location.host;
                const imgUrl = baseUrl + "/view?filename=" + encodeURIComponent(img.filename) + "&subfolder=" + encodeURIComponent(img.subfolder || "") + "&type=" + (img.type || "output");
                const newItem = { url: imgUrl, prompt_id: msg.data.prompt_id || nodeData.prompt_id };
                // 累积批量结果
                setBatchResults(prev => {
                  const updated = [...prev, newItem];
                  if (prev.length === 0) {
                    setResult({ url: imgUrl, prompt_id: newItem.prompt_id, outputs: nodeData.output });
                    setSelectedBatchIndex(0);
                  }
                  return updated;
                });
                setAssetSaved(false);
                // 清除轮询，防止覆盖 WebSocket 已设置的结果
                if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
                fetch(imgUrl)
                  .then(resp => resp.blob())
                  .then(blob => {
                    const file = new File([blob], img.filename || "generated.png", { type: blob.type || "image/png" });
                    return api.uploadAsset(file, "generated");
                  })
                  .then(() => { setAssetSaved(true); })
                  .catch((err: any) => console.warn("Asset save skipped:", err));
                const entry = {
                  url: imgUrl,
                  prompt: prompt || "(empty)",
                  mode: mode,
                  time: new Date().toISOString(),
                };
                setGenerationHistory(prev => {
                  const updated = [entry, ...prev];
                  if (updated.length > 100) updated.length = 100;
                  return updated;
                });
                receivedJobCountRef.current += 1;
                const done = receivedJobCountRef.current;
                const total = expectedJobCountRef.current || 1;
                setProgress(100);
                setStatusText("生成完成 (" + done + "/" + total + ")");
                if (done >= total) {
                  setGenerating(false);
                  receivedJobCountRef.current = 0;
                  expectedJobCountRef.current = 0;
                }
              }
            } else if (msg.type === "status") {
              if (msg.data?.status?.exec_info) {
                setGpuUsage(msg.data.status.exec_info.queue_remaining > 0 ? 85 : 12);
              }
            }
          } catch (e) { /* ignore parse errors */ }
        };
        ws.onclose = () => { setWsConnected(false); wsRef.current = null; };
        ws.onerror = () => {};
      } catch (e) {
        console.warn("WS connect failed", e);
      }
    }
    connectWs();
    return () => { if (wsRef.current) { wsRef.current.close(); wsRef.current = null; } };
  }, [clientId]);
  useEffect(() => {
    return () => {
      // 清理所有图片预览 URL
      Object.values(imageUploads).forEach((u: {preview: string | null}) => { if (u.preview) URL.revokeObjectURL(u.preview); });
    };
  }, [imageUploads]);
  useEffect(() => { localStorage.setItem("ws_saved_prompts", JSON.stringify(savedPrompts)); }, [savedPrompts]);
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (promptCollectionRef.current && !promptCollectionRef.current.contains(event.target as Node)) {
        setPromptCollectionOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);
  useEffect(() => {
    if (mode !== "assets") return;
    setAssetsLoading(true);
    api.assets({ limit: 20, offset: assetsPage * 20, order: "desc" })
      .then(r => {
        setAssetsList(r.assets || []);
        setAssetsTotal(r.total || 0);
      })
      .catch(() => {})
      .finally(() => setAssetsLoading(false));
  }, [mode, assetsPage]);
  // 从其他工作流发送图片过来时，自动设为第一个图片上传区
  useEffect(() => {
    if (!pendingImageUrl || !showImageUpload || imageFields.length === 0) return;
    const firstField = imageFields[0].name;
    const abort = new AbortController();
    fetch(pendingImageUrl, { signal: abort.signal })
      .then(resp => resp.blob())
      .then(blob => {
        const filename = "sendto_" + Date.now() + ".png";
        const file = new File([blob], filename, { type: blob.type || "image/png" });
        handleImageUpload(firstField, file);
        onClearPendingImage();
      })
      .catch((err: any) => {
        if (err.name !== "AbortError") console.warn("接收发送图片失败:", err);
        onClearPendingImage();
      });
    return () => abort.abort();
  }, [pendingImageUrl, mode]);
  // 动态图片上传处理
  const handleImageUpload = (fieldName: string, file: File) => {
    const prev = imageUploads[fieldName];
    if (prev?.preview) URL.revokeObjectURL(prev.preview);
    setImageUploads(p => ({ ...p, [fieldName]: { file, preview: URL.createObjectURL(file), hash: null } }));
  };
  const handleImageRemove = (fieldName: string) => {
    const prev = imageUploads[fieldName];
    if (prev?.preview) URL.revokeObjectURL(prev.preview);
    setImageUploads(p => {
      const { [fieldName]: _, ...rest } = p;
      return rest;
    });
  };
  const randomizeSeed = () => setParams((p: any) => ({...p, seed: Math.floor(Math.random() * 2**32)}));
  const uploadAndGetHash = async (file: File): Promise<string | null> => {
    try {
      const asset = await api.uploadAsset(file);
      return asset.hash || null;
    } catch (e) {
      setError("上传失败: " + (e instanceof Error ? e.message : String(e)));
      return null;
    }
  };
  const handleGenerate = async () => {
    setError(null);
    setResult(null);
    setBatchResults([]);
    setSelectedBatchIndex(0);
    setProgress(0);
    setProgressStep(0);
    setProgressTotal(0);
    setQueuedJobs([]);
    setNodeProgress({});
    setExecutingNode("");
    setGenerating(true);
    setStatusText("正在准备...");
    expectedJobCountRef.current = 1;
    receivedJobCountRef.current = 0;
    try {
      // 上传所有图片并注入 hash
      const imageHashes: Record<string, string> = {};
      for (const fieldName of Object.keys(imageUploads)) {
        const entry = imageUploads[fieldName];
        if (entry.file && !entry.hash) {
          setStatusText("正在上传素材...");
          const hash = await uploadAndGetHash(entry.file);
          if (hash) {
            setImageUploads(p => ({ ...p, [fieldName]: { ...p[fieldName], hash } }));
            imageHashes[fieldName] = hash;
          }
        } else if (entry.hash) {
          imageHashes[fieldName] = entry.hash;
        }
      }
      const workflowId = customBindings[mode] || modeToWorkflowId[mode] || "txt2img";
      // 工作流字段默认值（用户未修改时使用）
      const fieldDefaults: Record<string, unknown> = {};
      if (dynamicFields) {
        for (const f of dynamicFields) {
          if (f.default !== undefined && f.default !== null) fieldDefaults[f.name] = f.default;
        }
      }
      const jobParams: JobParams = {
        ...fieldDefaults,
        prompt: params.prompt || prompt || fieldDefaults.prompt || "masterpiece, best quality",
        negative_prompt: params.negative_prompt || negativePrompt || fieldDefaults.negative_prompt || undefined,
        seed: seedFixed ? (params.seed ?? fieldDefaults.seed ?? 0) : Math.floor(Math.random() * 2**32),
        ...params,
        ...imageHashes,
      };
      if (imageFields.length > 0 && mode === "i2v") jobParams.frame_count = 16;
      setStatusText("提交任务...");
      const batchResult = await api.queueBatch(workflowId, [{ params: jobParams }], clientId);
      setQueuedJobs(batchResult.queued);
      const promptId = batchResult.queued[0]?.prompt_id;
      if (promptId) {
        // 清除之前的轮询
        if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        let attempts = 0;
        pollRef.current = setInterval(async () => {
          attempts++;
          try {
            const jobResult = await api.job(promptId);
            if (jobResult.history?.status?.completed || jobResult.history?.outputs) {
              // 从历史记录输出中提取图片 URL
              let imgUrl: string | undefined;
              const outputs = jobResult.history?.outputs;
              if (outputs) {
                const firstNode: any = Object.values(outputs).find((v: any) => v?.images?.length > 0);
                if (firstNode?.images?.[0]) {
                  const img = firstNode.images[0];
                  const baseUrl = "http://" + window.location.host;
                  imgUrl = baseUrl + "/view?filename=" + encodeURIComponent(img.filename) + "&subfolder=" + encodeURIComponent(img.subfolder || "") + "&type=" + (img.type || "output");
                }
              }
              // 仅在 WebSocket 未设置结果时更新（保留已有的 url）
              setResult(prev => {
                if (prev?.url) return prev;
                return { url: imgUrl, prompt_id: promptId, outputs };
              });
              if (imgUrl) {
                setBatchResults(prev => {
                  if (prev.length === 0) {
                    return [{ url: imgUrl!, prompt_id: promptId }];
                  }
                  return prev;
                });
              }
              setGenerating(false);
              expectedJobCountRef.current = 0;
              receivedJobCountRef.current = 0;
              setAssetSaved(false);
              setProgress(100);
              setStatusText("生成完成");
              if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
            }
          } catch (e) { /* ignore */ }
          if (attempts > 60) {
            if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
            setGenerating(false);
            setStatusText("任务超时");
          }
        }, 5000);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setGenerating(false);
      setStatusText("生成失败");
    }
  };
  const handleBatchGenerate = async () => {
    setError(null); setResult(null); setBatchResults([]); setSelectedBatchIndex(0);
    setProgress(0); setQueuedJobs([]);
    setNodeProgress({});
    setExecutingNode("");
    setGenerating(true);
    setStatusText("正在提交批量任务...");
    expectedJobCountRef.current = batchCount;
    receivedJobCountRef.current = 0;
    try {
      // 上传所有图片并收集 hash
      const imageHashes: Record<string, string> = {};
      for (const fieldName of Object.keys(imageUploads)) {
        const entry = imageUploads[fieldName];
        if (entry.file && !entry.hash) {
          setStatusText("正在上传素材...");
          const hash = await uploadAndGetHash(entry.file);
          if (hash) {
            setImageUploads(p => ({ ...p, [fieldName]: { ...p[fieldName], hash } }));
            imageHashes[fieldName] = hash;
          }
        } else if (entry.hash) {
          imageHashes[fieldName] = entry.hash;
        }
      }
      const workflowId = customBindings[mode] || modeToWorkflowId[mode] || "txt2img";
      // 工作流字段默认值（用户未修改时使用）
      const fieldDefaults: Record<string, unknown> = {};
      if (dynamicFields) {
        for (const f of dynamicFields) {
          if (f.default !== undefined && f.default !== null) fieldDefaults[f.name] = f.default;
        }
      }
      const baseSeed = params.seed || fieldDefaults.seed || Math.floor(Math.random() * 2**32);
      const jobs = Array.from({ length: batchCount }, (_, i) => ({
        params: {
          ...fieldDefaults,
          prompt: params.prompt || prompt || fieldDefaults.prompt || "masterpiece, best quality",
          negative_prompt: params.negative_prompt || negativePrompt || fieldDefaults.negative_prompt || undefined,
          seed: seedFixed ? (baseSeed + i) : Math.floor(Math.random() * 2**32),
          ...params,
          ...imageHashes,
        } as JobParams,
      }));
      const batchResult = await api.queueBatch(workflowId, jobs, clientId);
      setQueuedJobs(batchResult.queued);
      setStatusText("已提交 " + batchResult.queued.length + " 个任务，等待生成...");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setGenerating(false);
      expectedJobCountRef.current = 0;
      receivedJobCountRef.current = 0;
      setStatusText("提交失败");
    }
  };
  const handleDeleteAsset = async (assetId: string) => {
    try {
      await api.deleteAsset(assetId);
      // 从列表中移除已删除项并刷新
      setAssetsList(prev => prev.filter(a => a.id !== assetId));
      setAssetsTotal(prev => Math.max(0, prev - 1));
    } catch (e) {
      console.warn("删除资产失败:", e);
    }
  };
  const toggleSavePrompt = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setSavedPrompts(prev => {
      if (prev.includes(trimmed)) return prev.filter(p => p !== trimmed);
      if (prev.length >= 50) return prev;
      return [...prev, trimmed];
    });
  };
  const switchBatchImage = (index: number) => {
    if (index >= 0 && index < batchResults.length) {
      setSelectedBatchIndex(index);
      setResult({ url: batchResults[index].url, prompt_id: batchResults[index].prompt_id });
    }
  };
  const jumpOptions = [
    { id: "i2i", label: "发送至图生图" },
    { id: "i2v", label: "发送至图生视频" },
    { id: "face", label: "发送至换脸(作为目标)" },
    { id: "clothes", label: "发送至换衣(作为模特)" },
    { id: "inpaint", label: "发送至局部重务" },
  ].filter(opt => opt.id !== mode);
  if (mode === "assets") {
    const baseUrl = "http://" + window.location.host;
    const totalPages = Math.ceil(assetsTotal / 20);
    return (
      <div className="flex-1 flex flex-col min-h-0 bg-bg-base">
        <div className="h-14 border-b border-border-main flex items-center justify-between px-5 shrink-0 bg-bg-panel/80">
          <h2 className="text-sm font-semibold text-text-primary flex items-center gap-2">
            <Library className="w-4 h-4 text-accent" />
            资产库
            {assetsTotal > 0 && <span className="text-xs text-text-secondary font-normal">({assetsTotal} 项)</span>}
          </h2>
          <div className="flex items-center gap-2">
            {assetsPage > 0 && (
              <button onClick={() => setAssetsPage(p => p - 1)} className="text-[11px] font-mono px-2.5 py-1 rounded border border-border-main/60 hover:border-accent/40 text-text-secondary hover:text-text-primary transition-all">
                上一页
              </button>
            )}
            {totalPages > 0 && <span className="text-[10px] font-mono text-text-secondary">{assetsPage + 1}/{totalPages}</span>}
            {(assetsPage + 1) < totalPages && (
              <button onClick={() => setAssetsPage(p => p + 1)} className="text-[11px] font-mono px-2.5 py-1 rounded border border-border-main/60 hover:border-accent/40 text-text-secondary hover:text-text-primary transition-all">
                下一页
              </button>
            )}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto custom-scrollbar p-5">
          {assetsLoading ? (
            <div className="flex items-center justify-center h-full">
              <RefreshCw className="w-8 h-8 animate-spin text-text-secondary opacity-50" />
            </div>
          ) : assetsList.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-text-secondary gap-3">
              <ImageIcon className="w-12 h-12 opacity-30" />
              <p className="font-mono text-xs tracking-widest">资产库为空</p>
              <p className="text-[11px] opacity-50">生成图片后将自动存入资产库</p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* 按日期分组 */}
              {(() => {
                const grouped: Record<string, AssetItem[]> = {};
                assetsList.forEach(a => {
                  const dateKey = a.created_at ? a.created_at.slice(0, 10) : "未知日期";
                  if (!grouped[dateKey]) grouped[dateKey] = [];
                  grouped[dateKey].push(a);
                });
                return Object.entries(grouped).map(([dateKey, items]) => (
                  <div key={dateKey}>
                    <div className="text-[11px] font-mono text-text-secondary mb-3 pl-1 border-l-2 border-accent/40 pl-2.5 tracking-wider">
                      {dateKey === "未知日期" ? "未知日期" : dateKey}
                      <span className="ml-2 text-text-secondary/50">({items.length})</span>
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
                      {items.map((asset) => (
                        <div key={asset.id || asset.hash} className="group bg-bg-panel border border-border-main/60 hover:border-accent/30 rounded-lg overflow-hidden transition-all hover:shadow-lg">
                          <div className="aspect-square bg-bg-input overflow-hidden relative">
                            {asset.preview_url || asset.url ? (
                              <img
                                src={asset.preview_url || asset.url}
                                alt={asset.name || "asset"}
                                className="w-full h-full object-cover"
                                loading="lazy"
                                onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                              />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center text-text-secondary">
                                <ImageIcon className="w-8 h-8 opacity-30" />
                              </div>
                            )}
                            {/* hover 操作图标覆盖层 */}
                            <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-all flex items-center justify-center gap-2">
                              <div className="opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1.5">
                                {asset.url && (
                                  <a
                                    href={asset.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="p-2 bg-white/90 hover:bg-white rounded-md text-text-primary hover:text-accent transition-all hover:scale-110"
                                    title="查看大图"
                                    onClick={(e) => e.stopPropagation()}
                                  >
                                    <Eye className="w-3.5 h-3.5" />
                                  </a>
                                )}
                                <a
                                  href={api.getAssetDownloadUrl(asset.id)}
                                  download
                                  className="p-2 bg-white/90 hover:bg-white rounded-md text-text-primary hover:text-accent transition-all hover:scale-110"
                                  title="下载"
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <Download className="w-3.5 h-3.5" />
                                </a>
                                <button
                                  onClick={(e) => { e.stopPropagation(); e.preventDefault(); handleDeleteAsset(asset.id); }}
                                  className="p-2 bg-white/90 hover:bg-danger/90 hover:text-white rounded-md text-text-primary transition-all hover:scale-110"
                                  title="删除"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </div>
                          </div>
                          <div className="p-2.5 space-y-1.5">
                            <p className="text-xs text-text-primary truncate font-mono">{asset.name || asset.hash?.slice(0, 12) || "未命名"}</p>
                            {asset.tags && asset.tags.length > 0 && (
                              <div className="flex flex-wrap gap-1">
                                {asset.tags.slice(0, 3).map((tag, i) => (
                                  <span key={i} className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-accent/10 text-accent">{tag}</span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ));
              })()}
            </div>
          )}
        </div>
      </div>
    );
  }
  if (!isGenMode) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center bg-bg-base/50 text-text-secondary">
        <Sparkles className="w-12 h-12 mb-4 opacity-50" />
        <p className="font-mono text-sm uppercase tracking-widest">{mode} 模块尚未实现</p>
        <p className="text-xs mt-2 opacity-50">请从侧边栏选择生成工作流。</p>
      </div>
    );
  }
  return (
    <>
    <div className="flex-1 flex flex-col lg:flex-row min-h-0 bg-bg-base relative">      {/* Left Panel */}
      <div className="w-full lg:w-[420px] flex-shrink-0 border-r border-border-main bg-bg-panel flex flex-col z-10 custom-scrollbar overflow-y-auto">
        <div className="p-5 border-b border-border-main/80 bg-bg-panel/40 sticky top-0 z-20 backdrop-blur-md">
          <h2 className="text-lg font-semibold text-text-primary flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-accent" />
            {modeNameMap[mode] || "生成工作流"}
          </h2>
          <p className="text-xs text-text-secondary mt-1 font-mono">工作流引擎：就绪</p>
          <div className="flex items-center gap-2 mt-2">
            <div className="relative">
              <button
                onClick={() => setBindingMenuOpen(!bindingMenuOpen)}
                className="text-[11px] font-mono flex items-center gap-1.5 px-2.5 py-1 rounded border border-border-main/60 bg-bg-input/40 hover:bg-bg-input hover:border-accent/40 text-text-secondary hover:text-text-primary transition-all"
              >
                <Settings2 className="w-3 h-3" />
                {customBindings[mode]
                  ? (workflowList.find(w => w.workflow_id === customBindings[mode])?.name || customBindings[mode])
                  : "绑定工作流"}
              </button>
              {bindingMenuOpen && (
                <div className="absolute top-full left-0 mt-1 w-56 bg-bg-panel border border-border-main rounded-lg shadow-xl py-1 z-50 max-h-60 overflow-y-auto">
                  <div className="px-3 py-2 text-[10px] text-text-secondary border-b border-border-main/50 font-mono tracking-wider">选择绑定的工作流</div>
                  <button
                    onClick={() => {
                      const next = { ...customBindings };
                      delete next[mode];
                      setCustomBindings(next);
                      localStorage.setItem("ws_bindings", JSON.stringify(next));
                      setBindingMenuOpen(false);
                    }}
                    className={"w-full text-left px-4 py-2 text-xs transition-colors flex items-center justify-between " + (!customBindings[mode] ? "text-accent bg-accent/5" : "text-text-primary hover:bg-bg-input")}
                  >
                    默认 (自动选择)
                    {!customBindings[mode] && <span className="text-accent text-[10px]">?</span>}
                  </button>
                  {workflowList.map(w => (
                    <button
                      key={w.workflow_id}
                      onClick={() => {
                        const next = { ...customBindings, [mode]: w.workflow_id };
                        setCustomBindings(next);
                        localStorage.setItem("ws_bindings", JSON.stringify(next));
                        setBindingMenuOpen(false);
                      }}
                      className={"w-full text-left px-4 py-2 text-xs transition-colors flex items-center justify-between " + (customBindings[mode] === w.workflow_id ? "text-accent bg-accent/5" : "text-text-primary hover:bg-bg-input")}
                    >
                      {w.name}
                      <span className="text-text-secondary text-[10px]">{w.workflow_id}</span>
                      {customBindings[mode] === w.workflow_id && <span className="text-accent text-[10px]">?</span>}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="p-5 space-y-6 flex-1">
          <div className="space-y-5">
            {dynamicFields && (() => {
              // 字段排序优先级 — 提示词 > LoRA > 采样 > 控制 > 尺寸 > 模型 > 其他
              const order: Record<string, number> = {
                prompt: 1, positive_prompt: 1, text: 1,
                negative_prompt: 2, negative_text: 2,
                lora_name: 8, lora_weight: 9, strength_model: 10, strength_clip: 11,
                seed: 15, noise_seed: 15, steps: 16, cfg: 17, guidance: 17,
                sampler_name: 18, scheduler: 19, denoise: 20, denoising_strength: 20,
                control_net_name: 23, cn_strength: 24, control_strength: 24,
                start_percent: 25, end_percent: 26,
                width: 30, height: 31, batch_size: 32, image_width: 30, image_height: 31,
                upscale_method: 35, upscale_factor: 36,
                ckpt_name: 40, checkpoint: 40, model_name: 40,
                vae_name: 42, clip_name: 43,
                // 视频参数
                frame_count: 50, num_frames: 50, fps: 51, frame_rate: 51,
                motion_bucket_id: 52, augmentation_level: 53, min_cfg: 54,
                motion_frame_count: 55, continue_motion_max_frames: 56,
                audio_scale: 60,
                pose_strength: 62, pose_start: 63, pose_end: 64,
                vace_strength: 65, track_temperature: 66, track_topk: 67,
              };
              // 所有字段由后端 schema 驱动，隐藏字段已在转换时过滤
              const uploadFieldNames = new Set(imageFields.map(f => f.name));
              const sorted = [...dynamicFields]
                .filter(f => !uploadFieldNames.has(f.name))
                .sort((a, b) => (order[a.name] ?? 60) - (order[b.name] ?? 60));

              // 中文标签映射
              const labels: Record<string, string> = {
                prompt: '提示词', positive_prompt: '提示词', text: '提示词',
                negative_prompt: '负向提示词', negative_text: '负向提示词',
                lora_name: 'LoRA 模型', lora_weight: 'LoRA 权重', strength_model: 'LoRA 模型强度', strength_clip: 'LoRA CLIP 强度',
                seed: '随机种子', noise_seed: '噪声种子', steps: '采样步数', cfg: '提示词引导 (CFG)', guidance: '引导强度',
                sampler_name: '采样器', scheduler: '调度器', denoise: '降噪强度', denoising_strength: '降噪强度',
                control_net_name: 'ControlNet', cn_strength: '控制强度', control_strength: '控制强度',
                start_percent: '起始百分比', end_percent: '结束百分比',
                width: '宽度', image_width: '宽度', height: '高度', image_height: '高度',
                batch_size: '批次数量', upscale_method: '放大算法', upscale_factor: '放大倍数',
                ckpt_name: '底模', checkpoint: '底模', model_name: '底模',
                vae_name: 'VAE', clip_name: 'CLIP 模型',
                frame_count: '视频帧数', num_frames: '视频帧数',
                // 视频专用参数
                fps: '帧率 (FPS)', frame_rate: '帧率 (FPS)',
                motion_bucket_id: '运动幅度',
                augmentation_level: '增强级别',
                min_cfg: '最小CFG',
                vace_strength: '控制强度',
                track_temperature: '轨迹温度', track_topk: '轨迹点数量',
                pose_strength: '姿态强度', pose_start: '姿态起始', pose_end: '姿态结束',
                motion_frame_count: '运动帧数',
                continue_motion_max_frames: '运动延续帧数',
                audio_scale: '音频强度',
              };

              // 字段分类
              const loraSet = new Set(['lora_name', 'lora_weight', 'strength_model', 'strength_clip']);
              const samplingSet = new Set(['seed', 'noise_seed', 'steps', 'cfg', 'guidance', 'sampler_name', 'scheduler', 'denoise', 'denoising_strength']);
              const controlSet = new Set(['control_net_name', 'cn_strength', 'control_strength', 'start_percent', 'end_percent']);
              const dimsSet = new Set(['width', 'height', 'batch_size', 'image_width', 'image_height', 'upscale_method', 'upscale_factor']);
              const modelSet = new Set(['ckpt_name', 'checkpoint', 'model_name', 'vae_name', 'clip_name']);
              const videoSet = new Set(['frame_count', 'num_frames', 'fps', 'frame_rate', 'motion_bucket_id', 'augmentation_level', 'min_cfg', 'motion_frame_count', 'continue_motion_max_frames', 'audio_scale', 'pose_strength', 'pose_start', 'pose_end', 'vace_strength', 'track_temperature', 'track_topk']);
              const catOf = (name: string) => {
                if (name === 'prompt' || name === 'positive_prompt' || name === 'text' || name === 'negative_prompt' || name === 'negative_text') return 'prompt';
                if (loraSet.has(name)) return 'lora';
                if (samplingSet.has(name)) return 'sampling';
                if (controlSet.has(name)) return 'control';
                if (dimsSet.has(name)) return 'dimensions';
                if (modelSet.has(name)) return 'model';
                if (videoSet.has(name)) return 'video';
                return 'other';
              };

              let lastCat = '';

              return sorted.map((field) => {
                const cat = catOf(field.name);
                const showHeader = cat !== 'prompt' && cat !== lastCat;
                lastCat = cat;

                const val = (params as any)[field.name];
                const setVal = (v: any) => setParams((prev: any) => ({ ...prev, [field.name]: v }));
                const label = labels[field.name] || field.name;

                return (
                  <React.Fragment key={field.name}>
                    {/* 分段头 */}
                    {showHeader && (
                      <div className="flex items-center gap-2 pt-2 pb-2 border-b border-border-main/30">
                        {cat === 'lora' && <Sparkles className="w-3 h-3 text-accent/50" />}
                        {cat === 'sampling' && <Dna className="w-3 h-3 text-accent/50" />}
                        {cat === 'control' && <Maximize2 className="w-3 h-3 text-accent/50" />}
                        {cat === 'dimensions' && <Maximize2 className="w-3 h-3 text-accent/50" />}
                        {cat === 'model' && <Layers className="w-3 h-3 text-accent/50" />}
                        {cat === 'other' && <Settings2 className="w-3 h-3 text-accent/50" />}
                        <span className="text-[10px] font-mono uppercase tracking-[0.15em] text-accent/60 font-semibold">
                          {cat === 'lora' ? 'LoRA 增效' : cat === 'sampling' ? '采样参数' : cat === 'control' ? '条件控制' : cat === 'dimensions' ? '尺寸设置' : cat === 'model' ? '模型' : cat === 'video' ? '视频参数' : '其他参数'}
                        </span>
                      </div>
                    )}

                    {/* ---- Combo 下拉 ---- */}
                    {field.type === 'combo' && field.options ? (
                      <div>
                        <label className="block text-[11px] font-mono text-text-secondary mb-1.5 tracking-wide">{label}</label>
                        <select
                          value={val ?? field.default ?? ''}
                          onChange={(e) => setVal(e.target.value)}
                          className="w-full bg-bg-input border border-border-main hover:border-accent/30 focus:border-accent/50 rounded-lg p-2.5 text-sm text-text-primary outline-none font-mono cursor-pointer transition-colors appearance-none"
                        >
                          {field.options.map((opt: string) => (
                            <option key={opt} value={opt}>{opt}</option>
                          ))}
                        </select>
                      </div>
                    ) : field.type === 'number' || field.type === 'int' || field.type === 'float' ? (
                      field.name === 'seed' || field.name === 'noise_seed' ? (
                        /* 种子 — 输入框 + 固定/随机按钮 + 随机化按钮 */
                        <div>
                          <label className="block text-[11px] font-mono text-text-secondary mb-1.5 tracking-wide">{label}</label>
                          <div className="flex items-center gap-1.5">
                            <button
                              onClick={() => setSeedFixed(!seedFixed)}
                              className={"p-2 rounded-lg border transition-all " + (seedFixed ? "bg-accent/10 border-accent/40 text-accent" : "bg-bg-input border-border-main text-text-secondary hover:border-accent/30")}
                              title={seedFixed ? "种子已锁定，点击切换为随机" : "种子随机，点击切换为锁定"}
                            >
                              {seedFixed ? <Lock className="w-3.5 h-3.5" /> : <LockOpen className="w-3.5 h-3.5" />}
                            </button>
                            <input
                              type="text"
                              value={val ?? field.default ?? ''}
                              onChange={(e) => { const n = Number(e.target.value); if (!isNaN(n)) setVal(n); }}
                              className={"flex-1 bg-bg-input border focus:border-accent/50 rounded-lg p-2.5 text-sm outline-none font-mono tracking-wider transition-colors " + (seedFixed ? "border-accent/40 text-accent" : "border-border-main text-text-primary")}
                              disabled={generating}
                            />
                            <button
                              onClick={() => setVal(Math.floor(Math.random() * 2 ** 32))}
                              className="p-2 bg-bg-input hover:bg-accent/10 border border-border-main hover:border-accent/40 rounded-lg transition-all group"
                              title="随机生成种子"
                              disabled={generating}
                            >
                              <Shuffle className="w-4 h-4 text-text-secondary group-hover:text-accent transition-colors" />
                            </button>
                          </div>
                          {seedFixed && (
                            <p className="text-[10px] font-mono text-accent/60 mt-1 tracking-wide">种子已锁定, 批量生成将在此种子基础上递增</p>
                          )}
                        </div>
                      ) : field.name === 'width' ? (
                        /* 尺寸 — width+height 并排 */
                        (() => {
                          const hField = sorted.find(f => f.name === 'height');
                          const wVal = (params as any)['width'];
                          const hVal = (params as any)['height'];
                          const setW = (v: any) => setParams((prev: any) => ({ ...prev, width: v }));
                          const setH = (v: any) => setParams((prev: any) => ({ ...prev, height: v }));
                          return (
                            <div>
                              <label className="block text-[11px] font-mono text-text-secondary mb-1.5 tracking-wide">尺寸 (宽 × 高)</label>
                              <div className="flex items-center gap-2">
                                <input
                                  type="number"
                                  min={field.min ?? 64} max={field.max ?? 4096}
                                  value={wVal ?? field.default ?? 512}
                                  onChange={(e) => setW(Number(e.target.value))}
                                  placeholder="宽"
                                  className="flex-1 bg-bg-input border border-border-main focus:border-accent/50 rounded-lg p-2.5 text-sm text-text-primary outline-none font-mono transition-colors"
                                />
                                <span className="text-text-secondary text-xs font-mono select-none">×</span>
                                <input
                                  type="number"
                                  min={hField?.min ?? 64} max={hField?.max ?? 4096}
                                  value={hVal ?? hField?.default ?? 512}
                                  onChange={(e) => setH(Number(e.target.value))}
                                  placeholder="高"
                                  className="flex-1 bg-bg-input border border-border-main focus:border-accent/50 rounded-lg p-2.5 text-sm text-text-primary outline-none font-mono transition-colors"
                                />
                              </div>
                            </div>
                          );
                        })()
                      ) : field.name === 'height' ? null : (
                        /* 普通数字 — Range 滑块 */
                        (() => {
                          const v = val ?? field.default ?? field.min ?? 0;
                          const fmin = field.min ?? 0;
                          const fmax = field.max ?? 100;
                          return (
                            <div>
                              <div className="flex items-center justify-between mb-1.5">
                                <label className="text-[11px] font-mono text-text-secondary tracking-wide">{label}</label>
                                <span className="text-[11px] font-mono font-bold text-accent bg-accent/10 px-2 py-0.5 rounded-full tabular-nums">
                                  {v}
                                </span>
                              </div>
                              <input
                                type="range"
                                min={fmin} max={fmax} step={field.step ?? 1}
                                value={v}
                                onChange={(e) => setVal(Number(e.target.value))}
                                className="w-full accent-accent cursor-pointer"
                              />
                              <div className="flex justify-between text-[10px] font-mono text-text-secondary/50 mt-0.5">
                                <span>{fmin}</span>
                                <span>{fmax}</span>
                              </div>
                            </div>
                          );
                        })()
                      )
                    ) : field.type === 'string' ? (
                      /* 提示词文本域 */
                      (() => {
                        const isNeg = field.name === 'negative_prompt';
                        const ph = field.name === 'prompt' ? '描述你想要的画面...' : field.name === 'negative_prompt' ? '不想看到的内容...' : (field.tooltip || '');
                        return (
                          <div>
                            <label className={'block text-[11px] font-mono mb-1.5 tracking-wide ' + (isNeg ? 'text-danger' : 'text-text-secondary')}>
                              {label}
                            </label>
                            <textarea
                              value={val ?? field.default ?? ''}
                              onChange={(e) => setVal(e.target.value)}
                              className={'w-full bg-bg-input border rounded-md p-3 text-sm text-text-primary outline-none transition-all resize-none custom-scrollbar placeholder-text-secondary/50 leading-relaxed ' + (isNeg ? 'h-20 border-border-main focus:border-danger/40 focus:ring-1 focus:ring-danger/30' : 'h-28 border-border-main focus:border-accent/40 focus:ring-1 focus:ring-accent/30')}
                              placeholder={ph}
                            />
                            {/* 提示词收藏与集锦 — 仅正向提示词 */}
                            {!isNeg && (
                              <div className="flex items-center gap-1.5 mt-1.5">
                                <button
                                  onClick={() => toggleSavePrompt(String(val ?? ''))}
                                  title={savedPrompts.includes(String(val ?? '').trim()) ? '取消收藏' : '收藏此提示词'}
                                  className={'p-1.5 rounded transition-all ' + (savedPrompts.includes(String(val ?? '').trim()) ? 'text-yellow-400 bg-yellow-400/10 hover:bg-yellow-400/20' : 'text-text-secondary hover:text-yellow-400 hover:bg-bg-input')}
                                >
                                  <Star className={'w-3.5 h-3.5 ' + (savedPrompts.includes(String(val ?? '').trim()) ? 'fill-current' : '')} />
                                </button>
                                <div className="relative" ref={promptCollectionRef}>
                                  <button
                                    onClick={() => setPromptCollectionOpen(!promptCollectionOpen)}
                                    title="提示词集锦"
                                    className="p-1.5 rounded text-text-secondary hover:text-accent hover:bg-bg-input transition-all"
                                  >
                                    <Bookmark className="w-3.5 h-3.5" />
                                  </button>
                                  {promptCollectionOpen && (
                                    <div className="absolute bottom-full left-0 mb-1 w-72 max-h-48 overflow-y-auto custom-scrollbar bg-bg-panel border border-border-main rounded-lg shadow-xl py-1 z-50">
                                      <div className="px-3 py-2 text-[10px] text-text-secondary border-b border-border-main/50 font-mono tracking-wider flex justify-between items-center">
                                        提示词集锦 ({savedPrompts.length})
                                        {savedPrompts.length > 0 && (
                                          <button onClick={() => { setSavedPrompts([]); setPromptCollectionOpen(false); }} className="text-text-secondary hover:text-danger transition-colors text-[9px]">清空全部</button>
                                        )}
                                      </div>
                                      {savedPrompts.length === 0 ? (
                                        <div className="px-4 py-6 text-center text-xs text-text-secondary">
                                          暂无收藏的提示词，点击 <Star className="w-3 h-3 inline text-text-secondary" /> 按钮收藏
                                        </div>
                                      ) : (
                                        savedPrompts.map((sp, i) => (
                                          <button
                                            key={i}
                                            onClick={() => { setVal(sp); setPromptCollectionOpen(false); }}
                                            className="w-full text-left px-4 py-2.5 text-xs text-text-primary hover:bg-bg-input hover:text-accent transition-colors flex items-start justify-between group/item border-b border-border-main/20 last:border-0"
                                          >
                                            <span className="line-clamp-2 flex-1 mr-2 leading-relaxed">{sp}</span>
                                            <button
                                              onClick={(e) => { e.stopPropagation(); toggleSavePrompt(sp); }}
                                              className="p-0.5 rounded text-text-secondary hover:text-danger transition-colors flex-shrink-0 mt-0.5 opacity-0 group-hover/item:opacity-100"
                                              title="取消收藏"
                                            >
                                              <XCircle className="w-3 h-3" />
                                            </button>
                                          </button>
                                        ))
                                      )}
                                    </div>
                                  )}
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })()
                    ) : null}
                  </React.Fragment>
                );
              });
            })()}
          </div>
          {showImageUpload && (
            <div className="space-y-4">
              <label className="block text-[11px] font-mono uppercase text-text-secondary mb-2 font-semibold">媒体源节点</label>
              <div className={`grid gap-3 ${imageFields.length <= 2 ? 'grid-cols-2' : imageFields.length === 3 ? 'grid-cols-3' : 'grid-cols-2'}`}>
                {imageFields.map((field, idx) => {
                  const upload = imageUploads[field.name];
                  const preview = upload?.preview;
                  const uploadSlotLabel = field.label || (idx === 0 ? '上传基础媒体' : idx === 1 ? '上传目标素材' : `上传图片 ${idx + 1}`);
                  return (
                    <div key={field.name}
                      className="flex-1 border-2 border-dashed border-border-main hover:border-accent/50 rounded-lg bg-bg-input/50 p-4 flex flex-col items-center text-center justify-center text-text-secondary hover:text-text-primary transition-colors cursor-pointer group will-change-transform"
                      onClick={() => uploadInputRefs.current[field.name]?.click()}
                      onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f?.type.startsWith("image/") || f?.type.startsWith("video/")) handleImageUpload(field.name, f); }}
                      onDragOver={(e) => e.preventDefault()}
                    >
                      {preview ? (
                        <div className="relative w-full">
                          <img src={preview} alt="" className="w-full h-24 object-cover rounded-md mb-2" />
                          <button className="absolute top-1 right-1 p-1 bg-black/60 rounded text-white hover:text-danger transition-colors"
                            onClick={(e) => { e.stopPropagation(); handleImageRemove(field.name); }}>
                            <Trash2 className="w-3 h-3" />
                          </button>
                          <span className="text-[10px] font-mono tracking-widest uppercase opacity-70">PNG / JPG</span>
                        </div>
                      ) : (<>
                        <UploadCloud className="w-8 h-8 mb-2 group-hover:scale-110 transition-transform group-hover:text-accent" />
                        <span className="text-[12px] font-medium leading-tight">{uploadSlotLabel}</span>
                        <span className="text-[10px] mt-1 font-mono tracking-widest uppercase">PNG / JPG</span>
                      </>)}
                      <input
                        ref={el => { uploadInputRefs.current[field.name] = el; }}
                        type="file" accept="image/*,video/*"
                        className="hidden"
                        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleImageUpload(field.name, f); }}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
        <div className="p-5 border-t border-border-main/80 bg-bg-base/30 space-y-3 sticky bottom-0 backdrop-blur-md">
          <button onClick={handleGenerate} disabled={generating}
            className="w-full flex items-center justify-center gap-2 bg-accent hover:opacity-90 text-accent-text font-bold py-3.5 px-4 rounded-md transition-all glow-accent active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {generating ? <RefreshCw className="w-5 h-5 animate-spin" /> : <Play className="w-5 h-5 fill-current" />}
            {generating ? "生成中.." : "开始生成"}
          </button>
          <div className="flex gap-2">
            <button onClick={handleBatchGenerate} disabled={generating}
              className="flex-1 flex items-center justify-center gap-2 bg-bg-input hover:brightness-110 border border-border-main text-text-primary font-medium py-2.5 px-4 rounded-md transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Layers className="w-4 h-4" />
              批量生成
            </button>
            <div className="relative" ref={batchSettingsRef}>
              <button onClick={() => setBatchSettingsOpen(!batchSettingsOpen)}
                className="p-2.5 bg-bg-input hover:brightness-110 border border-border-main text-text-secondary hover:text-text-primary rounded-md transition-all"
                title="批量设置"
              >
                <Settings2 className="w-4 h-4" />
              </button>
              {batchSettingsOpen && (
                <div className="absolute bottom-full right-0 mb-2 w-48 bg-bg-panel border border-border-main rounded-lg shadow-xl py-3 px-4 z-50">
                  <div className="text-[10px] font-mono text-text-secondary tracking-wider mb-3 uppercase">批量数量</div>
                  <div className="flex items-center gap-2">
                    <button onClick={() => setBatchCount(Math.max(1, batchCount - 1))}
                      className="p-1.5 bg-bg-input hover:bg-bg-panel border border-border-main rounded transition-colors text-text-secondary hover:text-text-primary">
                      <Minus className="w-3.5 h-3.5" />
                    </button>
                    <input type="number" min={1} max={50} value={batchCount}
                      onChange={(e) => setBatchCount(Math.max(1, Math.min(50, Number(e.target.value) || 1)))}
                      className="flex-1 text-center bg-bg-input border border-border-main rounded-md py-1.5 text-sm font-mono text-text-primary outline-none focus:border-accent/50 transition-colors" />
                    <button onClick={() => setBatchCount(Math.min(50, batchCount + 1))}
                      className="p-1.5 bg-bg-input hover:bg-bg-panel border border-border-main rounded transition-colors text-text-secondary hover:text-text-primary">
                      <Plus className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <div className="text-[10px] text-text-secondary mt-2 text-center font-mono">共 {batchCount} 组任务</div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
      {/* Right Panel */}
      <div className="flex-1 flex flex-col min-w-0 bg-bg-panel/50">
        <div className="h-14 lg:h-16 border-b border-border-main/60 flex items-center justify-between px-4 lg:px-6 shrink-0 bg-bg-base/80 backdrop-blur sticky top-0 z-10">
          <div className="flex space-x-6 overflow-x-auto custom-scrollbar no-scrollbar items-center">
            <div className="flex items-center gap-2 text-[11px] font-mono whitespace-nowrap">
              <Cpu className="w-4 h-4 text-text-secondary" />
              <span className="text-text-secondary hidden sm:inline">显卡:</span>
              <span className="text-accent font-bold">{gpuUsage}%</span>
              <div className="hidden md:block w-20 h-1.5 bg-bg-input rounded overflow-hidden ml-1 border border-border-main">
                <div className="h-full bg-accent relative" style={{width: gpuUsage + "%"}}>
                  <div className="absolute inset-0 bg-white/20 w-1/2 -skew-x-12 translate-x-32 animate-pulse"></div>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 text-[11px] font-mono whitespace-nowrap">
              <span className="text-text-secondary hidden sm:inline">显存:</span>
              <span className="text-accent font-bold brightness-110">0/24 GB</span>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0 ml-4">
            <button onClick={() => setHistoryOpen(true)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 text-[11px] font-mono bg-bg-input/40 hover:bg-bg-input border border-border-main/60 hover:border-accent/40 rounded text-text-secondary hover:text-text-primary transition-all"
              title="历史记录"
            >
              <History className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">历史</span>
            </button>
            {result?.url && (
              <div className="flex items-center gap-1 text-[10px] font-mono" title={assetSaved ? "已保存到资产库" : "资产保存中..."}>
                {assetSaved
                  ? <CheckCircle2 className="w-3 h-3 text-green-400" />
                  : <RefreshCw className="w-3 h-3 animate-spin text-text-secondary" />
                }
                <span className={assetSaved ? "text-green-400" : "text-text-secondary"}>{assetSaved ? "已存资产" : "保存中"}</span>
              </div>
            )}
            <div className={"flex items-center gap-2 py-1.5 px-3 border rounded-full " + (wsConnected ? "bg-accent/10 border-accent/20" : "bg-bg-input/50 border-border-main/50")}>
              <span className="relative flex h-2 w-2">
                <span className={"animate-ping absolute inline-flex h-full w-full rounded-full " + (wsConnected ? "bg-accent opacity-75" : "bg-text-secondary")}></span>
                <span className={"relative inline-flex rounded-full h-2 w-2 " + (wsConnected ? "bg-accent" : "bg-text-secondary")}></span>
              </span>
              <span className={"text-[10px] font-mono font-bold tracking-widest hidden sm:inline " + (wsConnected ? "text-accent" : "text-text-secondary")}>
                {wsConnected ? "节点运行中" : "连接中..."}
              </span>
            </div>
          </div>
        </div>
        <div className="flex-1 p-4 lg:p-8 flex flex-col items-center justify-center relative overflow-y-auto custom-scrollbar bg-grid-pattern gap-3">
          <div className="max-w-4xl w-full aspect-square sm:aspect-[4/3] md:aspect-video lg:aspect-auto lg:h-[75%] bg-bg-base/80 border border-border-main/80 rounded-lg shadow-2xl flex flex-col items-center justify-center text-text-secondary relative overflow-visible group transition-all duration-500 backdrop-blur-sm">
            {result?.url ? (
              <img src={result.url} alt="output" className="w-full h-full object-contain rounded-lg" />
            ) : error ? (
              <div className="text-center">
                <XCircle className="w-16 h-16 mb-4 text-danger opacity-40" />
                <span className="font-mono text-xs tracking-widest text-danger uppercase">生成失败</span>
                <p className="text-[11px] mt-2 font-mono opacity-70 max-w-xs">{error}</p>
              </div>
            ) : generating ? (
              <div className="text-center">
                <RefreshCw className="w-16 h-16 mb-4 animate-spin text-accent opacity-40" />
                <span className="font-mono text-xs tracking-widest opacity-40 uppercase">生成中..</span>
              </div>
            ) : (
              <>
                <ImageIcon className="w-16 h-16 mb-4 opacity-20 group-hover:scale-110 transition-transform duration-500" />
                <span className="font-mono text-xs tracking-widest opacity-40 uppercase">视口输出通道</span>
              </>
            )}
            {/* 批量结果左右切换箭头 */}
            {batchResults.length > 1 && result?.url && (
              <>
                <button
                  onClick={() => switchBatchImage(selectedBatchIndex - 1)}
                  disabled={selectedBatchIndex === 0}
                  className="absolute left-3 top-1/2 -translate-y-1/2 p-2 bg-black/60 hover:bg-black border border-white/10 rounded-md backdrop-blur text-white transition-all hover:scale-110 active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed z-10"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <button
                  onClick={() => switchBatchImage(selectedBatchIndex + 1)}
                  disabled={selectedBatchIndex >= batchResults.length - 1}
                  className="absolute right-3 top-1/2 -translate-y-1/2 p-2 bg-black/60 hover:bg-black border border-white/10 rounded-md backdrop-blur text-white transition-all hover:scale-110 active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed z-10"
                >
                  <ChevronRight className="w-5 h-5" />
                </button>
                {/* 缩略图索引指示器 */}
                <div className="absolute bottom-3 left-1/2 -translate-x-1/2 bg-black/60 backdrop-blur rounded-full px-3 py-1 text-xs font-mono text-white z-10">
                  {selectedBatchIndex + 1} / {batchResults.length}
                </div>
              </>
            )}
            <div className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity flex gap-2">
              {result?.url && (
                <>
                  <a href={result.url} target="_blank" rel="noopener noreferrer" className="p-2.5 bg-black/60 hover:bg-black border border-white/10 rounded-md backdrop-blur text-white transition-all hover:scale-105 active:scale-95" title="放大预览">
                    <Maximize2 className="w-4 h-4" />
                  </a>
                  <a href={result.url} download className="p-2.5 bg-black/60 hover:bg-black border border-white/10 rounded-md backdrop-blur text-white transition-all hover:text-accent hover:border-accent/50 hover:scale-105 active:scale-95" title="下载结果">
                    <Download className="w-4 h-4" />
                  </a>
                </>
              )}
              <div className="relative" ref={menuRef}>
                <button onClick={() => setShowSendMenu(!showSendMenu)}
                  className={"p-2.5 bg-black/60 hover:bg-black border border-white/10 rounded-md backdrop-blur text-white transition-all hover:scale-105 active:scale-95 " + (showSendMenu ? "border-accent text-accent" : "")}
                  title="发送到其他工作流"
                >
                  <Share2 className="w-4 h-4" />
                </button>
                {showSendMenu && (
                  <div className="absolute top-full right-0 mt-2 w-48 bg-bg-panel border border-border-main rounded-md shadow-xl py-1 z-50">
                    <div className="px-3 py-2 text-[10px] text-text-secondary border-b border-border-main/50 font-mono tracking-wider">直接设为原图</div>
                    {jumpOptions.map(opt => (
                      <button key={opt.id} onClick={() => { setShowSendMenu(false); onSendToWorkflow(opt.id as AppMode, result?.url); }}
                        className="w-full text-left px-4 py-2.5 text-xs text-text-primary hover:bg-bg-input hover:text-accent transition-colors flex items-center justify-between group/item"
                      >
                        {opt.label}
                        <UploadCloud className="w-3 h-3 opacity-0 group-hover/item:opacity-100 transition-opacity" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
        {/* 批量结果缩略图条 */}
        {batchResults.length > 1 && (
          <div className="shrink-0 border-t border-border-main/60 bg-bg-base/80 px-4 py-2.5">
            <div className="flex gap-2 overflow-x-auto custom-scrollbar items-center max-w-full">
              {batchResults.map((item, idx) => (
                <button
                  key={item.prompt_id || idx}
                  onClick={() => switchBatchImage(idx)}
                  className={"flex-shrink-0 w-16 h-16 rounded-md overflow-hidden border-2 transition-all hover:scale-105 active:scale-95 " + (idx === selectedBatchIndex ? "border-accent shadow-[0_0_8px_var(--theme-accent)]" : "border-transparent hover:border-border-main")}
                >
                  <img src={item.url} alt={"结果 " + (idx + 1)} className="w-full h-full object-cover" loading="lazy" />
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="border-t border-border-main/80 bg-bg-base flex flex-col shrink-0 relative z-20 shadow-[0_-10px_30px_rgba(0,0,0,0.5)]" style={{ minHeight: "11rem" }}>
          <div className="py-2.5 px-6 border-b border-border-main/50 flex justify-between items-center bg-bg-panel/80">
            <span className="text-[10px] font-mono text-text-secondary uppercase tracking-widest flex items-center gap-2 font-semibold">
              <Dna className="w-3.5 h-3.5 text-text-secondary" />
              执行轨迹
            </span>
            <span className="text-[10px] font-mono text-accent font-bold bg-accent/10 px-2 py-0.5 rounded">
              {generating ? progressStep + "/" + (progressTotal || params.steps || 30) + " 步" : "就绪"}
            </span>
          </div>
          {/* 节点进度列表 */}
          {generating && Object.keys(nodeProgress).length > 0 && (
            <div className="px-6 py-2 border-b border-border-main/30 bg-bg-panel/30 max-h-24 overflow-y-auto custom-scrollbar">
              <div className="flex flex-wrap gap-2">
                {(Object.entries(nodeProgress) as [string, {name: string; state: string; value: number; max: number}][]).map(([nid, info]) => (
                  <div key={nid} className="flex items-center gap-1.5 text-[10px] font-mono bg-bg-input/60 border border-border-main/40 rounded px-2 py-1">
                    <span className={info.state === "completed" ? "text-green-400" : "text-accent"}>
                      {info.state === "completed" ? <CheckCircle2 className="w-3 h-3" /> : <RefreshCw className="w-3 h-3 animate-spin" />}
                    </span>
                    <span className="text-text-secondary max-w-[120px] truncate">{info.name}</span>
                    <span className="text-text-primary tabular-nums">{info.value}/{info.max}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="p-4 lg:px-8 flex-1 flex flex-col justify-center">
            <div className="max-w-4xl w-full mx-auto space-y-3.5 relative">
              <div className="flex justify-between items-end">
                <div className="font-mono text-[13px]">
                  <span className={generating ? "text-accent flex items-center gap-2 drop-shadow-[0_0_5px_var(--theme-accent)]" : "text-text-secondary"}>
                    {generating && <RefreshCw className="w-4 h-4 animate-spin text-accent" />}
                    <span className="font-semibold tracking-wide">{statusText || "等待操作..."}</span>
                  </span>
                </div>
                <span className="text-xs font-mono text-text-secondary tracking-wider">
                  {generating ? "第" + progressStep + "/" + (progressTotal || params.steps || 30) + "步 (" + Math.round(progress) + "%)" : ""}
                </span>
              </div>
              <div className="w-full h-2 bg-bg-input border border-border-main rounded-full overflow-hidden relative shadow-inner">
                <div className="h-full bg-accent shadow-[0_0_12px_var(--theme-accent)] relative rounded-full transition-all duration-1000"
                  style={{ width: progress + "%" }}>
                  <div className="absolute inset-0 bg-white/20 w-1/2 -skew-x-12 translate-x-[200%] animate-[shimmer_2s_infinite]"></div>
                </div>
              </div>
              <div className="font-mono text-[11px] text-text-secondary truncate flex items-center gap-2">
                <span className="opacity-50">&gt;</span>
                {statusText || "等待操作..."}
                {queuedJobs.length > 0 && <span className="text-accent/80 ml-2">[{queuedJobs.length} tasks]</span>}
              </div>
          </div>
        </div>
      </div>
    </div>
    </div>
      {/* 历史记录面板 */}
      {historyOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setHistoryOpen(false)} />
          <div ref={historyRef} className="relative w-96 max-w-[90vw] h-full bg-bg-panel border-l border-border-main shadow-2xl flex flex-col z-10 animate-[slideInRight_0.2s_ease-out]">
            <div className="h-14 border-b border-border-main flex items-center justify-between px-5 shrink-0">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                <History className="w-4 h-4 text-accent" />
                生成历史
              </h3>
              <div className="flex items-center gap-2">
                {generationHistory.length > 0 && (
                  <button
                    onClick={() => { setGenerationHistory([]); localStorage.removeItem("ws_history"); }}
                    className="text-[10px] font-mono text-text-secondary hover:text-danger transition-colors px-2 py-1 rounded hover:bg-danger/10"
                  >
                    清空
                  </button>
                )}
                <button onClick={() => setHistoryOpen(false)} className="p-1.5 hover:bg-bg-input rounded text-text-secondary hover:text-text-primary transition-colors">
                  <XCircle className="w-4 h-4" />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-2">
              {generationHistory.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-text-secondary gap-3">
                  <ImageIcon className="w-10 h-10 opacity-30" />
                  <span className="text-xs font-mono tracking-widest">暂无生成记录</span>
                </div>
              ) : (
                generationHistory.map((entry, idx) => (
                  <button
                    key={idx}
                    onClick={() => { setResult({ url: entry.url }); setHistoryOpen(false); }}
                    className="w-full text-left bg-bg-base/60 hover:bg-bg-input border border-border-main/60 hover:border-accent/30 rounded-lg p-3 transition-all group"
                  >
                    <div className="flex gap-3">
                      <div className="w-16 h-16 rounded-md bg-bg-input overflow-hidden flex-shrink-0 border border-border-main/50">
                        <img src={entry.url} alt="" className="w-full h-full object-cover" loading="lazy" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-accent/10 text-accent">{modeNameMap[entry.mode] || entry.mode}</span>
                          <span className="text-[10px] text-text-secondary font-mono">{new Date(entry.time).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                        </div>
                        <p className="text-xs text-text-secondary truncate font-mono leading-relaxed">{entry.prompt}</p>
                      </div>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
        </div>
      )}
      <style>{`@keyframes slideInRight { from { transform: translateX(100%); } to { transform: translateX(0); } }`}</style>
    </>

  );
}
