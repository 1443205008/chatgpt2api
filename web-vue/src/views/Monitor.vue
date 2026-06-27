<template>
  <div class="space-y-6">
    <PagePanel class="space-y-5">
      <PanelHeader title="实时监控" align="start">
        <template #copy>
          <p class="mt-1 text-xs text-muted-foreground">
            容器内存实时窗口，不做历史时间范围；用于观察等待入口、等待账号、等待出口、上游生成、上游断流和本地拒绝/繁忙。
          </p>
          <p class="mt-1 text-xs text-muted-foreground">
            入口排队高时可适当调大环境变量 CHATGPT2API_THREAD_TOKENS 提高本地并发；最近更新：{{ monitorData?.updated_at || '未获取' }}
          </p>
        </template>
        <template #actions>
          <StateBadge :tone="autoRefresh ? 'success' : 'muted'" shape="rounded">
            {{ autoRefresh ? '自动刷新' : '已暂停' }}
          </StateBadge>
          <label class="flex items-center gap-2 text-xs text-muted-foreground">
            <span class="whitespace-nowrap">间隔</span>
            <Input
              :model-value="String(refreshIntervalSeconds)"
              type="number"
              min="1"
              max="300"
              step="1"
              root-class="w-16"
              @update:model-value="setRefreshIntervalInput"
              @blur="applyRefreshInterval()"
              @change="applyRefreshInterval()"
              @keyup.enter="applyRefreshInterval()"
            />
            <span class="whitespace-nowrap">秒</span>
          </label>
          <Button size="sm" variant="outline" :disabled="isLoading" @click="loadMonitor(false)">
            {{ isLoading ? '刷新中...' : '立即刷新' }}
          </Button>
          <Button size="sm" variant="outline" @click="toggleAutoRefresh">
            {{ autoRefresh ? '暂停刷新' : '继续刷新' }}
          </Button>
        </template>
      </PanelHeader>

      <div class="grid gap-3 xl:grid-cols-2">
        <div
          v-for="group in diagnosticGroups"
          :key="group.key"
          class="monitor-metric-group"
        >
          <div class="flex items-center justify-between gap-3">
            <p class="text-sm font-semibold text-foreground">{{ group.title }}</p>
            <p class="text-xs text-muted-foreground">{{ group.meta }}</p>
          </div>
          <div class="mt-3 grid gap-2 sm:grid-cols-2 2xl:grid-cols-4">
            <div
              v-for="item in group.items"
              :key="`${group.key}-${item.key}`"
              class="monitor-metric-cell"
            >
              <p class="truncate text-xs text-muted-foreground">{{ item.label }}</p>
              <p
                class="mt-1 text-base font-semibold leading-none tabular-nums"
                :class="item.value === '-' ? 'text-muted-foreground' : item.valueClass"
              >
                {{ item.value }}
              </p>
              <p v-if="item.meta" class="mt-1 truncate text-[11px] text-muted-foreground">
                {{ item.meta }}
              </p>
            </div>
          </div>
        </div>
      </div>

      <StateBlock
        v-if="loadError"
        compact
        dashed
        title="实时监控加载失败"
        :description="loadError"
      />
    </PagePanel>

    <PagePanel flush>
      <div class="p-4">
        <PanelHeader title="活跃请求" align="start">
          <template #copy>
            <p class="mt-1 text-xs text-muted-foreground">
              正在运行的图片请求，按进入时间排序。
            </p>
          </template>
          <template #actions>
            <MetaChip size="xs" tone="info">当前并发 {{ activeRows.length }} / {{ threadTokens }}</MetaChip>
            <MetaChip size="xs" tone="muted">入口排队 {{ entryQueueText }}</MetaChip>
          </template>
        </PanelHeader>
      </div>
      <div v-if="activeStageItems.length" class="flex flex-wrap gap-2 px-4 pb-3">
        <MetaChip
          v-for="item in activeStageItems"
          :key="item.label"
          size="xs"
          tone="muted"
        >
          {{ item.label }} {{ item.count }}
        </MetaChip>
      </div>
      <TableShell v-if="activeRows.length">
        <table class="monitor-table">
          <thead>
            <tr>
              <th>请求</th>
              <th>模型</th>
              <th>阶段</th>
              <th>已耗时</th>
              <th>关键耗时</th>
              <th>出口</th>
              <th>账号</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in activeRows" :key="row.call_id">
              <td>
                <p class="font-mono text-xs text-foreground">{{ shortCallId(row.call_id) }}</p>
                <p class="mt-1 text-[11px] text-muted-foreground">{{ row.endpoint || '-' }}</p>
              </td>
              <td>
                <MetaChip size="xs" tone="muted">{{ row.model || '-' }}</MetaChip>
              </td>
              <td>
                <StateBadge tone="info" shape="rounded" :bordered="false">
                  {{ row.stage_label || row.stage || '运行中' }}
                </StateBadge>
              </td>
              <td>{{ formatMs(row.elapsed_ms) }}</td>
              <td>{{ metricDigest(row) }}</td>
              <td>
                <MetaChip size="xs" tone="muted">{{ egressText(row) }}</MetaChip>
              </td>
              <td class="max-w-[12rem] truncate">{{ row.account_email || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </TableShell>
      <div v-else class="px-4 pb-4">
        <StateBlock compact dashed title="暂无活跃请求" description="开始压测或发起图片请求后，这里会实时出现运行中的调用。" />
      </div>
    </PagePanel>

    <div class="grid items-stretch gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(22rem,0.72fr)]">
      <PagePanel flush class="monitor-paired-panel">
        <div class="monitor-paired-header">
          <div class="monitor-paired-header__copy">
            <p class="ui-section-title">最近完成</p>
            <p class="monitor-paired-header__desc">
              最近完成的图片相关调用，窗口保存在进程内存中。
            </p>
          </div>
          <div class="monitor-paired-header__meta">
            <MetaChip size="xs" tone="muted">{{ completedWindowText }}</MetaChip>
          </div>
        </div>
        <div v-if="recentRows.length" class="monitor-paired-body">
          <TableShell>
            <table class="monitor-table">
              <thead>
                <tr>
                  <th>请求</th>
                  <th>状态</th>
                  <th>模型</th>
                  <th>总耗时</th>
                  <th>入口等待</th>
                  <th>账号 / 出口</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in recentRows" :key="`recent-${row.call_id}-${row.ended_at}`">
                  <td>
                    <p class="font-mono text-xs text-foreground">{{ shortCallId(row.call_id) }}</p>
                    <p class="mt-1 text-[11px] text-muted-foreground">{{ row.ended_at || row.updated_at || '-' }}</p>
                  </td>
                  <td>
                    <StateBadge :tone="statusTone(row.status)" shape="rounded" :bordered="false">
                      {{ statusLabel(row.status) }}
                    </StateBadge>
                  </td>
                  <td class="max-w-[12rem] truncate">{{ row.model || '-' }}</td>
                  <td>{{ formatMs(row.duration_ms) }}</td>
                  <td>{{ formatMs(metricValue(row, 'handler_queue_ms')) }}</td>
                  <td>{{ accountEgressDigest(row) }}</td>
                </tr>
              </tbody>
            </table>
          </TableShell>
        </div>
        <div v-else class="monitor-paired-body px-4 pb-4">
          <StateBlock compact dashed title="暂无完成记录" description="当前容器启动后还没有图片相关请求完成。" />
        </div>
      </PagePanel>

      <PagePanel flush class="monitor-paired-panel">
        <div class="monitor-paired-header">
          <div class="monitor-paired-header__copy">
            <p class="ui-section-title">慢请求</p>
            <p class="monitor-paired-header__desc">
              按等待入口、等待账号、等待出口、上游生成和上游断流综合排序。
            </p>
          </div>
          <div class="monitor-paired-header__meta">
            <MetaChip size="xs" tone="muted">慢 {{ slowRows.length }}</MetaChip>
          </div>
        </div>
        <div v-if="slowRows.length" class="monitor-paired-body space-y-2 px-4 pb-4">
          <div
            v-for="row in slowRows"
            :key="`slow-${row.call_id}-${row.ended_at}`"
            class="rounded-2xl border border-border bg-background px-3 py-3"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="truncate text-sm font-medium text-foreground">
                  {{ row.model || '-' }}
                  <span class="font-mono text-xs text-muted-foreground">{{ shortCallId(row.call_id) }}</span>
                </p>
                <p class="mt-1 text-xs text-muted-foreground">{{ row.endpoint || '-' }}</p>
              </div>
              <StateBadge :tone="statusTone(row.status)" size="xs" shape="rounded" :bordered="false">
                {{ formatMs(row.duration_ms) }}
              </StateBadge>
            </div>
            <div class="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
              <span
                v-for="item in slowMetricItems(row)"
                :key="`${row.call_id}-${item.key}`"
                class="rounded-xl px-2 py-1"
                :class="item.important ? 'bg-primary/10 text-primary' : 'bg-muted/60'"
              >
                {{ item.label }} {{ item.value }}
              </span>
            </div>
            <p v-if="slowRowReason(row)" class="mt-2 text-xs text-muted-foreground">
              {{ slowRowReason(row) }}
            </p>
            <p v-if="row.error" class="mt-2 line-clamp-2 text-xs text-muted-foreground">
              {{ row.error }}
            </p>
          </div>
        </div>
        <div v-else class="monitor-paired-body px-4 pb-4">
          <StateBlock compact dashed title="暂无慢请求" description="窗口内没有可排序的完成请求。" />
        </div>
      </PagePanel>
    </div>

    <PagePanel flush>
      <div class="p-4">
        <PanelHeader title="阶段事件" align="start">
          <template #copy>
            <p class="mt-1 text-xs text-muted-foreground">
              最近阶段变化，辅助观察请求是否集中卡在同一环节。
            </p>
          </template>
        </PanelHeader>
      </div>
      <TableShell v-if="eventRows.length">
        <table class="monitor-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>请求</th>
              <th>模型</th>
              <th>阶段</th>
              <th>耗时</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in eventRows" :key="`${row.call_id}-${row.event}-${index}`">
              <td>{{ row.time || '-' }}</td>
              <td class="font-mono text-xs">{{ shortCallId(row.call_id) }}</td>
              <td class="max-w-[14rem] truncate">{{ row.model || '-' }}</td>
              <td>{{ row.label || row.event }}</td>
              <td>{{ eventMetricText(row) }}</td>
            </tr>
          </tbody>
        </table>
      </TableShell>
      <div v-else class="px-4 pb-4">
        <StateBlock compact dashed title="暂无阶段事件" description="有图片请求进入后会开始记录。" />
      </div>
    </PagePanel>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Button, Input } from 'nanocat-ui'
import { monitorApi, type RealtimeMonitorEvent, type RealtimeMonitorRecord, type RealtimeMonitorResponse } from '@/api/monitor'
import { MetaChip, PagePanel, PanelHeader, StateBadge, StateBlock, TableShell } from '@/components/ai'

type BadgeTone = 'success' | 'danger' | 'warning' | 'info' | 'muted'

const monitorData = ref<RealtimeMonitorResponse | null>(null)
const isLoading = ref(false)
const loadError = ref('')
const autoRefresh = ref(true)
const REFRESH_INTERVAL_STORAGE_KEY = 'chatgpt2api_monitor_refresh_interval_secs'
const DEFAULT_REFRESH_INTERVAL_SECONDS = 5
const MIN_REFRESH_INTERVAL_SECONDS = 1
const MAX_REFRESH_INTERVAL_SECONDS = 300
const refreshIntervalSeconds = ref(readStoredRefreshInterval())
let refreshTimer: number | undefined
let refreshRunId = 0

const summary = computed(() => monitorData.value?.summary)
const activeRows = computed(() => monitorData.value?.active || [])
const recentRows = computed(() => monitorData.value?.recent.slice(0, 20) || [])
const slowRows = computed(() => monitorData.value?.slow.slice(0, 8) || [])
const eventRows = computed(() => monitorData.value?.events.slice(0, 30) || [])
const threadTokens = computed(() => monitorData.value?.threadpool?.tokens || '-')
const completedWindowText = computed(() => {
  const windowInfo = monitorData.value?.window
  if (!windowInfo) return '窗口 0 / 0'
  return `窗口 ${windowInfo.completed} / ${windowInfo.completed_capacity}`
})
const activeStageItems = computed(() =>
  Object.entries(summary.value?.active_by_stage || {})
    .filter(([, count]) => Number(count) > 0)
    .slice(0, 8)
    .map(([label, count]) => ({ label, count: Number(count) })),
)

const entryQueueMetricKeys = ['handler_queue_ms', 'stream_first_queue_ms'] as const
const entryAccountMetricKeys = ['handler_queue_ms', 'stream_first_queue_ms', 'account_wait_ms', 'egress_wait_ms'] as const
const entryQueueP95 = computed(() => maxMetricFromMap(summary.value?.metric_p95 || {}, entryQueueMetricKeys))
const entryQueueText = computed(() => formatMs(entryQueueP95.value))

const diagnosticGroups = computed(() => {
  const data = summary.value
  const p95 = summary.value?.metric_p95 || {}
  const bottleneckValue = Number(data?.bottleneck?.value_ms || 0)
  const localBusy = summary.value?.slow_counts?.local_reject_or_busy ?? 0
  const entryAccountTotal = sumMetricFromMap(p95, entryAccountMetricKeys)
  const httpConnectTotal = sumMetricFromMap(p95, ['http_dns_ms', 'http_tcp_ms', 'http_tls_ms'])
  return [
    {
      key: 'overview',
      title: '实时概览',
      meta: '窗口、成功率、瓶颈',
      items: [
        { key: 'active', label: '当前并发', value: data?.active ?? 0, meta: `线程容量 ${threadTokens.value}`, valueClass: 'text-foreground' },
        { key: 'completed', label: '完成窗口', value: data?.completed ?? 0, meta: completedWindowText.value, valueClass: 'text-foreground' },
        { key: 'success', label: '成功率', value: `${data?.success_rate ?? 0}%`, meta: `成功 ${data?.success ?? 0}`, valueClass: 'text-emerald-600 dark:text-emerald-400' },
        { key: 'failed', label: '失败数', value: data?.failed ?? 0, meta: '窗口内失败', valueClass: Number(data?.failed || 0) > 0 ? 'text-rose-600 dark:text-rose-400' : 'text-foreground' },
        { key: 'average', label: '平均耗时', value: formatMs(data?.avg_duration_ms), meta: '窗口均值', valueClass: 'text-sky-600 dark:text-sky-400' },
        { key: 'p95', label: 'P95 耗时', value: formatMs(data?.p95_duration_ms), meta: '慢请求参考', valueClass: 'text-sky-600 dark:text-sky-400' },
        { key: 'bottleneck', label: '当前瓶颈', value: data?.bottleneck?.label || '-', meta: 'P95 最大阶段', valueClass: 'text-foreground' },
        { key: 'bottleneck_ms', label: '瓶颈耗时', value: formatMs(bottleneckValue), meta: '阶段 P95', valueClass: 'text-foreground' },
      ],
    },
    {
      key: 'account',
      title: '入口、账号与出口',
      meta: '本地线程、账号池、代理出口',
      items: [
        { key: 'handler_queue_ms', label: '入口排队', value: formatMs(p95.handler_queue_ms), meta: '等待后端线程', valueClass: 'text-sky-600 dark:text-sky-400' },
        { key: 'stream_first_queue_ms', label: '首包排队', value: formatMs(p95.stream_first_queue_ms), meta: '等待流式首包', valueClass: 'text-sky-600 dark:text-sky-400' },
        { key: 'account_wait_ms', label: '账号等待', value: formatMs(p95.account_wait_ms), meta: '账号池筛选', valueClass: 'text-cyan-600 dark:text-cyan-400' },
        { key: 'egress_wait_ms', label: '出口等待', value: formatMs(p95.egress_wait_ms), meta: activeEgressMeta(), valueClass: 'text-teal-600 dark:text-teal-400' },
        { key: 'egress_acquire_ms', label: '出口租约', value: formatMs(p95.egress_acquire_ms), meta: '代理节点并发', valueClass: 'text-teal-600 dark:text-teal-400' },
        { key: 'entry_account_total_ms', label: '入口账号合计', value: formatMs(entryAccountTotal), meta: '入口 + 首包 + 账号 + 出口', valueClass: 'text-sky-600 dark:text-sky-400' },
        { key: 'entry_p95', label: '入口排队 P95', value: entryQueueText.value, meta: `线程容量 ${threadTokens.value} · 慢 ${data?.slow_counts?.handler_queue ?? 0}`, valueClass: 'text-sky-600 dark:text-sky-400' },
        { key: 'local_busy', label: '本地拒绝/繁忙', value: `${localBusy}`, meta: '无号 / 并发 / 策略', valueClass: 'text-foreground' },
      ],
    },
    {
      key: 'upstream_prepare',
      title: '上游准备与 HTTP',
      meta: '上传、令牌、建连、首包',
      items: [
        { key: 'upload_ms', label: '图片上传', value: formatMs(p95.upload_ms), meta: '参考图上传', valueClass: 'text-foreground' },
        { key: 'bootstrap_ms', label: '上游初始化', value: formatMs(p95.bootstrap_ms), meta: 'ChatGPT 会话', valueClass: 'text-foreground' },
        { key: 'requirements_ms', label: '令牌获取', value: formatMs(p95.requirements_ms), meta: 'requirements / token', valueClass: 'text-foreground' },
        { key: 'prepare_conversation_ms', label: '会话准备', value: formatMs(p95.prepare_conversation_ms), meta: '准备图片会话', valueClass: 'text-foreground' },
        { key: 'generation_start_ms', label: '启动生成', value: formatMs(p95.generation_start_ms), meta: '提交上游请求', valueClass: 'text-foreground' },
        { key: 'http_connect_ms', label: 'HTTP 建连', value: formatMs(httpConnectTotal), meta: 'DNS + TCP + TLS', valueClass: 'text-sky-600 dark:text-sky-400' },
        { key: 'http_wait_ms', label: 'HTTP 等待', value: formatMs(p95.http_wait_ms), meta: '发出请求到首包', valueClass: 'text-sky-600 dark:text-sky-400' },
        { key: 'http_ttfb_ms', label: 'HTTP 首包', value: formatMs(p95.http_ttfb_ms), meta: '请求开始到首包', valueClass: 'text-sky-600 dark:text-sky-400' },
      ],
    },
    {
      key: 'upstream_result',
      title: '生成与结果',
      meta: '流、轮询、下载',
      items: [
        { key: 'sse_first_event_ms', label: 'SSE 首事件', value: formatMs(p95.sse_first_event_ms), meta: '首个 data 事件', valueClass: 'text-indigo-600 dark:text-indigo-400' },
        { key: 'sse_max_gap_ms', label: 'SSE 最大空窗', value: formatMs(p95.sse_max_gap_ms), meta: '两次事件最大间隔', valueClass: 'text-indigo-600 dark:text-indigo-400' },
        { key: 'conversation_stream_ms', label: '上游生成', value: formatMs(p95.conversation_stream_ms), meta: '会话流响应', valueClass: 'text-emerald-600 dark:text-emerald-400' },
        { key: 'stream_error_ms', label: '上游断流', value: formatMs(p95.stream_error_ms), meta: 'HTTP2 / SSE', valueClass: 'text-slate-600 dark:text-slate-300' },
        { key: 'resolve_ms', label: '图片解析', value: formatMs(p95.resolve_ms), meta: 'conversation / file', valueClass: 'text-emerald-600 dark:text-emerald-400' },
        { key: 'download_ms', label: '图片下载', value: formatMs(p95.download_ms), meta: '下载并返回', valueClass: 'text-foreground' },
        { key: 'stream_ms', label: '单图内部', value: formatMs(p95.stream_ms), meta: '上游到结果', valueClass: 'text-foreground' },
        { key: 'total_ms', label: '单图总耗时', value: formatMs(p95.total_ms), meta: '完整链路', valueClass: 'text-foreground' },
      ],
    },
  ]
})

async function loadMonitor(silent = true, source: 'auto' | 'manual' = silent ? 'auto' : 'manual') {
  const autoRequest = source === 'auto'
  const runId = refreshRunId
  if (autoRequest && !autoRefresh.value) return
  if (isLoading.value && silent) return
  isLoading.value = true
  try {
    const data = await monitorApi.realtime()
    if (autoRequest && (!autoRefresh.value || runId !== refreshRunId)) return
    monitorData.value = data
    loadError.value = ''
  } catch (error: any) {
    if (autoRequest && (!autoRefresh.value || runId !== refreshRunId)) return
    loadError.value = error?.message || 'Request failed'
  } finally {
    isLoading.value = false
  }
}

function startPolling() {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = undefined
  }
  if (!autoRefresh.value) return
  refreshTimer = window.setInterval(() => {
    if (!autoRefresh.value) return
    void loadMonitor(true, 'auto')
  }, normalizedRefreshIntervalSeconds() * 1000)
}

