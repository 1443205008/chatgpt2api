<template>
  <div class="space-y-6">
    <PagePanel class="log-control-panel">
      <PanelHeader title="日志管理" align="start">
        <template #copy>
          <p v-if="activeLogView === 'system' && selectedLogCount > 0" class="mt-1 text-xs text-muted-foreground">
            已选 {{ selectedLogCount }} 条
          </p>
        </template>
        <template #actions>
          <Button size="sm" :variant="activeLogView === 'system' ? 'primary' : 'outline'" @click="setActiveLogView('system')">
            调用日志
          </Button>
          <Button size="sm" :variant="activeLogView === 'runtime' ? 'primary' : 'outline'" @click="setActiveLogView('runtime')">
            运行日志
          </Button>
          <Button size="sm" variant="outline" :disabled="activeFetching" @click="refreshActiveLogs">
            {{ activeFetching ? '刷新中...' : '刷新' }}
          </Button>
          <Button size="sm" variant="outline" :disabled="activeExportDisabled" @click="exportActiveLogs">
            导出当前页
          </Button>
          <Button
            v-if="activeLogView === 'system'"
            size="sm"
            variant="outline"
            root-class="text-rose-600 hover:text-rose-700"
            :disabled="selectedLogCount === 0 || isFetching || isDeleting"
            @click="requestDeleteSelectedLogs"
          >
            删除所选{{ selectedLogCount ? ` (${selectedLogCount})` : '' }}
          </Button>
          <Button v-if="activeLogView === 'runtime'" size="sm" :variant="autoRefreshEnabled ? 'primary' : 'outline'" @click="toggleAutoRefresh">
            {{ autoRefreshEnabled ? '自动刷新 8s' : '自动刷新' }}
          </Button>
        </template>
      </PanelHeader>

      <MetricStrip
        :items="activeMetricItems"
        :columns-class="activeLogView === 'runtime' ? 'grid-cols-2 md:grid-cols-3 xl:grid-cols-5' : 'grid-cols-2 md:grid-cols-3 xl:grid-cols-6'"
        density="compact"
      />

      <FilterToolbar v-if="activeLogView === 'system'" class="log-toolbar">
        <Input
          v-model.trim="filters.search"
          type="text"
          placeholder="搜索关键词、账号、错误码"
          block
          root-class="log-search-input"
        />
        <DateRangeInputs
          v-model:start="filters.startDate"
          v-model:end="filters.endDate"
          class="log-date-pair"
          input-root-class="log-date-input"
        />
        <div class="log-filter-select">
          <GroupedSelectMenu
            :model-value="systemQuickFilterSelection"
            :groups="systemQuickFilterGroups"
            multiple
            placeholder="筛选"
            selected-count-text="筛选"
            :max-visible-labels="1"
            aria-label="筛选"
            @update:model-value="updateSystemQuickFilters"
          />
        </div>
        <div class="log-filter-select">
          <GroupedSelectMenu
            :model-value="advancedConditionSelection"
            :groups="advancedConditionMenuGroups"
            multiple
            placeholder="更多条件"
            selected-count-text="条件"
            :max-visible-labels="1"
            aria-label="更多条件"
            @update:model-value="updateAdvancedConditions"
          />
        </div>
        <Button size="sm" variant="ghost" :disabled="activeSystemFilterCount === 0" @click="resetFilters">
          重置
        </Button>
      </FilterToolbar>

      <FilterToolbar v-else class="log-toolbar">
        <Input
          v-model.trim="runtimeFilters.search"
          type="text"
          placeholder="搜索运行事件、错误、conversation_id、文件路径..."
          block
          root-class="log-search-input"
        />
        <GroupedSelectMenu
          :model-value="String(runtimeFilters.limit)"
          :options="runtimeLimitOptions"
          selected-indicator="none"
          aria-label="运行日志数量"
          @update:model-value="updateRuntimeLimit"
        />
        <FloatingActionMenu
          :label="runtimeFilterLabel"
          :items="runtimeFilterMenuItems"
          align="left"
          trigger-class="min-w-[7.5rem]"
          @select="handleRuntimeFilterMenuSelect"
        />
      </FilterToolbar>
    </PagePanel>

    <PagePanel v-if="activeLogView === 'system' && isFetching && logs.length === 0">
      <PageLoadingState
        title="正在加载调用日志"
        description="正在读取调用记录和统计信息..."
        compact
        dashed
      />
    </PagePanel>

    <PagePanel v-else-if="activeLogView === 'system'" flush>
      <TableShell>
        <table class="w-full min-w-[1120px] table-fixed text-left">
          <colgroup>
            <col class="w-12" />
            <col class="w-36" />
            <col class="w-24" />
            <col class="w-40" />
            <col class="w-28" />
            <col class="w-24" />
            <col class="w-28" />
            <col />
            <col class="w-36" />
          </colgroup>
          <thead class="bg-muted/40 text-xs text-muted-foreground">
            <tr>
              <th class="py-3 pl-4 pr-2">
                <Checkbox
                  :model-value="allVisibleLogsSelected"
                  :disabled="visibleLogs.length === 0"
                  @update:model-value="toggleSelectAllVisibleLogs"
                >
                  <span class="sr-only">全选当前页日志</span>
                </Checkbox>
              </th>
              <th class="py-3 pr-5">时间</th>
              <th class="py-3 pr-5">类型</th>
              <th class="py-3 pr-5">令牌名称</th>
              <th class="py-3 pr-5">调用耗时</th>
              <th class="py-3 pr-5">状态</th>
              <th class="py-3 pr-5">图片</th>
              <th class="py-3 pr-5">简述</th>
              <th class="py-3 pr-4 text-right">操作</th>
            </tr>
          </thead>
          <tbody class="text-sm text-foreground">
            <tr v-if="!isFetching && logs.length === 0">
              <td colspan="9" class="py-8">
                <EmptyState
                  plain
                  :title="logsLoadError ? '日志加载失败' : '暂无日志'"
                  :description="logsLoadError || '换个筛选条件或刷新后再看。'"
                />
              </td>
            </tr>
            <tr
              v-for="item in visibleLogs"
              :key="item.id"
              class="border-t border-border transition-colors hover:bg-muted/30"
              :class="{ 'bg-primary/5': isLogSelected(item.id) }"
            >
              <td class="py-4 pl-4 pr-2 align-middle">
                <Checkbox
                  :model-value="isLogSelected(item.id)"
                  @update:model-value="(checked) => toggleLogSelection(item.id, checked)"
                >
                  <span class="sr-only">选择日志 {{ item.time || item.id }}</span>
                </Checkbox>
              </td>
              <td class="py-4 pr-5 align-middle text-xs text-muted-foreground">
                <p class="whitespace-nowrap text-foreground">{{ item.time || '-' }}</p>
              </td>
              <td class="py-4 pr-5 align-middle">
                <MetaChip size="xs" tone="muted">{{ typeLabel(item.type) }}</MetaChip>
              </td>
              <td class="py-4 pr-5 align-middle">
                <p class="max-w-[12rem] truncate text-xs text-foreground" :title="tokenLabel(item)">
                  {{ tokenLabel(item) || '-' }}
                </p>
              </td>
              <td class="py-4 pr-5 align-middle text-xs text-muted-foreground">
                {{ formatDuration(item.durationMs) || '-' }}
              </td>
              <td class="py-4 pr-5 align-middle">
                <StateBadge :tone="statusTone(item)" shape="rounded" :bordered="false">
                  {{ statusLabel(item) }}
                </StateBadge>
              </td>
              <td class="py-4 pr-5 align-middle">
                <LogImagePreviewCell
                  :image-urls="item.imageUrls"
                  :first-image-broken="isPreviewBroken(item.imageUrls[0] || '')"
                  :alt="item.preview || '日志结果图片'"
                  @preview-click="openDetail(item)"
                  @image-error="markPreviewBroken"
                />
              </td>
              <td class="py-4 pr-5 align-middle">
                <p class="max-w-[28rem] truncate text-xs text-foreground" :class="{ 'text-rose-600': isFailed(item) }" :title="summaryText(item)">
                  {{ summaryText(item) || '-' }}
                </p>
              </td>
              <td class="py-4 pr-4 text-right align-middle">
                <div class="flex justify-end gap-1.5">
                  <Button size="xs" variant="outline" @click="openDetail(item)">
                    查看详情
                  </Button>
                  <Button size="xs" variant="ghost" root-class="text-rose-600 hover:text-rose-700" @click="requestDeleteLog(item)">
                    删除
                  </Button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>

        <template #footer>
        <ListPagination
          v-model:page="currentPage"
          v-model:page-size="filters.limit"
          :total-count="logMeta.total"
          :page-size-options="systemLogPageSizeOptions"
          unit="条日志"
          :disabled="isFetching"
        />
        </template>
      </TableShell>
    </PagePanel>

    <PagePanel v-else-if="runtimeFetching && runtimeLogs.length === 0">
      <PageLoadingState
        title="正在加载运行日志"
        description="正在读取运行事件和日志文件..."
        compact
        dashed
      />
    </PagePanel>

    <PagePanel v-else>
      <RuntimeLogPanel
        :raw-text="runtimeRawText"
        :empty-title="runtimeLoadError ? '运行日志加载失败' : '暂无运行日志'"
        :empty-description="runtimeLoadError"
      />
    </PagePanel>

    <ModalShell
      :open="!!selectedLog"
      max-width="54rem"
      :z-index="130"
      align="start"
      placement="end"
      panel-class="flex h-[calc(100vh-32px)] max-h-[calc(100vh-32px)] flex-col"
      close-on-backdrop
      @close="closeDetail"
    >
      <template v-if="selectedLog">
          <ModalHeader title="日志详情" @close="closeDetail" />

          <div class="scrollbar-slim flex-1 space-y-5 overflow-y-auto px-5 py-4">
            <section class="log-detail-summary">
              <div class="log-detail-summary__main">
                <div class="log-detail-summary__copy">
                  <div class="log-detail-summary__title-row">
                    <StateBadge :tone="statusTone(selectedLog)" shape="rounded" :bordered="false">
                      {{ statusLabel(selectedLog) }}
                    </StateBadge>
                  </div>
                  <p class="log-detail-summary__title">
                    {{ summaryText(selectedLog) || '调用日志' }}
                  </p>
                </div>
                <div class="log-detail-summary__duration">
                  <span>总耗时</span>
                  <strong>{{ formatTimelineMs(selectedLog.durationMs) }}</strong>
                </div>
              </div>
            </section>

            <div class="detail-field-stack">
              <section class="detail-field-section">
                <div class="detail-field-section__header">
                  <span>请求身份</span>
                </div>
                <div class="detail-field-grid">
                  <DetailFieldCard
                    v-for="field in selectedPrimaryDetailFields"
                    :key="field.label"
                    :class="{ 'detail-field-grid__item--wide': field.wide }"
                    :label="field.label"
                    :value="field.value"
                    :copyable="field.copyable"
                    variant="row"
                    @copy="copyText"
                  />
                </div>
              </section>

              <section v-if="selectedDiagnosticDetailFields.length" class="detail-field-section">
                <div class="detail-field-section__header detail-field-section__header--muted">
                  <span>诊断字段</span>
                </div>
                <div class="detail-field-grid detail-field-grid--diagnostic">
                  <DetailFieldCard
                    v-for="field in selectedDiagnosticDetailFields"
                    :key="field.label"
                    :label="field.label"
                    :value="field.value"
                    :copyable="field.copyable"
                    variant="row"
                    @copy="copyText"
                  />
                </div>
              </section>
            </div>

            <section v-if="selectedHasTimeline" class="detail-timeline">
              <div class="detail-timeline__header">
                <div>
                  <span class="detail-timeline__title">步骤耗时</span>
                  <p>按执行顺序展示，条形长度表示相对耗时</p>
                </div>
                <div class="detail-timeline__meta">
                  <MetaChip size="xs" tone="muted">{{ selectedTimelineStepCount }} 步</MetaChip>
                  <MetaChip v-if="selectedTimelineSegmentTotal" size="xs" tone="muted">
                    分段合计 {{ formatTimelineMs(selectedTimelineSegmentTotal) }}
                  </MetaChip>
                  <MetaChip v-if="selectedBottleneckStep" size="xs" tone="warning">
                    瓶颈 {{ selectedBottleneckStep.label }}
                  </MetaChip>
                </div>
              </div>

              <div v-if="selectedTimelineSegments.length" class="detail-timeline-segments">
                <div class="detail-timeline-segments__track">
                  <div
                    v-for="segment in selectedTimelineSegments"
                    :key="segment.key"
                    class="detail-timeline-segments__segment"
                    :class="[
                      `detail-timeline-segments__segment--${segment.category}`,
                      `detail-timeline-segments__segment--${segment.tone}`,
                      { 'detail-timeline-segments__segment--compact': segment.compact },
                    ]"
                    :style="segment.barStyle"
                    :title="segment.title"
                  >
                    <span>{{ segment.label }}</span>
                    <strong>{{ segment.value }}</strong>
                  </div>
                </div>
                <div v-if="selectedTimelineLegendItems.length" class="detail-timeline-segments__legend">
                  <span
                    v-for="item in selectedTimelineLegendItems"
                    :key="`${item.key}-legend`"
                    class="detail-timeline-segments__legend-item"
                    :class="[`detail-timeline-segments__legend-item--${item.category}`, `detail-timeline-segments__legend-item--${item.tone}`]"
                  >
                    <i />
                    {{ item.label }}
                  </span>
                </div>
              </div>

              <div v-else class="detail-timeline__empty">
                这条日志没有步骤耗时埋点；新的图片请求会显示分段耗时。
              </div>

              <div v-if="selectedTimelineGroups.length" class="detail-timeline__details">
                <button type="button" class="detail-timeline__toggle" @click.stop="toggleTimelineDetails">
                  <span>步骤明细</span>
                  <strong>{{ timelineDetailsVisible ? '收起' : '展开' }}</strong>
                </button>
                <div v-show="timelineDetailsVisible" class="detail-timeline__groups">
                  <div v-for="group in selectedTimelineGroups" :key="group.name" class="detail-timeline__group">
                    <div class="detail-timeline__group-title">{{ group.name }}</div>
                    <div class="detail-timeline__steps">
                      <div
                        v-for="step in group.steps"
                        :key="step.key"
                        class="detail-timeline__step"
                        :class="[`detail-timeline__step--${step.category}`, `detail-timeline__step--${step.tone}`]"
                      >
                        <div class="detail-timeline__step-main">
                          <div class="detail-timeline__step-head">
                            <div class="detail-timeline__step-label">
                              <span>{{ step.label }}</span>
                              <StateBadge :tone="step.tone" size="xs" shape="rounded">
                                {{ step.statusLabel }}
                              </StateBadge>
                            </div>
                            <span v-if="step.time" class="detail-timeline__step-time">{{ step.time }}</span>
                          </div>
                          <div class="detail-timeline__bar">
                            <span :style="step.barStyle" />
                          </div>
                          <p v-if="step.note" class="detail-timeline__step-note">{{ step.note }}</p>
                        </div>
                        <strong class="detail-timeline__step-value">{{ step.value }}</strong>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <DetailTextBlock
              :title="selectedLog.requestTextTruncated ? '请求文本（已截断）' : '请求文本'"
              :content="selectedLog.requestTextFull || selectedLog.requestText"
              @copy="copyText"
            />
            <DetailTextBlock
              title="错误"
              :content="selectedLog.error"
              tone="danger"
              @copy="copyText"
            />
            <DetailTextBlock
              title="原始上游错误"
              :content="selectedLog.rawUpstreamError"
              tone="danger"
              @copy="copyText"
            />
            <DetailTextBlock
              title="上游文本回复"
              :content="selectedLog.rawUpstreamMessage || selectedLog.upstreamPreview"
              tone="warning"
              @copy="copyText"
            />
            <DetailImagePreview
              :images="selectedDetailImages"
              @image-error="markPreviewBroken"
              @preview-click="openDetailImagePreview"
            />
            <DetailTextBlock
              title="结果 URL"
              :content="selectedLog.urls.join('\n')"
              @copy="copyText"
            />

            <DetailTextBlock
              title="原始 detail JSON"
              :content="selectedLog.rawJson"
              tone="muted"
              max-height="24rem"
              @copy="copyText"
            />
          </div>
      </template>
    </ModalShell>

    <GalleryLightbox
      :file="selectedDetailPreviewFile"
      :image-url="selectedDetailPreview?.url || ''"
      size-label=""
      :copied="Boolean(selectedDetailPreviewFile && copiedLogPreviewKey === selectedDetailPreviewFile.path)"
      :show-actions="true"
      :show-tag-action="false"
      @download="downloadLogPreviewFile"
      @copy="copyLogPreviewFile"
      @close="selectedDetailPreview = null"
    />

    <OperationProgressModal
      :open="operationProgress.open"
      :title="operationProgress.title"
      :subtitle="operationProgress.subtitle"
      :total="operationProgress.total"
      :current="operationProgress.current"
      :status-label="operationProgress.statusLabel"
      :message="operationProgress.message"
      :error="operationProgress.error"
      :busy="operationProgress.busy"
      @close="operationProgress.open = false"
    />

    <ConfirmDialog
      :open="Boolean(deleteTarget)"
      title="删除日志"
      :message="`确认删除这条日志吗？删除后无法恢复。${deleteTarget?.time ? `\n时间：${deleteTarget.time}` : ''}`"
      confirm-text="删除"
      cancel-text="取消"
      @confirm="deleteLog"
      @cancel="deleteTarget = null"
    />
    <ConfirmDialog
      :open="deleteSelectedOpen"
      title="删除所选日志"
      :message="`确认删除当前选中的 ${selectedLogCount} 条日志吗？删除后无法恢复。`"
      confirm-text="删除所选"
      cancel-text="取消"
      @confirm="deleteSelectedLogs"
      @cancel="deleteSelectedOpen = false"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Button, Checkbox, EmptyState, Input } from 'nanocat-ui'
