"use client";

import localforage from "localforage";

import type { ImageResponse } from "@/lib/api";

type ApiEnvelope<T> = {
  code?: number;
  message?: string;
  data?: T;
};

type Paginated<T> = {
  items: T[];
};

type Sub2APIKey = {
  id: number;
  key: string;
  name: string;
  group_id?: number | null;
  status?: string;
};

type Sub2APIProfile = {
  id?: number;
  balance?: number;
};

export type Sub2APIEmbeddedConfig = {
  baseUrl: string;
  apiBaseUrl: string;
  token: string;
  userId: string;
  groupId?: number;
};

const EMBEDDED_KEY_NAME = "chatgpt2api-web";

const embeddedStorage = localforage.createInstance({
  name: "chatgpt2api",
  storeName: "sub2api_embedded",
});

function normalizeOrigin(raw: string) {
  const trimmed = raw.trim().replace(/\/$/, "");
  if (!trimmed) return "";
  try {
    return new URL(trimmed).origin;
  } catch {
    return "";
  }
}

function unwrapSub2APIResponse<T>(raw: unknown): T {
  if (raw && typeof raw === "object" && "code" in raw) {
    const envelope = raw as ApiEnvelope<T>;
    if (envelope.code !== 0) {
      throw new Error(envelope.message || "Sub2API 请求失败");
    }
    return envelope.data as T;
  }
  return raw as T;
}

async function readJSONResponse<T>(response: Response): Promise<T> {
  const raw = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message =
      typeof raw === "object" && raw
        ? String((raw as { message?: unknown; error?: unknown; detail?: unknown }).message || (raw as { error?: unknown }).error || (raw as { detail?: unknown }).detail || "")
        : "";
    throw new Error(message || `Sub2API 请求失败 (${response.status})`);
  }
  return unwrapSub2APIResponse<T>(raw);
}

async function sub2apiJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const cfg = getSub2APIEmbeddedConfig();
  if (!cfg) {
    throw new Error("Sub2API 嵌入参数缺失");
  }
  const response = await fetch(`${cfg.apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${cfg.token}`,
      ...(init?.headers || {}),
    },
  });
  return readJSONResponse<T>(response);
}

function apiKeyCacheKey(cfg: Sub2APIEmbeddedConfig) {
  return `${cfg.baseUrl}:${cfg.userId || "unknown"}:${cfg.groupId || 0}`;
}

async function clearCachedSub2APIKey(cfg: Sub2APIEmbeddedConfig) {
  await embeddedStorage.removeItem(apiKeyCacheKey(cfg));
}

export function getSub2APIEmbeddedConfig(): Sub2APIEmbeddedConfig | null {
  if (typeof window === "undefined") return null;

  const params = new URLSearchParams(window.location.search);
  if (params.get("ui_mode") !== "embedded") return null;

  const token = String(params.get("token") || "").trim();
  const baseUrl =
    normalizeOrigin(String(params.get("sub2api_base") || "")) ||
    normalizeOrigin(String(params.get("src_host") || ""));
  if (!token || !baseUrl) return null;

  const rawGroupId = String(params.get("image_group_id") || params.get("group_id") || "").trim();
  const parsedGroupId = rawGroupId ? Number(rawGroupId) : 0;

  return {
    baseUrl,
    apiBaseUrl: `${baseUrl}/api/v1`,
    token,
    userId: String(params.get("user_id") || "").trim(),
    groupId: Number.isFinite(parsedGroupId) && parsedGroupId > 0 ? parsedGroupId : undefined,
  };
}

export function isSub2APIEmbedded() {
  return getSub2APIEmbeddedConfig() !== null;
}

export async function fetchSub2APIEmbeddedBalance() {
  const profile = await sub2apiJSON<Sub2APIProfile>("/user/profile");
  return profile.balance;
}

async function getOrCreateSub2APIKey(): Promise<string> {
  const cfg = getSub2APIEmbeddedConfig();
  if (!cfg) {
    throw new Error("Sub2API 嵌入参数缺失");
  }

  const cacheKey = apiKeyCacheKey(cfg);
  const cached = String((await embeddedStorage.getItem<string>(cacheKey)) || "").trim();
  if (cached) {
    return cached;
  }

  const existing = await sub2apiJSON<Paginated<Sub2APIKey>>(
    `/keys?page=1&page_size=100&search=${encodeURIComponent(EMBEDDED_KEY_NAME)}`,
  );
  const found = (existing.items || []).find(
    (item) =>
      item.name === EMBEDDED_KEY_NAME &&
      item.key &&
      item.status !== "inactive" &&
      (cfg.groupId ? item.group_id === cfg.groupId : true),
  );
  if (found?.key) {
    await embeddedStorage.setItem(cacheKey, found.key);
    return found.key;
  }

  const created = await sub2apiJSON<Sub2APIKey>("/keys", {
    method: "POST",
    body: JSON.stringify({
      name: EMBEDDED_KEY_NAME,
      ...(cfg.groupId ? { group_id: cfg.groupId } : {}),
    }),
  });
  if (!created.key) {
    throw new Error("Sub2API API Key 创建失败");
  }
  await embeddedStorage.setItem(cacheKey, created.key);
  return created.key;
}

async function callSub2APIGateway<T>(
  path: string,
  buildInit: (apiKey: string) => RequestInit,
  retry = true,
): Promise<T> {
  const cfg = getSub2APIEmbeddedConfig();
  if (!cfg) {
    throw new Error("Sub2API 嵌入参数缺失");
  }

  const apiKey = await getOrCreateSub2APIKey();
  const response = await fetch(`${cfg.baseUrl}${path}`, buildInit(apiKey));
  if ((response.status === 401 || response.status === 403) && retry) {
    await clearCachedSub2APIKey(cfg);
    return callSub2APIGateway(path, buildInit, false);
  }
  return readJSONResponse<T>(response);
}

export async function generateImageViaSub2API(prompt: string, model?: string, size?: string) {
  return callSub2APIGateway<ImageResponse>("/v1/images/generations", (apiKey) => ({
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      prompt,
      ...(model ? { model } : {}),
      ...(size ? { size } : {}),
      n: 1,
      response_format: "b64_json",
    }),
  }));
}

export async function editImageViaSub2API(files: File | File[], prompt: string, model?: string, size?: string) {
  const uploadFiles = Array.isArray(files) ? files : [files];
  return callSub2APIGateway<ImageResponse>("/v1/images/edits", (apiKey) => {
    const formData = new FormData();
    uploadFiles.forEach((file) => formData.append("image", file));
    formData.append("prompt", prompt);
    formData.append("n", "1");
    if (model) formData.append("model", model);
    if (size) formData.append("size", size);

    return {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
      },
      body: formData,
    };
  });
}