function stopPolling() {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = undefined
  }
  refreshRunId += 1
}

function toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) {
    applyRefreshInterval(false)
    startPolling()
    void loadMonitor(true, 'auto')
  } else {
    stopPolling()
  }
}

function clampRefreshInterval(value: unknown) {
  const seconds = Math.round(Number(value || DEFAULT_REFRESH_INTERVAL_SECONDS))
  if (!Number.isFinite(seconds)) return DEFAULT_REFRESH_INTERVAL_SECONDS
  return Math.min(MAX_REFRESH_INTERVAL_SECONDS, Math.max(MIN_REFRESH_INTERVAL_SECONDS, seconds))
}

function readStoredRefreshInterval() {
  try {
    return clampRefreshInterval(window.localStorage.getItem(REFRESH_INTERVAL_STORAGE_KEY))
  } catch {
    return DEFAULT_REFRESH_INTERVAL_SECONDS
  }
}

function normalizedRefreshIntervalSeconds() {
  return clampRefreshInterval(refreshIntervalSeconds.value)
}

function setRefreshIntervalInput(value: unknown) {
  refreshIntervalSeconds.value = clampRefreshInterval(value)
}

function applyRefreshInterval(restart = true) {
  const nextValue = normalizedRefreshIntervalSeconds()
  refreshIntervalSeconds.value = nextValue
  try {
    window.localStorage.setItem(REFRESH_INTERVAL_STORAGE_KEY, String(nextValue))
  } catch {
    // ignore storage errors
  }
  if (restart && autoRefresh.value) {
    startPolling()
  }
}