import type { ActionMenuItem } from 'nanocat-ui'
import ConfirmDialog from '@/components/ui/AppConfirmDialog.vue'
import GroupedSelectMenu from '@/components/ui/GroupedSelectMenu.vue'
import DateRangeInputs from '@/components/ai/DateRangeInputs.vue'
import DetailFieldCard from '@/components/ai/DetailFieldCard.vue'
import DetailImagePreview from '@/components/ai/DetailImagePreview.vue'
import DetailTextBlock from '@/components/ai/DetailTextBlock.vue'
import FilterToolbar from '@/components/ai/FilterToolbar.vue'
import FloatingActionMenu from '@/components/ai/FloatingActionMenu.vue'
import ListPagination from '@/components/ai/ListPagination.vue'
import LogImagePreviewCell from '@/components/ai/LogImagePreviewCell.vue'
import MetaChip from '@/components/ai/MetaChip.vue'
import MetricStrip from '@/components/ai/MetricStrip.vue'
import ModalHeader from '@/components/ai/ModalHeader.vue'
import ModalShell from '@/components/ai/ModalShell.vue'
import PageLoadingState from '@/components/ai/PageLoadingState.vue'
import PagePanel from '@/components/ai/PagePanel.vue'
import PanelHeader from '@/components/ai/PanelHeader.vue'
import RuntimeLogPanel from '@/components/ai/RuntimeLogPanel.vue'
import StateBadge from '@/components/ai/StateBadge.vue'
import TableShell from '@/components/ai/TableShell.vue'
import { actionMenuGroups } from '@/components/ai/menuItems'
import { logsApi } from '@/api/logs'
import { resolveGalleryFileUrl, type GalleryFile } from '@/api/gallery'
import type { RuntimeLog, RuntimeLogsResponse, SystemLogRow, SystemLogsResponse } from '@/api/logs'
import {
  formatLogDuration as formatDuration,
  isSystemLogFailed as isFailed,
  isSystemLogLimited as isLimited,
  isSystemLogSuccess as isSuccess,
  normalizeSystemLogRow,
} from '@/api/logs'
import { useToast } from '@/composables/useToast'
import { downloadUrlAsFile, saveBlob } from '@/lib/downloads'
import { getNumberPreference, preferenceKeys, setNumberPreference } from '@/lib/preferences'

const GalleryLightbox = defineAsyncComponent(() => import('@/components/ai/GalleryLightbox.vue'))
const OperationProgressModal = defineAsyncComponent(() => import('@/components/ai/OperationProgressModal.vue'))

type LogRow = SystemLogRow

type DetailField = {
  label: string
  value: string
  copyable?: boolean
  wide?: boolean
}

type DetailTone = 'success' | 'danger' | 'warning' | 'info' | 'muted'
type DetailTimelineCategory = 'entry' | 'prepare' | 'network' | 'upstream' | 'resolve' | 'download' | 'retry' | 'response'

type DetailTimelineStepConfig = {
  key: string
  label: string
  group: string
  hint?: string
}

type DetailTimelineStep = DetailTimelineStepConfig & {
  valueMs: number
  value: string
  tone: DetailTone
  category: DetailTimelineCategory
  statusLabel: string
  barStyle: Record<string, string>
  time: string
  note: string
}

type DetailTimelineSegment = {
  key: string
  label: string
  valueMs: number
  value: string
  percent: string
  tone: DetailTone
  category: DetailTimelineCategory
  compact: boolean
  barStyle: Record<string, string>
  title: string
}

type DetailTimelineLegendItem = {
  key: DetailTimelineCategory | DetailTone
  label: string
  category: DetailTimelineCategory | 'state'
  tone: DetailTone
}

type DetailTimelineGroup = {
  name: string
  steps: DetailTimelineStep[]
}

type DetailPreviewImage = {
  url: string
  title?: string
  filename?: string
  alt?: string
  broken?: boolean
}

type LogView = 'system' | 'runtime'
type AdvancedFilterKey = 'type' | 'status' | 'model' | 'account'
type FilterOption = { label: string; value: string }
type GroupedSelectOption = FilterOption & { disabled?: boolean }
type GroupedSelectGroup = {
  label?: string
  options: GroupedSelectOption[]
}
type AdvancedConditionGroup = {
  key: AdvancedFilterKey
  label: string
  options: FilterOption[]
}

const detailTimelineSteps: DetailTimelineStepConfig[] = [
  { key: 'handler_queue_ms', label: '等待入口', group: '入口与账号', hint: 'run_in_threadpool' },
  { key: 'stream_first_queue_ms', label: '读取首包', group: '入口与账号', hint: '首个响应事件' },
  { key: 'account_wait_ms', label: '等待账号', group: '入口与账号', hint: '账号池筛选' },
  { key: 'egress_wait_ms', label: '等待出口', group: '入口与账号', hint: '代理出口准备' },
  { key: 'egress_acquire_ms', label: '出口租约', group: '入口与账号', hint: '代理节点并发' },
  { key: 'upload_ms', label: '上传输入图', group: '上游准备', hint: '参考图上传' },
  { key: 'bootstrap_ms', label: '预热页面', group: '上游准备', hint: 'ChatGPT 页面' },
  { key: 'requirements_ms', label: '获取请求令牌', group: '上游准备', hint: 'requirements / token' },
  { key: 'prepare_conversation_ms', label: '准备会话', group: '上游准备', hint: '图片会话上下文' },
  { key: 'generation_start_ms', label: '启动生成', group: '上游准备', hint: '提交上游请求' },
  { key: 'http_dns_ms', label: 'HTTP DNS', group: 'HTTP 连接', hint: '域名解析' },
  { key: 'http_tcp_ms', label: 'HTTP TCP', group: 'HTTP 连接', hint: '代理 / TCP 建连' },
  { key: 'http_tls_ms', label: 'HTTP TLS', group: 'HTTP 连接', hint: 'TLS 握手' },
  { key: 'http_wait_ms', label: 'HTTP 等待', group: 'HTTP 连接', hint: '请求发出到首包' },
  { key: 'http_ttfb_ms', label: 'HTTP 首包', group: 'HTTP 连接', hint: '请求开始到首包' },
  { key: 'sse_first_event_ms', label: 'SSE 首事件', group: '生成与结果', hint: '首个 data 事件' },
  { key: 'sse_max_gap_ms', label: 'SSE 最大空窗', group: '生成与结果', hint: '两次事件最大间隔' },
  { key: 'sse_last_gap_ms', label: 'SSE 收尾空窗', group: '生成与结果', hint: '最后事件到关闭' },
  { key: 'conversation_stream_ms', label: '上游生成', group: '生成与结果', hint: 'ChatGPT 会话流' },
  { key: 'stream_error_ms', label: '上游断流', group: '生成与结果', hint: 'HTTP2 / SSE' },
  { key: 'resolve_ms', label: '解析/轮询', group: '生成与结果', hint: 'conversation / file' },
  { key: 'download_ms', label: '下载图片', group: '生成与结果', hint: '图片文件下载' },
  { key: 'retry_wait_ms', label: '重试等待', group: '生成与结果', hint: '轮询 / 退避' },
  { key: 'response_ms', label: '响应整理', group: '生成与结果', hint: 'Codex 响应' },
  { key: 'stream_ms', label: '单图内部', group: '生成与结果', hint: '单图链路' },
  { key: 'total_ms', label: '单图总耗时', group: '生成与结果', hint: '完整链路' },
]

const detailTimelineGroupOrder = ['入口与账号', '上游准备', 'HTTP 连接', '生成与结果']
const detailTimelineAggregateKeys = new Set([
  'http_dns_ms',
  'http_tcp_ms',
  'http_tls_ms',
  'http_wait_ms',
  'http_ttfb_ms',
  'sse_first_event_ms',
  'sse_max_gap_ms',
  'sse_last_gap_ms',
  'stream_ms',
  'total_ms',
])
const defaultTimelineWarningThresholdMs = 60_000
const timelineWarningThresholdMs: Record<string, number> = {
  handler_queue_ms: 1_000,
  stream_first_queue_ms: 1_000,
  account_wait_ms: 10_000,
  egress_wait_ms: 10_000,
  egress_acquire_ms: 10_000,
  upload_ms: 60_000,
  bootstrap_ms: 60_000,
  requirements_ms: 60_000,
  prepare_conversation_ms: 60_000,
  generation_start_ms: 60_000,
  http_dns_ms: 1_000,
  http_tcp_ms: 3_000,
  http_tls_ms: 5_000,
  http_wait_ms: 30_000,
  http_ttfb_ms: 30_000,
  sse_first_event_ms: 30_000,
  sse_max_gap_ms: 60_000,
  sse_last_gap_ms: 30_000,
  download_ms: 60_000,
  retry_wait_ms: 60_000,
  response_ms: 30_000,
}

const detailTimelineCategoryLabels: Record<DetailTimelineCategory, string> = {
  entry: '入口与账号',
  prepare: '上游准备',
  network: 'HTTP 连接',
  upstream: '上游生成',
  resolve: '解析/轮询',
  download: '图片下载',
  retry: '重试等待',
  response: '响应整理',
}
const detailTimelineCategoryOrder: DetailTimelineCategory[] = ['entry', 'prepare', 'network', 'upstream', 'resolve', 'download', 'retry', 'response']

const toast = useToast()
const route = useRoute()
const apiBaseUrl = import.meta.env.VITE_API_URL || window.location.origin
const activeLogView = ref<LogView>('system')
const logs = ref<LogRow[]>([])
const isFetching = ref(false)
const logsLoadError = ref('')
const runtimeLogs = ref<RuntimeLog[]>([])
const runtimeFetching = ref(false)
const runtimeLoadError = ref('')
const selectedLog = ref<LogRow | null>(null)
const timelineDetailsExpanded = ref(false)
const selectedDetailPreview = ref<DetailPreviewImage | null>(null)
const copiedLogPreviewKey = ref('')
const autoRefreshEnabled = ref(false)
const currentPage = ref(1)
const brokenPreviewUrls = ref<Set<string>>(new Set())
const deleteTarget = ref<LogRow | null>(null)
const deleteSelectedOpen = ref(false)
const selectedLogIds = ref<string[]>([])
const isDeleting = ref(false)
const operationProgress = reactive({
  open: false,
  title: '',
  subtitle: '',
  total: 0,
  current: 0,
  statusLabel: '已处理',
  message: '',
  error: '',
  busy: false,
})
const DEFAULT_SYSTEM_LOG_LIMIT = 20
const DEFAULT_RUNTIME_LOG_LIMIT = 500

const logMeta = reactive<SystemLogsResponse>({
  items: [],
  total: 0,
  limit: DEFAULT_SYSTEM_LOG_LIMIT,
  offset: 0,
  has_more: false,
  facets_scope: '',
  stats_scope: '',
  total_scope: '',
  facets: {
    statuses: {},
    endpoints: {},
    models: {},
    accounts: {},
  },
  stats: {
    total: 0,
    success: 0,
    failed: 0,
    limited: 0,
    image: 0,
  },
})

const filters = reactive({
  type: 'call',
  status: '',
  endpoint: '',
  model: '',
  account: '',
  conversationId: '',
  search: '',
  startDate: '',
  endDate: '',
  limit: DEFAULT_SYSTEM_LOG_LIMIT,
})

const runtimeFilters = reactive({
  level: '',
  source: '',
  search: '',
  limit: DEFAULT_RUNTIME_LOG_LIMIT,
})

const runtimeMeta = reactive<RuntimeLogsResponse>({
  items: [],
  total: 0,
  limit: DEFAULT_RUNTIME_LOG_LIMIT,
  sources: {
    memory: true,
    files: [],
  },
})

const typeOptions = [
  { label: '调用日志', value: 'call' },
  { label: '账号日志', value: 'account' },
  { label: '全部类型', value: '' },
]

const systemLogPageSizeOptions = [20, 50, 100, 200, 500]
const runtimeLimitOptions = [
  { label: '100', value: '100' },
  { label: '300', value: '300' },
  { label: '500', value: '500' },
  { label: '1000', value: '1000' },
  { label: '2000', value: '2000' },
]

const runtimeLevelOptions = [
  { label: '全部级别', value: '' },
  { label: 'debug', value: 'debug' },
  { label: 'info', value: 'info' },
  { label: 'warning', value: 'warning' },
  { label: 'error', value: 'error' },
]

const runtimeSourceOptions = [
  { label: '全部来源', value: '' },
  { label: '内存日志', value: 'memory' },
  { label: '文件尾部', value: 'file' },
]