function formatMs(value: unknown) {
  const ms = Number(value || 0)
  if (!Number.isFinite(ms) || ms <= 0) return '-'
  if (ms >= 60_000) return `${(ms / 60_000).toFixed(1)}m`
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms)}ms`
}

function shortCallId(value: unknown) {
  const text = String(value || '')
  return text ? text.slice(0, 8) : '-'
}

function maxMetricFromMap(map: Record<string, number> | undefined, keys: readonly string[]) {
  return keys.reduce((max, key) => Math.max(max, Number(map?.[key] || 0)), 0)
}

function sumMetricFromMap(map: Record<string, number> | undefined, keys: readonly string[]) {
  return keys.reduce((sum, key) => sum + Math.max(0, Number(map?.[key] || 0)), 0)
}

function metricValue(row: RealtimeMonitorRecord, key: string) {
  const perf = row.perf || {}
  const metrics = row.metrics || {}
  return Math.max(Number(perf[key] || 0), Number(metrics[key] || 0))
}

function proxySourceLabel(value: unknown) {
  const source = String(value || 'direct')
  if (source.includes('account_group')) return '账号组'
  if (source.includes('account')) return '账号'
  if (source.includes('default')) return '默认'
  if (source.includes('global')) return '默认'
  if (source.includes('runtime_resource')) return '资源代理'
  if (source.includes('runtime')) return 'Runtime'
  if (source.includes('explicit')) return '指定'
  if (source.includes('direct')) return '直连'
  return source
}

function egressLabelText(row: RealtimeMonitorRecord) {
  const value = String(row.egress_label || '').trim()
  const source = String(row.proxy_source || '').trim()
  if (!value || value === 'direct') return ''
  if (value === source || value === `${source}_profile`) return ''
  if (value.startsWith('proxy:')) return ''
  return value
}

function egressText(row: RealtimeMonitorRecord) {
  const label = proxySourceLabel(row.proxy_source)
  const egressLabel = egressLabelText(row)
  if (egressLabel) return `${label} ${egressLabel}`
  const hash = String(row.proxy_hash || '')
  if (hash && hash !== 'direct') return `${label} ${hash}`
  return label
}

function accountEgressDigest(row: RealtimeMonitorRecord) {
  const accountWait = formatMs(metricValue(row, 'account_wait_ms'))
  const egressWait = formatMs(metricValue(row, 'egress_wait_ms'))
  return `账号 ${accountWait} / 出口 ${egressWait}`
}

function activeEgressMeta() {
  const items = Object.entries(summary.value?.active_by_egress || {})
  if (!items.length) return '代理组、默认代理、Runtime 或直连出口'
  return items
    .slice(0, 2)
    .map(([key, count]) => {
      const [source, ...rest] = key.split(':')
      const detail = rest.join(':')
      return `${proxySourceLabel(source)}${detail ? ` ${detail}` : ''} ${count}`
    })
    .join(' / ')
}

function metricDigest(row: RealtimeMonitorRecord) {
  const pairs = [
    ['等待入口', 'handler_queue_ms'],
    ['首包', 'stream_first_queue_ms'],
    ['等待账号', 'account_wait_ms'],
    ['等待出口', 'egress_wait_ms'],
    ['出口租约', 'egress_acquire_ms'],
    ['上传', 'upload_ms'],
    ['初始化', 'bootstrap_ms'],
    ['令牌', 'requirements_ms'],
    ['准备', 'prepare_conversation_ms'],
    ['启动', 'generation_start_ms'],
    ['HTTP首包', 'http_ttfb_ms'],
    ['HTTP等待', 'http_wait_ms'],
    ['SSE首事件', 'sse_first_event_ms'],
    ['SSE空窗', 'sse_max_gap_ms'],
    ['上游生成', 'conversation_stream_ms'],
    ['上游断流', 'stream_error_ms'],
    ['解析/轮询', 'resolve_ms'],
    ['下载', 'download_ms'],
    ['重试等待', 'retry_wait_ms'],
    ['单图链路', 'stream_ms'],
  ] as const
  const parts = pairs
    .map(([label, key]) => {
      const value = metricValue(row, key)
      return value > 0 ? { label, value, text: `${label} ${formatMs(value)}` } : null
    })
    .filter(Boolean)
    .sort((a, b) => (b?.value || 0) - (a?.value || 0))
    .map(item => item?.text || '')
  const stageElapsed = Number(row.stage_elapsed_ms || 0)
  if (String(row.status || '').toLowerCase() === 'running' && stageElapsed > 0) {
    parts.unshift(`当前阶段 ${formatMs(stageElapsed)}`)
  }
  return parts.slice(0, 4).join(' / ') || '-'
}

function rowDurationMs(row: RealtimeMonitorRecord) {
  const value = Math.max(Number(row.duration_ms || 0), Number(row.elapsed_ms || 0))
  return Number.isFinite(value) ? Math.max(0, value) : 0
}

function trackedDurationMs(row: RealtimeMonitorRecord) {
  const queue = metricValue(row, 'handler_queue_ms') + metricValue(row, 'stream_first_queue_ms')
  const linearStages = [
    'account_wait_ms',
    'egress_wait_ms',
    'upload_ms',
    'bootstrap_ms',
    'requirements_ms',
    'prepare_conversation_ms',
    'generation_start_ms',
    'conversation_stream_ms',
    'stream_error_ms',
    'resolve_ms',
    'download_ms',
    'retry_wait_ms',
    'response_ms',
  ].reduce((sum, key) => sum + metricValue(row, key), 0)
  const wrappedStage = Math.max(metricValue(row, 'total_ms'), metricValue(row, 'stream_ms'), linearStages)
  return queue + wrappedStage
}

function untrackedDurationMs(row: RealtimeMonitorRecord) {
  return Math.max(0, rowDurationMs(row) - trackedDurationMs(row))
}

function slowMetricItems(row: RealtimeMonitorRecord) {
  const pairs = [
    { key: 'handler_queue_ms', label: '等待入口' },
    { key: 'stream_first_queue_ms', label: '首包' },
    { key: 'account_wait_ms', label: '等待账号' },
    { key: 'egress_wait_ms', label: '等待出口' },
    { key: 'egress_acquire_ms', label: '出口租约' },
    { key: 'upload_ms', label: '上传' },
    { key: 'bootstrap_ms', label: '初始化' },
    { key: 'requirements_ms', label: '令牌' },
    { key: 'prepare_conversation_ms', label: '准备' },
    { key: 'generation_start_ms', label: '启动' },
    { key: 'http_dns_ms', label: 'HTTP DNS' },
    { key: 'http_tcp_ms', label: 'HTTP TCP' },
    { key: 'http_tls_ms', label: 'HTTP TLS' },
    { key: 'http_wait_ms', label: 'HTTP 等待' },
    { key: 'http_ttfb_ms', label: 'HTTP 首包' },
    { key: 'sse_first_event_ms', label: 'SSE 首事件' },
    { key: 'sse_max_gap_ms', label: 'SSE 最大空窗' },
    { key: 'sse_last_gap_ms', label: 'SSE 收尾空窗' },
    { key: 'conversation_stream_ms', label: '上游生成' },
    { key: 'stream_error_ms', label: '上游断流' },
    { key: 'resolve_ms', label: '解析/轮询' },
    { key: 'download_ms', label: '下载' },
    { key: 'retry_wait_ms', label: '重试等待' },
    { key: 'response_ms', label: '响应整理' },
    { key: 'stream_ms', label: '单图内部' },
    { key: 'total_ms', label: '单图总耗时' },
  ]
  const items = pairs
    .map((item) => {
      const raw = metricValue(row, item.key)
      return raw > 0
        ? { ...item, raw, value: formatMs(raw), important: raw >= 10_000 }
        : null
    })
    .filter(Boolean) as Array<{ key: string; label: string; raw: number; value: string; important: boolean }>
  const untracked = untrackedDurationMs(row)
  if (untracked >= 1000) {
    items.push({
      key: 'untracked_ms',
      label: '未标记',
      raw: untracked,
      value: formatMs(untracked),
      important: untracked >= 10_000,
    })
  }
  if (!items.length) {
    const total = rowDurationMs(row)
    if (total > 0) {
      items.push({ key: 'duration_ms', label: '总耗时', raw: total, value: formatMs(total), important: total >= 10_000 })
    }
  }
  return items
}

function slowRowReason(row: RealtimeMonitorRecord) {
  const candidates = slowMetricItems(row)
    .filter(item => !['stream_ms', 'total_ms', 'duration_ms'].includes(item.key))
    .sort((a, b) => b.raw - a.raw)
  const top = candidates[0]
  if (!top || top.raw < 1000) return ''
  if (top.key === 'untracked_ms') {
    return `仍有 ${top.value} 没有落到具体阶段，说明这段链路还缺埋点。`
  }
  if (top.key === 'resolve_ms') {
    return `主要卡在图片结果解析/轮询，通常对应等待 ChatGPT 图片任务完成或轮询超时。`
  }
  if (top.key === 'conversation_stream_ms') {
    return `主要卡在上游生成中，通常是 ChatGPT 生成阶段耗时。`
  }
  if (top.key === 'stream_error_ms') {
    return `主要卡在上游断流，通常是 HTTP2/SSE、代理或上游边缘节点中断。`
  }
  if (top.key === 'http_ttfb_ms' || top.key === 'http_wait_ms') {
    return `主要卡在 HTTP 首包，通常是代理出口、上游边缘节点或请求排队变慢。`
  }
  if (['http_dns_ms', 'http_tcp_ms', 'http_tls_ms'].includes(top.key)) {
    return `主要卡在 HTTP 建连阶段：${top.label} ${top.value}。`
  }
  if (top.key === 'sse_first_event_ms') {
    return `主要卡在 SSE 首事件，说明连接已建立但上游长时间没有返回首个事件。`
  }
  if (top.key === 'sse_max_gap_ms' || top.key === 'sse_last_gap_ms') {
    return `主要卡在 SSE 空窗，说明上游流中间长时间没有新事件。`
  }
  if (top.key === 'egress_wait_ms') {
    return `主要卡在等待出口，通常是代理组、默认代理、Runtime 出口或出站会话准备变慢。`
  }
  if (['upload_ms', 'bootstrap_ms', 'requirements_ms', 'prepare_conversation_ms', 'generation_start_ms'].includes(top.key)) {
    return `主要卡在上游准备阶段：${top.label} ${top.value}。`
  }
  if (top.key === 'account_wait_ms') {
    return `主要卡在等待账号，通常是可用账号不足或账号并发被占满。`
  }
  if (top.key === 'retry_wait_ms') {
    return `主要卡在重试等待，通常是轮询、TLS 或连接失败后的退避时间。`
  }
  if (top.key === 'handler_queue_ms' || top.key === 'stream_first_queue_ms') {
    return `主要卡在等待入口，通常是后端同步线程容量不足；可通过环境变量 CHATGPT2API_THREAD_TOKENS 调整。`
  }
  return `主要耗时：${top.label} ${top.value}。`
}

function statusLabel(status: unknown) {
  const value = String(status || '').toLowerCase()
  if (value === 'success') return '成功'
  if (value === 'failed' || value === 'error' || value === 'fail') return '失败'
  if (value === 'running') return '运行中'
  return value || '-'
}

function statusTone(status: unknown): BadgeTone {
  const value = String(status || '').toLowerCase()
  if (value === 'success') return 'success'
  if (value === 'failed' || value === 'error' || value === 'fail') return 'danger'
  if (value === 'running') return 'info'
  return 'muted'
}

function eventMetricText(row: RealtimeMonitorEvent) {
  const pairs = [
    ['等待入口', 'handler_queue_ms'],
    ['首包', 'stream_first_queue_ms'],
    ['等待账号', 'account_wait_ms'],
    ['等待出口', 'egress_wait_ms'],
    ['上传', 'upload_ms'],
    ['初始化', 'bootstrap_ms'],
    ['令牌', 'requirements_ms'],
    ['准备', 'prepare_conversation_ms'],
    ['启动', 'generation_start_ms'],
    ['HTTP首包', 'http_ttfb_ms'],
    ['HTTP等待', 'http_wait_ms'],
    ['SSE首事件', 'sse_first_event_ms'],
    ['SSE空窗', 'sse_max_gap_ms'],
    ['上游生成', 'conversation_stream_ms'],
    ['上游断流', 'stream_error_ms'],
    ['解析/轮询', 'resolve_ms'],
    ['下载', 'download_ms'],
    ['重试等待', 'retry_wait_ms'],
    ['响应整理', 'response_ms'],
    ['单图内部', 'stream_ms'],
    ['单图总耗时', 'total_ms'],
  ] as const
  const parts = pairs
    .map(([label, key]) => {
      const value = Number(row[key] || 0)
      return value > 0 ? `${label} ${formatMs(value)}` : ''
    })
    .filter(Boolean)
  return parts.slice(0, 3).join(' / ') || '-'
}

onMounted(() => {
  void loadMonitor(false)
  startPolling()
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.monitor-table {
  width: 100%;
  min-width: 840px;
  border-collapse: collapse;
  text-align: left;
  font-size: 13px;
}

.monitor-table th {
  border-bottom: 1px solid hsl(var(--border));
  background: hsl(var(--muted) / 0.42);
  padding: 10px 14px;
  color: hsl(var(--muted-foreground));
  font-size: 11px;
  font-weight: 600;
}

.monitor-table td {
  border-bottom: 1px solid hsl(var(--border) / 0.72);
  padding: 12px 14px;
  vertical-align: middle;
  color: hsl(var(--foreground));
}

.monitor-table tbody tr:hover td {
  background: hsl(var(--muted) / 0.28);
}

.monitor-metric-group {
  border-radius: 8px;
  border: 1px solid hsl(var(--border));
  background: hsl(var(--background));
  padding: 14px;
}

.monitor-metric-cell {
  min-width: 0;
  border-radius: 7px;
  background: hsl(var(--muted) / 0.34);
  padding: 10px 12px;
}

.monitor-paired-panel {
  display: flex;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  flex-direction: column;
}

.monitor-paired-header {
  display: flex;
  min-height: 92px;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px 14px;
}

.monitor-paired-header__copy {
  min-width: 0;
  flex: 1 1 auto;
}

.monitor-paired-header__desc {
  margin-top: 6px;
  max-width: 48rem;
  color: hsl(var(--muted-foreground));
  font-size: 12px;
  line-height: 1.55;
}

.monitor-paired-header__meta {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  padding-top: 2px;
}

.monitor-paired-body {
  height: clamp(360px, calc(100vh - 350px), 560px);
  min-height: 0;
  overflow-y: auto;
}

@media (max-width: 768px) {
  .monitor-paired-header {
    min-height: auto;
    flex-direction: column;
    align-items: stretch;
  }

  .monitor-paired-header__meta {
    justify-content: flex-start;
    padding-top: 0;
  }
}

</style>