let autoRefreshTimer: number | null = null
let filterFetchTimer: number | null = null
let logPreviewCopyResetTimer: number | null = null
let isApplyingRouteQuery = false
const routeTargetLogId = ref('')

function cleanString(value: unknown): string {
  if (value === undefined || value === null) return ''
  return String(value).trim()
}

function isPreviewBroken(url: string): boolean {
  return brokenPreviewUrls.value.has(url)
}

function markPreviewBroken(event: Event, url: string) {
  const img = event.target as HTMLImageElement
  img.style.opacity = '0'
  brokenPreviewUrls.value = new Set([...brokenPreviewUrls.value, url])
}

function filenameFromUrl(url: string): string {
  const value = cleanString(url)
  if (!value) return '-'
  try {
    const parsed = new URL(value, window.location.origin)
    const name = parsed.pathname.split('/').filter(Boolean).pop()
    return name || parsed.hostname || value
  } catch {
    return value.split('/').filter(Boolean).pop() || value
  }
}

const logStats = computed(() => logMeta.stats)
const activeFetching = computed(() => activeLogView.value === 'runtime' ? runtimeFetching.value : isFetching.value)
const activeExportDisabled = computed(() => (
  activeLogView.value === 'runtime'
    ? runtimeLogs.value.length === 0
    : logs.value.length === 0
))
const runtimeStats = computed(() => {
  const counts = { total: runtimeLogs.value.length, warning: 0, error: 0, memory: 0, file: 0 }
  runtimeLogs.value.forEach((item) => {
    const level = cleanString(item.level).toLowerCase()
    const source = cleanString(item.source).toLowerCase()
    if (level === 'warning') counts.warning += 1
    if (level === 'error' || level === 'critical') counts.error += 1
    if (source === 'memory') counts.memory += 1
    if (source === 'file') counts.file += 1
  })
  return counts
})

const systemMetricItems = computed(() => [
  { label: '总数', value: logStats.value.total, class: 'text-foreground' },
  { label: logMeta.stats_scope === 'page' ? '本页成功' : '成功', value: logStats.value.success, class: 'text-emerald-600' },
  { label: logMeta.stats_scope === 'page' ? '本页失败' : '失败', value: logStats.value.failed, class: 'text-rose-600' },
  { label: logMeta.stats_scope === 'page' ? '本页限流' : '限流', value: logStats.value.limited, class: 'text-amber-600' },
  { label: logMeta.stats_scope === 'page' ? '本页图片' : '图片接口', value: logStats.value.image, class: 'text-cyan-600' },
])

const runtimeMetricItems = computed(() => [
  { label: '运行日志', value: runtimeStats.value.total, class: 'text-foreground' },
  { label: 'Warning', value: runtimeStats.value.warning, class: 'text-amber-600' },
  { label: 'Error', value: runtimeStats.value.error, class: 'text-rose-600' },
  { label: '内存', value: runtimeStats.value.memory, class: 'text-cyan-600' },
  { label: '文件', value: runtimeStats.value.file, class: 'text-violet-600' },
])

const activeMetricItems = computed(() => activeLogView.value === 'runtime' ? runtimeMetricItems.value : systemMetricItems.value)
const currentLogIdSet = computed(() => new Set(logs.value.map((item) => item.id).filter(Boolean)))
const selectedDeletableLogIds = computed(() => (
  Array.from(new Set(selectedLogIds.value)).filter((id) => currentLogIdSet.value.has(id))
))
const runtimeRawText = computed(() => runtimeLogs.value.map(formatRuntimeLogLine).join('\n'))

const activeSystemFilterCount = computed(() => [
  filters.search,
  filters.startDate,
  filters.endDate,
  filters.status,
  filters.endpoint,
  filters.model,
  filters.account,
  filters.conversationId,
  filters.type !== 'call' ? filters.type || 'all' : '',
].filter(Boolean).length)

const activeRuntimeFilterCount = computed(() => [
  runtimeFilters.level,
  runtimeFilters.source,
  runtimeFilters.search,
].filter(Boolean).length)

const runtimeFilterLabel = computed(() => activeRuntimeFilterCount.value ? `筛选 ${activeRuntimeFilterCount.value}` : '筛选')

function currentMenuLabel(label: string, active: boolean): string {
  return active ? `${label}（当前）` : label
}

const quickEndpointValues = ['/v1/images/edits', '/v1/images/generations'] as const
const systemQuickFilterOptions: GroupedSelectOption[] = [
  { label: '只看失败', value: 'quick:status:failed' },
  { label: '图生图', value: 'quick:endpoint:/v1/images/edits' },
  { label: '文生图', value: 'quick:endpoint:/v1/images/generations' },
]
const systemQuickFilterGroups: GroupedSelectGroup[] = [
  { options: systemQuickFilterOptions },
]
const systemQuickFilterSelection = computed(() => {
  const values: string[] = []
  if (filters.status === 'failed') values.push('quick:status:failed')
  if (filters.endpoint === '/v1/images/edits') values.push('quick:endpoint:/v1/images/edits')
  if (filters.endpoint === '/v1/images/generations') values.push('quick:endpoint:/v1/images/generations')
  return values
})

const runtimeFilterMenuItems = computed<ActionMenuItem[]>(() => actionMenuGroups(
  runtimeLevelOptions
    .filter((item) => item.value)
    .map((item) => ({
      key: `runtime-level:${item.value}`,
      label: currentMenuLabel(`级别 ${item.label}`, runtimeFilters.level === item.value),
    })),
  runtimeSourceOptions
    .filter((item) => item.value)
    .map((item) => ({
      key: `runtime-source:${item.value}`,
      label: currentMenuLabel(item.label, runtimeFilters.source === item.value),
    })),
  [
    { key: 'runtime-clear:level', label: '清除级别筛选', disabled: !runtimeFilters.level },
    { key: 'runtime-clear:source', label: '清除来源筛选', disabled: !runtimeFilters.source },
  ],
))

function optionFromFacet(facet: Record<string, number>, allLabel: string) {
  return [
    { label: allLabel, value: '' },
    ...Object.keys(facet)
      .map(cleanString)
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b))
      .map((value) => ({ label: `${value} (${facet[value] || 0})`, value })),
  ]
}

const statusOptions = computed(() => [
  { label: '全部状态', value: '' },
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failed' },
  { label: '限流/受限', value: 'limited' },
])

const modelOptions = computed(() => optionFromFacet(logMeta.facets.models, '全部模型'))
const accountOptions = computed(() => optionFromFacet(logMeta.facets.accounts, '全部账号'))
const advancedConditionCount = computed(() => [
  filters.type !== 'call' ? filters.type || 'all' : '',
  filters.status,
  filters.model,
  filters.account,
].filter(Boolean).length)
const advancedConditionGroups = computed<AdvancedConditionGroup[]>(() => [
  {
    key: 'type',
    label: '类型',
    options: [
      { label: '调用日志', value: 'call' },
      { label: '账号日志', value: 'account' },
      { label: '全部类型', value: '' },
    ],
  },
  {
    key: 'status',
    label: '状态',
    options: statusOptions.value,
  },
  {
    key: 'model',
    label: '模型',
    options: modelOptions.value,
  },
  {
    key: 'account',
    label: '账号',
    options: accountOptions.value,
  },
])
const advancedConditionMenuGroups = computed<GroupedSelectGroup[]>(() => (
  advancedConditionGroups.value.map((group) => ({
    label: group.label,
    options: group.options.map((option) => ({
      label: option.label,
      value: advancedConditionOptionValue(group.key, option.value),
    })),
  }))
))
const advancedConditionSelection = computed(() => {
  const values: string[] = []
  if (filters.type !== 'call') values.push(advancedConditionOptionValue('type', filters.type))
  if (filters.status) values.push(advancedConditionOptionValue('status', filters.status))
  if (filters.model) values.push(advancedConditionOptionValue('model', filters.model))
  if (filters.account) values.push(advancedConditionOptionValue('account', filters.account))
  return values
})

const visibleLogs = computed(() => {
  return logs.value
})

const selectedLogIdSet = computed(() => new Set(selectedDeletableLogIds.value))
const selectedLogCount = computed(() => selectedDeletableLogIds.value.length)
const allVisibleLogsSelected = computed(() => {
  if (visibleLogs.value.length === 0) return false
  return visibleLogs.value.every((item) => selectedLogIdSet.value.has(item.id))
})

const selectedBottleneckStep = computed<DetailTimelineStep | null>(() => {
  const steps = selectedTimelineGroups.value.flatMap((group) => group.steps)
  return steps.reduce<DetailTimelineStep | null>((current, step) => {
    if (!current || step.valueMs > current.valueMs) return step
    return current
  }, null)
})

const selectedTimelineStepCount = computed(() => selectedTimelineGroups.value.reduce((total, group) => total + group.steps.length, 0))
const selectedTimelineSegmentTotal = computed(() => selectedTimelineSegments.value.reduce((total, segment) => total + segment.valueMs, 0))

const selectedTimelineSegments = computed<DetailTimelineSegment[]>(() => {
  const item = selectedLog.value
  if (!item) return []
  const rawSegments = detailTimelineSteps
    .filter((step) => !detailTimelineAggregateKeys.has(step.key))
    .map((step) => ({
      ...step,
      valueMs: metricValueFromLog(item, step.key),
    }))
    .filter((step) => step.valueMs > 0)
  const totalMs = rawSegments.reduce((total, step) => total + step.valueMs, 0)
  if (totalMs <= 0) return []
  const maxMs = Math.max(...rawSegments.map((step) => step.valueMs), 0)
  return rawSegments.map((step) => {
    const percent = (step.valueMs / totalMs) * 100
    const tone = timelineStepTone(step.key, step.valueMs, maxMs)
    const category = timelineStepCategory(step.key, step.group)
    const value = formatTimelineMs(step.valueMs)
    return {
      key: step.key,
      label: step.label,
      valueMs: step.valueMs,
      value,
      percent: `${percent.toFixed(percent >= 10 ? 0 : 1)}%`,
      tone,
      category,
      compact: percent < 12,
      barStyle: { flexGrow: String(Math.max(step.valueMs, 1)) },
      title: `${step.label} ${value} · ${percent.toFixed(1)}%`,
    }
  })
})

const selectedTimelineLegendItems = computed<DetailTimelineLegendItem[]>(() => {
  const segments = selectedTimelineSegments.value
  if (!segments.length) return []
  const categories = new Set(segments.map((segment) => segment.category))
  const items: DetailTimelineLegendItem[] = detailTimelineCategoryOrder
    .filter((category) => categories.has(category))
    .map((category) => ({
      key: category,
      label: detailTimelineCategoryLabels[category],
      category,
      tone: 'info',
    }))
  if (segments.some((segment) => segment.tone === 'warning')) {
    items.push({ key: 'warning', label: '超过阈值', category: 'state', tone: 'warning' })
  }
  if (segments.some((segment) => segment.tone === 'danger')) {
    items.push({ key: 'danger', label: '异常中断', category: 'state', tone: 'danger' })
  }
  return items
})

const selectedTimelineGroups = computed<DetailTimelineGroup[]>(() => {
  const item = selectedLog.value
  if (!item) return []
  const maxMs = Math.max(...detailTimelineSteps.map((step) => metricValueFromLog(item, step.key)), 0)
  if (maxMs <= 0) return []
  const groups = new Map<string, DetailTimelineStep[]>()
  detailTimelineSteps.forEach((step) => {
    const valueMs = metricValueFromLog(item, step.key)
    if (valueMs <= 0) return
    const width = Math.max(3, Math.round((valueMs / maxMs) * 100))
    const tone = timelineStepTone(step.key, valueMs, maxMs)
    const category = timelineStepCategory(step.key, step.group)
    const groupSteps = groups.get(step.group) || []
    groupSteps.push({
      ...step,
      valueMs,
      value: formatTimelineMs(valueMs),
      tone,
      category,
      statusLabel: timelineStatusLabel(tone),
      barStyle: { width: `${width}%` },
      time: eventTimeForMetric(item, step.key),
      note: timelineStepNote(item, step),
    })
    groups.set(step.group, groupSteps)
  })
  return detailTimelineGroupOrder
    .map((name) => ({ name, steps: groups.get(name) || [] }))
    .filter((group) => group.steps.length > 0)
})

const timelineDetailsAutoExpanded = computed(() => {
  const item = selectedLog.value
  if (!item) return false
  if (isFailed(item)) return true
  if (Number(item.durationMs || 0) >= 180_000) return true
  if (metricValueFromLog(item, 'stream_error_ms') > 0) return true
  return selectedBottleneckStep.value?.tone === 'danger'
})
const timelineDetailsVisible = computed(() => timelineDetailsExpanded.value)
const selectedHasTimeline = computed(() => selectedTimelineSegments.value.length > 0 || selectedTimelineGroups.value.length > 0)

function toggleTimelineDetails() {
  timelineDetailsExpanded.value = !timelineDetailsExpanded.value
}

const selectedPrimaryDetailFields = computed<DetailField[]>(() => {
  const item = selectedLog.value
  if (!item) return []
  return compactDetailFields([
    { label: '请求 ID', value: rawDetailValue(item, 'call_id') || item.id, copyable: true },
    { label: '接口', value: item.endpoint, copyable: true },
    { label: '模型', value: item.model, copyable: true },
    { label: '账号', value: item.accountEmail, copyable: true },
    { label: '密钥', value: maskKeyLabel([item.keyName, item.keyId].filter(Boolean).join(' / ')) },
    { label: '出口', value: egressDetailValue(item) },
    { label: '会话 ID', value: item.conversationId, copyable: true },
    { label: '时间', value: timeRangeDetailValue(item), wide: true },
  ])
})

const selectedDiagnosticDetailFields = computed<DetailField[]>(() => {
  const item = selectedLog.value
  if (!item) return []
  if (!hasDiagnosticSignal(item)) return []
  const shouldShowBooleans = isFailed(item) || isLimited(item) || Boolean(item.errorCode || item.error || item.reason)
  return compactDetailFields([
    { label: '状态码', value: item.statusCode },
    { label: '错误码', value: item.errorCode, copyable: true },
    { label: '阶段', value: diagnosticStageValue(item), copyable: true },
    { label: '原因', value: item.reason, copyable: true },
    { label: '上游错误', value: item.upstreamErrorType, copyable: true },
    { label: '上游请求 ID', value: item.upstreamRequestId, copyable: true },
    { label: '请求形状', value: item.requestShape, copyable: true },
    shouldShowBooleans ? { label: '工具调用', value: item.toolInvoked } : null,
    shouldShowBooleans ? { label: '阻断', value: item.blocked } : null,
    { label: '上游文本长度', value: item.upstreamMessageLen },
  ])
})

const selectedDetailImages = computed(() => {
  const item = selectedLog.value
  if (!item) return []
  return item.imageUrls.map((url, index) => {
    const sourceUrl = item.urls[index] || url
    return {
      url,
      title: sourceUrl,
      filename: filenameFromUrl(sourceUrl),
      alt: `日志结果图片 ${index + 1}`,
      broken: isPreviewBroken(url),
    }
  })
})

const selectedDetailPreviewFile = computed<GalleryFile | null>(() => {
  const image = selectedDetailPreview.value
  if (!image) return null
  const filename = image.filename || filenameFromUrl(image.title || image.url) || 'log-preview-image'
  return {
    filename,
    path: image.title || image.url,
    url: image.url,
    thumbnail_url: image.url,
    size: 0,
    created_at: '',
    mtime: 0,
    date: '',
    type: 'image',
    expired: false,
    expires_in_seconds: null,
    tags: [],
    storage: 'log',
    local: false,
    webdav: false,
    width: null,
    height: null,
  }
})

function typeLabel(type: string): string {
  if (type === 'call') return '调用日志'
  if (type === 'account') return '账号日志'
  return type || '日志'
}

function tokenLabel(item: LogRow): string {
  return item.keyName || item.keyId || item.accountEmail
}

function summaryText(item: LogRow): string {
  return item.summary || item.error || item.reason || item.preview
}

function statusLabel(item: LogRow): string {
  if (isSuccess(item)) return '成功'
  if (isFailed(item)) return '失败'
  if (isLimited(item)) return '受限'
  return item.status || '记录'
}

function statusTone(item: LogRow): 'success' | 'danger' | 'warning' | 'muted' {
  if (isSuccess(item)) return 'success'
  if (isFailed(item)) return 'danger'
  if (isLimited(item)) return 'warning'
  return 'muted'
}

function detailRecord(item: LogRow): Record<string, any> {
  const detail = item.raw.detail
  return detail && typeof detail === 'object' ? detail : {}
}

function monitorRecord(item: LogRow): Record<string, any> {
  const monitor = detailRecord(item).monitor
  return monitor && typeof monitor === 'object' ? monitor : {}
}

function rawDetailValue(item: LogRow, key: string): string {
  return formatInlineValue(detailRecord(item)[key])
}

function rawMonitorValue(item: LogRow, key: string): string {
  return formatInlineValue(monitorRecord(item)[key])
}

function isErrorStatusCode(value: string): boolean {
  const statusCode = Number(cleanString(value))
  return Number.isFinite(statusCode) && statusCode >= 400
}

function diagnosticStageValue(item: LogRow): string {
  const stage = item.stage || rawMonitorValue(item, 'stage_label') || rawMonitorValue(item, 'stage')
  const normalized = cleanString(stage).toLowerCase()
  if (isSuccess(item) && ['success', 'completed', 'complete', 'done', '完成'].includes(normalized)) return ''
  return stage
}

function hasDiagnosticSignal(item: LogRow): boolean {
  return Boolean(
    isFailed(item)
      || isLimited(item)
      || isErrorStatusCode(item.statusCode)
      || item.errorCode
      || item.error
      || item.reason
      || item.upstreamErrorType
      || item.upstreamRequestId
      || item.blocked === '是'
      || item.toolInvoked === '是'
      || diagnosticStageValue(item),
  )
}

function formatInlineValue(value: unknown): string {
  if (value === undefined || value === null || value === '') return ''
  if (Array.isArray(value)) return value.map(formatInlineValue).filter(Boolean).join(' · ')
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>).filter(([, item]) => item !== undefined && item !== null && item !== '')
    if (!entries.length) return ''
    const primitive = entries.every(([, item]) => !item || ['string', 'number', 'boolean'].includes(typeof item))
    if (primitive && entries.length <= 8) {
      return entries.map(([key, item]) => `${key}: ${formatInlineValue(item)}`).join(' · ')
    }
    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return String(value)
    }
  }
  return String(value).trim()
}

function formatTimelineMs(value: unknown): string {
  const ms = Number(value || 0)
  if (!Number.isFinite(ms) || ms <= 0) return '-'
  if (ms >= 60_000) return `${(ms / 60_000).toFixed(1)}m`
  if (ms >= 10_000) return `${(ms / 1000).toFixed(1)}s`
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)}s`
  return `${Math.round(ms)}ms`
}

function metricFromRecord(record: unknown, key: string): number {
  if (!record || typeof record !== 'object') return 0
  const raw = (record as Record<string, unknown>)[key]
  const parsed = Number(raw || 0)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}

function metricValueFromLog(item: LogRow, key: string): number {
  const detail = detailRecord(item)
  const monitor = monitorRecord(item)
  const values = [
    metricFromRecord(detail.perf, key),
    metricFromRecord(detail.metrics, key),
    metricFromRecord(monitor.metrics, key),
  ]
  const images = monitor.images
  if (images && typeof images === 'object') {
    Object.values(images as Record<string, any>).forEach((image) => {
      if (image && typeof image === 'object') values.push(metricFromRecord(image.metrics, key))
    })
  }
  return Math.max(...values, 0)
}

function timelineStepCategory(key: string, group: string): DetailTimelineCategory {
  if (group === '入口与账号') return 'entry'
  if (group === '上游准备') return 'prepare'
  if (group === 'HTTP 连接') return 'network'
  if (key === 'sse_first_event_ms' || key === 'sse_max_gap_ms' || key === 'sse_last_gap_ms') return 'upstream'
  if (key === 'conversation_stream_ms') return 'upstream'
  if (key === 'resolve_ms') return 'resolve'
  if (key === 'download_ms') return 'download'
  if (key === 'retry_wait_ms') return 'retry'
  return 'response'
}

function timelineStepTone(key: string, valueMs: number, _maxMs: number): DetailTone {
  if (key === 'stream_error_ms') return 'danger'
  const threshold = timelineWarningThresholdMs[key] ?? defaultTimelineWarningThresholdMs
  if (valueMs >= threshold) return 'warning'
  return 'info'
}

function timelineStatusLabel(tone: DetailTone): string {
  if (tone === 'danger') return '异常'
  if (tone === 'warning') return '慢'
  if (tone === 'success') return '完成'
  if (tone === 'info') return '记录'
  return '记录'
}

function durationTone(valueMs: number): DetailTone {
  if (valueMs >= 120_000) return 'warning'
  return 'muted'
}

function eventTimeForMetric(item: LogRow, metricKey: string): string {
  const events = monitorRecord(item).events
  if (!Array.isArray(events)) return ''
  const matched = events.find((event) => event && typeof event === 'object' && Number((event as Record<string, unknown>)[metricKey] || 0) > 0)
  return formatInlineValue((matched as Record<string, unknown> | undefined)?.time)
}

function requestShapeImageSummary(item: LogRow): string {
  const shape = detailRecord(item).request_shape
  if (!shape || typeof shape !== 'object') return ''
  const record = shape as Record<string, unknown>
  const pairs: Array<[string, string]> = [
    ['input_image_parts', '输入图'],
    ['image_url_parts', '图链'],
    ['image_parts', '图片块'],
    ['data_url_images', 'base64'],
    ['remote_image_urls', '远程图'],
    ['literal_image_placeholders', '占位图'],
  ]
  const parts = pairs
    .map(([key, label]) => [label, Number(record[key] || 0)] as const)
    .filter(([, count]) => Number.isFinite(count) && count > 0)
    .map(([label, count]) => `${label} ${count}`)
  return parts.join(' · ')
}

function timelineStepNote(item: LogRow, step: DetailTimelineStepConfig): string {
  const parts = [step.hint || '']
  if (step.key === 'upload_ms') parts.push(requestShapeImageSummary(item))
  if (step.key === 'resolve_ms' && item.imageUrls.length) parts.push(`结果图 ${item.imageUrls.length}`)
  if (step.key === 'download_ms' && item.imageUrls.length) parts.push(`下载 ${item.imageUrls.length} 张`)
  return parts.filter(Boolean).join(' · ')
}

function maskEmail(value: string): string {
  const email = cleanString(value)
  if (!email || !email.includes('@')) return email
  const [name, domain] = email.split('@')
  const masked = name.length <= 2 ? `${name.slice(0, 1)}*` : `${name.slice(0, 2)}***${name.slice(-1)}`
  return `${masked}@${domain}`
}

function maskKeyLabel(value: string): string {
  return cleanString(value).replace(/sk-[A-Za-z0-9_-]{6,}/g, (token) => `${token.slice(0, 5)}***${token.slice(-4)}`)
}

function proxySourceLabel(value: unknown): string {
  const source = cleanString(value)
  if (!source) return ''
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

function egressModeLabel(value: unknown): string {
  const mode = cleanString(value)
  if (!mode) return ''
  if (mode === 'direct') return '直连'
  if (mode === 'single_proxy') return '单代理'
  if (mode === 'proxy_group') return '代理组'
  return mode
}

function egressDetailValue(item: LogRow): string {
  const source = item.proxySource || rawMonitorValue(item, 'proxy_source')
  const hash = item.proxyHash || rawMonitorValue(item, 'proxy_hash')
  const groupId = item.proxyGroupId || rawMonitorValue(item, 'proxy_group_id')
  const nodeName = item.proxyNodeName || rawMonitorValue(item, 'proxy_node_name')
  const nodeId = item.proxyNodeId || rawMonitorValue(item, 'proxy_node_id')
  const egressLabel = item.egressLabel || rawMonitorValue(item, 'egress_label')
  const label = proxySourceLabel(source)
  if (!label) return ''
  const nodeLabel = [groupId, nodeName || nodeId].filter(Boolean).join('/')
  if (nodeLabel) return `${label} ${nodeLabel}`
  if (egressLabel && egressLabel !== 'direct' && !egressLabel.startsWith('proxy:')) return `${label} ${egressLabel}`
  if (hash && hash !== 'direct') return `${label} ${hash}`
  return label
}

function hasDetailValue(value: string): boolean {
  const clean = cleanString(value)
  return Boolean(clean && clean !== '-' && clean.toLowerCase() !== 'null' && clean.toLowerCase() !== 'undefined')
}

function compactDetailFields(fields: Array<DetailField | null>, options: { keepStatus?: boolean } = {}): DetailField[] {
  return fields.filter((field): field is DetailField => {
    if (!field) return false
    if (options.keepStatus && field.label === '状态') return true
    return hasDetailValue(field.value)
  })
}

function timeRangeDetailValue(item: LogRow): string {
  const start = cleanString(item.startedAt || item.time)
  const end = cleanString(item.endedAt)
  if (!start) return end
  if (!end || end === start) return start
  return `${start} → ${end}`
}

function formatRuntimeLogLine(item: RuntimeLog): string {
  const time = cleanString(item.time)
  const level = cleanString(item.level).toUpperCase()
  const source = cleanString(item.source)
  const message = cleanString(item.message) || '-'
  const path = cleanString(item.path)
  return [
    time,
    level,
    source ? `[${source}]` : '',
    message,
    path,
  ].filter(Boolean).join(' ')
}

function updateRuntimeLimit(value: string) {
  const parsed = Number(value)
  runtimeFilters.limit = Number.isFinite(parsed) ? Math.min(Math.max(Math.trunc(parsed), 1), 2000) : DEFAULT_RUNTIME_LOG_LIMIT
}

function loadStoredLogLimits() {
  filters.limit = getNumberPreference(preferenceKeys.systemLogLimit, DEFAULT_SYSTEM_LOG_LIMIT, { min: 1, max: 20000 })
  runtimeFilters.limit = getNumberPreference(preferenceKeys.runtimeLogLimit, DEFAULT_RUNTIME_LOG_LIMIT, { min: 1, max: 2000 })
}

function setActiveLogView(view: LogView) {
  if (activeLogView.value === view) return
  activeLogView.value = view
  if (view === 'runtime' && runtimeLogs.value.length === 0 && !runtimeLoadError.value) {
    void fetchRuntimeLogs()
  }
}

function refreshActiveLogs() {
  if (activeLogView.value === 'runtime') {
    void fetchRuntimeLogs()
    return
  }
  void fetchLogs()
}

function queryValue(value: unknown): string {
  if (Array.isArray(value)) return cleanString(value[0])
  return cleanString(value)
}

function applyRouteQuery() {
  isApplyingRouteQuery = true
  try {
    const query = route.query
    const limit = Number(queryValue(query.limit))
    routeTargetLogId.value = queryValue(query.log_id)
    filters.type = queryValue(query.type) || 'call'
    filters.status = queryValue(query.status)
    filters.endpoint = queryValue(query.endpoint)
    filters.model = queryValue(query.model)
    filters.account = queryValue(query.account)
    filters.conversationId = queryValue(query.conversation_id || query.conversationId)
    filters.search = queryValue(query.search)
    filters.startDate = queryValue(query.start_date || query.startDate)
    filters.endDate = queryValue(query.end_date || query.endDate)
    if (Number.isFinite(limit) && limit > 0) {
      filters.limit = Math.min(Math.max(Math.trunc(limit), 1), 20000)
    }
    currentPage.value = 1
    clearLogSelection()
    if (routeTargetLogId.value) selectedLog.value = null
  } finally {
    isApplyingRouteQuery = false
  }
}

function resetFilters() {
  filters.type = 'call'
  filters.status = ''
  filters.endpoint = ''
  filters.model = ''
  filters.account = ''
  filters.conversationId = ''
  filters.search = ''
  filters.startDate = ''
  filters.endDate = ''
  currentPage.value = 1
  clearLogSelection()
}

function touchSystemFilters() {
  currentPage.value = 1
  clearLogSelection()
}

function advancedConditionOptionValue(key: AdvancedFilterKey, value: string): string {
  return `advanced:${key}:${encodeURIComponent(value)}`
}

function parseAdvancedConditionOptionValue(key: string): { conditionKey: AdvancedFilterKey; value: string } | null {
  const match = key.match(/^advanced:(type|status|model|account):(.*)$/)
  if (!match) return null
  return {
    conditionKey: match[1] as AdvancedFilterKey,
    value: decodeURIComponent(match[2] || ''),
  }
}

function latestAdvancedConditionValue(values: string[], key: AdvancedFilterKey): string | null {
  const matched = values
    .map(parseAdvancedConditionOptionValue)
    .filter((item): item is { conditionKey: AdvancedFilterKey; value: string } => Boolean(item && item.conditionKey === key))
  if (matched.length === 0) return null
  return matched[matched.length - 1].value
}

function updateAdvancedConditions(value: string | string[]) {
  const values = Array.isArray(value) ? value : value ? [value] : []
  filters.type = latestAdvancedConditionValue(values, 'type') ?? 'call'
  filters.status = latestAdvancedConditionValue(values, 'status') ?? ''
  filters.model = latestAdvancedConditionValue(values, 'model') ?? ''
  filters.account = latestAdvancedConditionValue(values, 'account') ?? ''
  touchSystemFilters()
}

function latestQuickEndpointValue(values: string[]): string | null {
  const matched = values
    .filter((item) => item.startsWith('quick:endpoint:'))
    .map((item) => item.slice('quick:endpoint:'.length))
  return matched.length ? matched[matched.length - 1] : null
}

function updateSystemQuickFilters(value: string | string[]) {
  const values = Array.isArray(value) ? value : value ? [value] : []
  const hasFailedFilter = values.includes('quick:status:failed')
  const endpoint = latestQuickEndpointValue(values)

  if (hasFailedFilter) {
    filters.status = 'failed'
  } else if (filters.status === 'failed') {
    filters.status = ''
  }

  if (endpoint) {
    filters.endpoint = endpoint
  } else if ((quickEndpointValues as readonly string[]).includes(filters.endpoint)) {
    filters.endpoint = ''
  }

  touchSystemFilters()
}

function handleRuntimeFilterMenuSelect(key: string) {
  if (key.startsWith('runtime-level:')) {
    runtimeFilters.level = key.slice('runtime-level:'.length)
  } else if (key.startsWith('runtime-source:')) {
    runtimeFilters.source = key.slice('runtime-source:'.length)
  } else if (key === 'runtime-clear:level') {
    runtimeFilters.level = ''
  } else if (key === 'runtime-clear:source') {
    runtimeFilters.source = ''
  }
}

function openDetail(item: LogRow) {
  selectedLog.value = item
}

function closeDetail() {
  selectedLog.value = null
  selectedDetailPreview.value = null
}

function openDetailImagePreview(image: DetailPreviewImage) {
  selectedDetailPreview.value = image
}

async function downloadLogPreviewFile(file: GalleryFile) {
  try {
    await downloadUrlAsFile(resolveGalleryFileUrl(file.url), file.filename, { localPath: file.path })
  } catch (error: any) {
    toast.error(`下载失败：${error?.message || '图片源不可读取'}`)
  }
}

async function copyLogPreviewFile(file: GalleryFile | null) {
  if (!file) return
  const url = resolveGalleryFileUrl(file.url)
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(url)
    } else {
      const input = document.createElement('input')
      input.value = url
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      document.body.removeChild(input)
    }
    copiedLogPreviewKey.value = file.path
    if (logPreviewCopyResetTimer !== null) {
      window.clearTimeout(logPreviewCopyResetTimer)
    }
    logPreviewCopyResetTimer = window.setTimeout(() => {
      copiedLogPreviewKey.value = ''
      logPreviewCopyResetTimer = null
    }, 1800)
    toast.success('图片链接已复制。', '复制成功')
  } catch {
    copiedLogPreviewKey.value = ''
    toast.error('复制图片链接失败。', '复制失败')
  }
}

function isLogSelected(id: string): boolean {
  return selectedLogIdSet.value.has(id)
}

function toggleLogSelection(id: string, checked?: boolean) {
  const next = new Set(selectedLogIds.value)
  const shouldSelect = typeof checked === 'boolean' ? checked : !next.has(id)
  if (shouldSelect) next.add(id)
  else next.delete(id)
  selectedLogIds.value = Array.from(next)
}

function toggleSelectAllVisibleLogs(checked?: boolean) {
  const next = new Set(selectedLogIds.value)
  const shouldSelect = typeof checked === 'boolean' ? checked : !allVisibleLogsSelected.value
  visibleLogs.value.forEach((item) => {
    if (shouldSelect) next.add(item.id)
    else next.delete(item.id)
  })
  selectedLogIds.value = Array.from(next)
}

function clearLogSelection() {
  selectedLogIds.value = []
}

function requestDeleteLog(item: LogRow) {
  deleteTarget.value = item
}

function requestDeleteSelectedLogs() {
  if (selectedLogCount.value === 0) return
  deleteSelectedOpen.value = true
}

async function copyText(value: string) {
  const text = cleanString(value)
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    toast.success('已复制')
  } catch {
    toast.error('复制失败')
  }
}

async function fetchLogs() {
  if (isFetching.value) return
  isFetching.value = true
  logsLoadError.value = ''
  try {
    const response = await logsApi.listSystem({
      type: filters.type || undefined,
      start_date: filters.startDate || undefined,
      end_date: filters.endDate || undefined,
      status: filters.status || undefined,
      endpoint: filters.endpoint || undefined,
      model: filters.model || undefined,
      account: filters.account || undefined,
      conversation_id: filters.conversationId || undefined,
      search: filters.search || undefined,
      limit: filters.limit,
      offset: (currentPage.value - 1) * filters.limit,
    })
    logs.value = response.items.map((item, index) => normalizeSystemLogRow(item, index, { apiBaseUrl }))
    const visibleIds = new Set(logs.value.map((item) => item.id))
    selectedLogIds.value = selectedLogIds.value.filter((id) => visibleIds.has(id))
    const targetId = routeTargetLogId.value
    if (targetId) {
      const targetLog = logs.value.find((item) => item.id === targetId)
      if (targetLog) selectedLog.value = targetLog
    }
    logMeta.total = response.total
    logMeta.limit = response.limit
    logMeta.offset = response.offset
    logMeta.has_more = response.has_more
    logMeta.facets_scope = response.facets_scope
    logMeta.stats_scope = response.stats_scope
    logMeta.total_scope = response.total_scope
    logMeta.facets = response.facets
    logMeta.stats = response.stats
  } catch (error: any) {
    logsLoadError.value = error.message || '日志加载失败'
    toast.error(logsLoadError.value)
  } finally {
    isFetching.value = false
  }
}

async function fetchRuntimeLogs() {
  if (runtimeFetching.value) return
  runtimeFetching.value = true
  runtimeLoadError.value = ''
  try {
    const response = await logsApi.listRuntime({
      level: runtimeFilters.level || undefined,
      source: runtimeFilters.source || undefined,
      search: runtimeFilters.search || undefined,
      limit: runtimeFilters.limit,
    })
    runtimeLogs.value = response.items
    runtimeMeta.items = response.items
    runtimeMeta.total = response.total
    runtimeMeta.limit = response.limit
    runtimeMeta.sources = response.sources
  } catch (error: any) {
    runtimeLoadError.value = error.message || '运行日志加载失败'
    toast.error(runtimeLoadError.value)
  } finally {
    runtimeFetching.value = false
  }
}

function saveJsonBlob(payload: unknown, filename: string) {
  const blob = new Blob(
    [JSON.stringify(payload, null, 2)],
    { type: 'application/json' },
  )
  saveBlob(blob, filename)
}

function exportLogs() {
  saveJsonBlob(
    { exported_at: new Date().toISOString(), page: currentPage.value, total: logMeta.total, logs: logs.value.map((item) => item.raw) },
    `logs_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`,
  )
}

function exportRuntimeLogs() {
  saveJsonBlob(
    { exported_at: new Date().toISOString(), total: runtimeMeta.total, logs: runtimeLogs.value },
    `runtime_logs_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`,
  )
}

function exportActiveLogs() {
  if (activeLogView.value === 'runtime') {
    exportRuntimeLogs()
    return
  }
  exportLogs()
}

async function deleteLog() {
  const item = deleteTarget.value
  if (!item) return
  deleteTarget.value = null
  isDeleting.value = true
  operationProgress.open = true
  operationProgress.title = '删除日志'
  operationProgress.subtitle = item.time || item.id
  operationProgress.total = 1
  operationProgress.current = 0
  operationProgress.statusLabel = '已提交'
  operationProgress.message = '正在提交删除请求...'
  operationProgress.error = ''
  operationProgress.busy = true
  try {
    await logsApi.delete([item.id])
    operationProgress.current = 1
    operationProgress.statusLabel = '已处理'
    operationProgress.message = '删除完成，正在刷新列表...'
    if (selectedLog.value?.id === item.id) selectedLog.value = null
    selectedLogIds.value = selectedLogIds.value.filter((id) => id !== item.id)
    toast.success('日志已删除')
    await fetchLogs()
    operationProgress.message = '日志已删除'
  } catch (error: any) {
    operationProgress.error = error.message || '删除失败'
    toast.error(operationProgress.error)
  } finally {
    isDeleting.value = false
    operationProgress.busy = false
  }
}

async function deleteSelectedLogs() {
  const ids = selectedDeletableLogIds.value
  if (ids.length === 0) {
    deleteSelectedOpen.value = false
    return
  }
  deleteSelectedOpen.value = false
  isDeleting.value = true
  operationProgress.open = true
  operationProgress.title = '批量删除日志'
  operationProgress.subtitle = `已选择 ${ids.length} 条`
  operationProgress.total = ids.length
  operationProgress.current = 0
  operationProgress.statusLabel = '已提交'
  operationProgress.message = '正在提交批量删除请求...'
  operationProgress.error = ''
  operationProgress.busy = true
  try {
    const result = await logsApi.delete(ids)
    operationProgress.current = Number(result.removed ?? ids.length)
    operationProgress.statusLabel = '已处理'
    operationProgress.message = '删除完成，正在刷新列表...'
    if (selectedLog.value && ids.includes(selectedLog.value.id)) selectedLog.value = null
    clearLogSelection()
    toast.success(`已删除 ${result.removed ?? ids.length} 条日志`)
    await fetchLogs()
    operationProgress.message = `已删除 ${result.removed ?? ids.length} 条日志`
  } catch (error: any) {
    operationProgress.error = error.message || '删除失败'
    toast.error(operationProgress.error)
  } finally {
    isDeleting.value = false
    operationProgress.busy = false
  }
}

function scheduleAutoRefresh() {
  if (autoRefreshTimer) window.clearTimeout(autoRefreshTimer)
  if (!autoRefreshEnabled.value || activeLogView.value !== 'runtime') return
  autoRefreshTimer = window.setTimeout(async () => {
    await fetchRuntimeLogs()
    scheduleAutoRefresh()
  }, 8000)
}

function scheduleFilterFetch() {
  if (activeLogView.value !== 'system') return
  if (isApplyingRouteQuery) return
  if (filterFetchTimer) window.clearTimeout(filterFetchTimer)
  filterFetchTimer = window.setTimeout(() => {
    if (currentPage.value === 1) {
      void fetchLogs()
      return
    }
    currentPage.value = 1
  }, 250)
}

function toggleAutoRefresh() {
  autoRefreshEnabled.value = !autoRefreshEnabled.value
  scheduleAutoRefresh()
}

watch(
  () => [
    filters.type,
    filters.status,
    filters.endpoint,
    filters.model,
    filters.account,
    filters.conversationId,
    filters.search,
    filters.startDate,
    filters.endDate,
    filters.limit,
  ],
  scheduleFilterFetch,
)

watch(currentPage, () => {
  if (activeLogView.value === 'system') void fetchLogs()
})

watch(
  () => filters.limit,
  (limit) => {
    setNumberPreference(preferenceKeys.systemLogLimit, limit)
  },
)

watch(
  () => runtimeFilters.limit,
  (limit) => {
    setNumberPreference(preferenceKeys.runtimeLogLimit, limit)
  },
)

watch(autoRefreshEnabled, scheduleAutoRefresh)

watch(activeLogView, () => {
  scheduleAutoRefresh()
})

watch(
  () => selectedLog.value?.id || '',
  () => {
    timelineDetailsExpanded.value = timelineDetailsAutoExpanded.value
  },
)

watch(
  () => [
    runtimeFilters.level,
    runtimeFilters.source,
    runtimeFilters.search,
    runtimeFilters.limit,
  ],
  () => {
    if (activeLogView.value !== 'runtime') return
    if (filterFetchTimer) window.clearTimeout(filterFetchTimer)
    filterFetchTimer = window.setTimeout(() => {
      void fetchRuntimeLogs()
    }, 250)
  },
)

watch(
  () => route.query,
  () => {
    applyRouteQuery()
    void fetchLogs()
  },
  { deep: true },
)

onMounted(() => {
  loadStoredLogLimits()
  applyRouteQuery()
  void fetchLogs()
})

onBeforeUnmount(() => {
  if (autoRefreshTimer) window.clearTimeout(autoRefreshTimer)
  if (filterFetchTimer) window.clearTimeout(filterFetchTimer)
  if (logPreviewCopyResetTimer) window.clearTimeout(logPreviewCopyResetTimer)
})
</script>

<style scoped>
.log-control-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

:deep(.log-search-input) {
  min-width: min(100%, 18rem);
  flex: 1 1 22rem;
}

.log-date-pair {
  --date-range-flex: 0 0 auto;
  --date-range-min-width: 0;
  --date-range-input-min-width: 9.25rem;
}

.log-filter-select {
  flex: 0 0 auto;
}

.log-detail-summary {
  display: flex;
  flex-direction: column;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background:
    linear-gradient(180deg, hsl(var(--muted) / 0.34), transparent 72%),
    hsl(var(--card));
  padding: 12px 14px;
}

.log-detail-summary__main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.log-detail-summary__copy {
  min-width: 0;
}

.log-detail-summary__title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.log-detail-summary__title {
  margin-top: 8px;
  overflow-wrap: anywhere;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.55;
  color: hsl(var(--foreground));
}

.log-detail-summary__duration {
  display: flex;
  min-width: 5.5rem;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  text-align: right;
}

.log-detail-summary__duration span {
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.log-detail-summary__duration strong {
  font-size: 20px;
  font-weight: 650;
  color: hsl(var(--foreground));
}

.detail-field-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-field-section {
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  background: hsl(var(--card));
  padding: 12px;
}

.detail-field-section__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  color: hsl(var(--foreground));
  font-size: 12px;
  font-weight: 600;
}

.detail-field-section__header--muted {
  color: hsl(var(--muted-foreground));
}

.detail-field-grid {
  display: grid;
  gap: 8px;
}

.detail-field-grid--diagnostic {
  gap: 6px;
}

.detail-field-grid__item--wide {
  grid-column: 1 / -1;
}

.detail-field-grid > .detail-field-grid__item--wide.detail-field-card--row {
  grid-template-columns: 4.8rem minmax(0, 1fr);
}

.detail-timeline {
  display: flex;
  flex-direction: column;
  gap: 14px;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--card));
  padding: 14px;
}

.detail-timeline__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.detail-timeline__title {
  font-size: 13px;
  font-weight: 650;
  color: hsl(var(--foreground));
}

.detail-timeline__header p {
  margin-top: 3px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.detail-timeline__meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.detail-timeline-segments {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-timeline-segments__track {
  display: flex;
  height: 28px;
  min-height: 28px;
  gap: 2px;
  overflow: hidden;
  border-radius: 8px;
  background: hsl(var(--muted) / 0.72);
  padding: 3px;
}

.detail-timeline-segments__segment {
  position: relative;
  display: flex;
  min-width: 6px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  overflow: hidden;
  border-radius: 5px;
  background: hsl(var(--muted-foreground) / 0.45);
  color: rgb(255 255 255 / 0.96);
  padding: 0 8px;
  white-space: nowrap;
}

.detail-timeline-segments__segment + .detail-timeline-segments__segment {
  border-left: 0;
}

.detail-timeline-segments__segment span,
.detail-timeline-segments__segment strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.detail-timeline-segments__segment span {
  font-size: 12px;
  font-weight: 600;
}

.detail-timeline-segments__segment strong {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  font-weight: 750;
}

.detail-timeline-segments__segment--muted,
.detail-timeline-segments__segment--info {
  background: hsl(var(--muted-foreground) / 0.48);
}

.detail-timeline-segments__segment--compact {
  padding: 0;
}

.detail-timeline-segments__segment--compact span,
.detail-timeline-segments__segment--compact strong {
  display: none;
}

.detail-timeline-segments__segment--entry {
  background: rgb(96 165 250 / 0.74);
}

.detail-timeline-segments__segment--prepare {
  background: rgb(20 184 166 / 0.72);
}

.detail-timeline-segments__segment--network {
  background: rgb(14 165 233 / 0.68);
}

.detail-timeline-segments__segment--upstream {
  background: rgb(99 102 241 / 0.72);
}

.detail-timeline-segments__segment--resolve {
  background: rgb(245 158 11 / 0.58);
  color: rgb(74 45 0);
}

.detail-timeline-segments__segment--download {
  background: rgb(34 197 94 / 0.62);
  color: rgb(4 52 24);
}

.detail-timeline-segments__segment--retry {
  background: rgb(249 115 22 / 0.66);
  color: rgb(68 33 0);
}

.detail-timeline-segments__segment--response {
  background: hsl(var(--muted-foreground) / 0.46);
}

.detail-timeline-segments__segment--warning {
  background: rgb(245 158 11 / 0.84);
  color: rgb(74 45 0);
}

.detail-timeline-segments__segment--danger {
  background: rgb(244 63 94 / 0.86);
  color: rgb(255 255 255 / 0.96);
}

.detail-timeline-segments__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
}

.detail-timeline-segments__legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.detail-timeline-segments__legend-item i {
  height: 7px;
  width: 7px;
  flex: 0 0 auto;
  border-radius: 999px;
  background: hsl(var(--muted-foreground) / 0.54);
}

.detail-timeline-segments__legend-item--entry i {
  background: rgb(96 165 250);
}

.detail-timeline-segments__legend-item--prepare i {
  background: rgb(20 184 166);
}

.detail-timeline-segments__legend-item--network i {
  background: rgb(14 165 233);
}

.detail-timeline-segments__legend-item--upstream i {
  background: rgb(99 102 241);
}

.detail-timeline-segments__legend-item--resolve i {
  background: rgb(245 158 11);
}

.detail-timeline-segments__legend-item--download i {
  background: rgb(34 197 94);
}

.detail-timeline-segments__legend-item--retry i {
  background: rgb(249 115 22);
}

.detail-timeline-segments__legend-item--response i {
  background: hsl(var(--muted-foreground));
}

.detail-timeline-segments__legend-item--state i {
  background: hsl(var(--muted-foreground));
}

.detail-timeline-segments__legend-item--warning i {
  background: rgb(245 158 11);
}

.detail-timeline-segments__legend-item--danger i {
  background: rgb(244 63 94);
}

.detail-timeline__empty {
  border: 1px dashed hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--muted) / 0.25);
  padding: 14px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.detail-timeline__groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-timeline__details {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-timeline__toggle {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--muted) / 0.22);
  padding: 8px 10px;
  text-align: left;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.detail-timeline__toggle:hover {
  background: hsl(var(--muted) / 0.34);
  color: hsl(var(--foreground));
}

.detail-timeline__toggle span {
  font-weight: 600;
  color: hsl(var(--foreground));
}

.detail-timeline__toggle strong {
  font-weight: 600;
}

.detail-timeline__group {
  display: grid;
  grid-template-columns: 5.5rem minmax(0, 1fr);
  gap: 12px;
}

.detail-timeline__group-title {
  padding-top: 5px;
  font-size: 12px;
  font-weight: 600;
  color: hsl(var(--muted-foreground));
}

.detail-timeline__steps {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 9px;
}

.detail-timeline__step {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 4.5rem;
  align-items: start;
  gap: 12px;
}

.detail-timeline__step-main {
  min-width: 0;
}

.detail-timeline__step-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.detail-timeline__step-label {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.detail-timeline__step-time {
  flex: 0 0 auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.detail-timeline__bar {
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: hsl(var(--muted) / 0.48);
  margin-top: 7px;
}

.detail-timeline__bar span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: hsl(var(--muted-foreground) / 0.5);
}

.detail-timeline__step--entry .detail-timeline__bar span {
  background: rgb(96 165 250 / 0.78);
}

.detail-timeline__step--prepare .detail-timeline__bar span {
  background: rgb(20 184 166 / 0.76);
}

.detail-timeline__step--network .detail-timeline__bar span {
  background: rgb(14 165 233 / 0.7);
}

.detail-timeline__step--upstream .detail-timeline__bar span {
  background: rgb(99 102 241 / 0.76);
}

.detail-timeline__step--resolve .detail-timeline__bar span {
  background: rgb(245 158 11 / 0.62);
}

.detail-timeline__step--download .detail-timeline__bar span {
  background: rgb(34 197 94 / 0.68);
}

.detail-timeline__step--retry .detail-timeline__bar span {
  background: rgb(249 115 22 / 0.72);
}

.detail-timeline__step--response .detail-timeline__bar span {
  background: hsl(var(--muted-foreground) / 0.5);
}

.detail-timeline__step--warning .detail-timeline__bar span {
  background: rgb(245 158 11 / 0.84);
}

.detail-timeline__step--danger .detail-timeline__bar span {
  background: rgb(244 63 94 / 0.82);
}

.detail-timeline__step-note {
  margin-top: 6px;
  overflow-wrap: anywhere;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.detail-timeline__step-value {
  padding-top: 1.6rem;
  text-align: right;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 13px;
  font-weight: 650;
  color: hsl(var(--foreground));
}

@media (min-width: 640px) {
  .detail-field-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .log-detail-summary__main,
  .detail-timeline__header {
    flex-direction: column;
  }

  .log-detail-summary__duration {
    align-items: flex-start;
    text-align: left;
  }

  .detail-timeline__group {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .detail-timeline__step {
    grid-template-columns: 1fr;
  }

  .detail-timeline-segments__track {
    height: 22px;
    min-height: 22px;
  }

  .detail-timeline__step-value {
    padding-top: 0;
    text-align: left;
  }
}

</style>
