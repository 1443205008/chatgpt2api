<template>
  <footer ref="composerShellRef" class="studio-composer-shell">
    <input
      ref="fileInputRef"
      type="file"
      accept="image/*"
      multiple
      class="hidden"
      @change="handleFileChange"
    />

    <form
      class="chat-input-panel"
      :class="{ 'is-dragging': isDragging }"
      @submit.prevent="$emit('submit')"
      @dragenter.prevent="isDragging = true"
      @dragover.prevent="isDragging = true"
      @dragleave="handleDragLeave"
      @drop.prevent="handleDrop"
      @click="textareaRef?.focus()"
    >
      <div class="chat-input-panel-shell">
        <div v-if="isEditing" class="chat-editing-bar" @click.stop>
          <div class="chat-editing-info">
            <Icon icon="lucide:pencil" class="h-3.5 w-3.5" />
            <span>正在编辑原消息，发送后会替换该消息并重新生成后续回复。</span>
          </div>
          <button type="button" class="chat-editing-cancel" @click="$emit('cancel-edit')">
            取消
          </button>
        </div>

        <div
          class="chat-input-panel-inner"
          :class="{ 'chat-input-panel-inner-attach': references.length }"
          @click="textareaRef?.focus()"
        >
          <div v-if="mode === 'image' && references.length" class="attach-images">
            <div v-for="(source, index) in references" :key="source.id" class="chat-attachment-preview">
              <button type="button" class="studio-reference-preview" :title="source.name" @click.stop="$emit('preview-reference', source)">
                <img v-if="source.dataUrl" :src="source.dataUrl" :alt="source.name" />
                <Icon v-else icon="lucide:image" class="h-5 w-5" />
              </button>
              <button type="button" class="chat-attachment-remove" :aria-label="`移除 ${source.name}`" @click.stop="$emit('remove-reference', index)">
                <Icon icon="lucide:x" class="h-3.5 w-3.5" />
              </button>
            </div>
          </div>

          <textarea
            ref="textareaRef"
            v-model="textValue"
            class="chat-input custom-scrollbar"
            rows="1"
            :placeholder="placeholderText"
            @input="resizeTextarea"
            @paste="handlePaste"
            @keydown.enter.exact.prevent="$emit('submit')"
          ></textarea>
        </div>

        <div class="chat-input-actions" @click.stop>
          <div class="chat-input-action-row">
            <button
              type="button"
              class="chat-input-action"
              :disabled="isSending"
              @click="$emit('open-prompts')"
            >
              <span class="icon"><Icon icon="lucide:book-open" class="h-3.5 w-3.5" /></span>
              <span class="text">提示词</span>
            </button>

            <button
              v-for="option in modeOptions"
              :key="option.value"
              type="button"
              class="chat-input-action"
              :class="{ 'chat-input-action-active': mode === option.value }"
              @click="modeValue = option.value"
            >
              <span class="icon">
                <Icon :icon="modeIcon(option.value)" class="h-3.5 w-3.5" />
              </span>
              <span class="text">{{ option.label }}</span>
            </button>

            <template v-if="mode === 'chat'">
              <div class="chat-select-wrap">
                <GroupedSelectMenu
                  v-model="chatModelValue"
                  :options="chatModelSelectOptions"
                  selected-indicator="none"
                  placement="top"
                />
              </div>
              <div class="chat-select-wrap chat-select-wrap--effort">
                <GroupedSelectMenu
                  v-model="chatReasoningEffortValue"
                  :options="chatReasoningEffortOptions"
                  selected-indicator="none"
                  placement="top"
                />
              </div>
            </template>

            <template v-else-if="mode === 'image'">
              <button
                type="button"
                class="chat-input-action"
                :class="{ 'chat-input-action-active': references.length }"
                :disabled="isSending"
                @click="fileInputRef?.click()"
              >
                <span class="icon"><Icon icon="lucide:paperclip" class="h-3.5 w-3.5" /></span>
                <span class="text">{{ references.length ? '继续添加' : '参考图' }}</span>
              </button>
              <div class="chat-settings-anchor">
                <button
                  ref="settingsButtonRef"
                  type="button"
                  class="chat-input-action"
                  :class="{ 'chat-input-action-active': settingsOpen }"
                  @click.stop="toggleSettings"
                >
                  <span class="icon"><Icon icon="lucide:sliders-horizontal" class="h-3.5 w-3.5" /></span>
                  <span class="text">{{ imageSummaryLabel }}</span>
                  <Icon icon="lucide:chevron-down" class="h-3.5 w-3.5" />
                </button>

                <div v-if="settingsOpen" class="studio-size-popover" @click.stop>
                  <div class="studio-size-section">
                    <div class="studio-size-label">模型</div>
                    <GroupedSelectMenu
                      v-model="imageModelValue"
                      :options="imageModelSelectOptions"
                      selected-indicator="none"
                      block
                    />
                  </div>
                  <div class="studio-size-section">
                    <div class="studio-size-label">质量</div>
                    <div class="studio-choice-grid is-quality">
                      <button
                        v-for="option in IMAGE_QUALITY_OPTIONS"
                        :key="option.value"
                        type="button"
                        class="studio-choice-button"
                        :class="{ 'is-active': imageForm.quality === option.value }"
                        @click="$emit('update:imageQuality', option.value)"
                      >
                        {{ option.label }}
                      </button>
                    </div>
                  </div>
                  <div class="studio-size-section">
                    <div class="studio-size-label">数量</div>
                    <div class="studio-choice-grid is-count">
                      <button
                        v-for="option in IMAGE_COUNT_OPTIONS"
                        :key="option.value"
                        type="button"
                        class="studio-choice-button"
                        :class="{ 'is-active': imageForm.n === option.value }"
                        @click="$emit('update:imageCount', option.value)"
                      >
                        {{ option.label }}
                      </button>
                    </div>
                  </div>
                  <div class="studio-size-section">
                    <div class="studio-size-label">比例</div>
                    <div class="studio-choice-grid is-ratio">
                      <button
                        v-for="option in ratioOptions"
                        :key="option.value"
                        type="button"
                        class="studio-choice-button"
                        :class="{ 'is-active': selectedRatio === option.value }"
                        @click="selectRatio(option.value)"
                      >
                        {{ option.label }}
                      </button>
                    </div>
                  </div>
                  <div class="studio-size-section">
                    <div class="studio-size-label">分辨率</div>
                    <div class="studio-choice-grid is-resolution">
                      <button
                        v-for="option in resolutionOptions"
                        :key="option.value"
                        type="button"
                        class="studio-choice-button"
                        :class="{ 'is-active': selectedResolution === option.value }"
                        @click="selectResolution(option.value)"
                      >
                        {{ option.label }}
                      </button>
                    </div>
                    <p class="studio-size-current">{{ selectedSizeDetailLabel }}</p>
                  </div>
                </div>
              </div>
              <button
                v-if="references.length"
                type="button"
                class="chat-input-action"
                :disabled="isSending"
                @click="$emit('clear-references')"
              >
                <span class="icon"><Icon icon="lucide:x" class="h-3.5 w-3.5" /></span>
                <span class="text">清空参考</span>
              </button>
            </template>
          </div>

          <div class="chat-input-submit-row">
            <div v-if="references.length" class="chat-input-status">
              <span class="min-w-0 truncate">{{ references.length }} 张参考图</span>
              <span class="chat-input-count">{{ imageForm.n }} 张输出</span>
            </div>
          <button
            v-if="isStreaming"
            type="button"
            class="chat-input-send chat-input-send-danger"
            aria-label="停止输出"
            @click.stop="$emit('stop')"
          >
            <Icon icon="lucide:square" class="h-4 w-4" />
            <span class="chat-input-send-label">停止</span>
          </button>
          <button
            v-else
            type="submit"
            class="chat-input-send"
            :class="text.trim() && !isSending ? 'chat-input-send-ready' : 'chat-input-send-idle'"
            :disabled="isSending || !text.trim()"
            :aria-label="mode === 'image' ? '提交图片任务' : '发送消息'"
            @click.stop
          >
            <Icon :icon="isSending ? 'lucide:loader-circle' : 'lucide:send-horizontal'" class="h-4 w-4" :class="{ 'animate-spin': isSending }" />
            <span class="chat-input-send-label">{{ isEditing ? '保存' : '发送' }}</span>
          </button>
          </div>
        </div>
      </div>

      <div v-if="isDragging" class="studio-drop-overlay">
        <Icon icon="lucide:image-plus" class="h-5 w-5" />
        松开以上传参考图
      </div>
    </form>

  </footer>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import GroupedSelectMenu from '@/components/ui/GroupedSelectMenu.vue'
import {
  DEFAULT_IMAGE_SIZE,
  IMAGE_COUNT_OPTIONS,
  IMAGE_QUALITY_OPTIONS,
  formatImageSizeLabel,
  resolveImageSizePresets,
  type ImageSizeResolution,
} from '@/api/imageTasks'
import type { StudioComposeMode, StudioImageForm, StudioReference } from './types'

const props = defineProps<{
  mode: StudioComposeMode
  text: string
  chatModel: string
  chatReasoningEffort: string
  imageForm: StudioImageForm
  chatModelOptions: string[]
  imageModelOptions: string[]
  references: StudioReference[]
  isSending: boolean
  isStreaming: boolean
  isEditing: boolean
}>()

const emit = defineEmits<{
  'update:mode': [mode: StudioComposeMode]
  'update:text': [text: string]
  'update:chatModel': [model: string]
  'update:chatReasoningEffort': [effort: string]
  'update:imageModel': [model: string]
  'update:imageSize': [size: string]
  'update:imageQuality': [quality: string]
  'update:imageCount': [count: number]
  submit: []
  stop: []
  'cancel-edit': []
  'add-files': [files: File[]]
  'remove-reference': [index: number]
  'clear-references': []
  'preview-reference': [reference: StudioReference]
  'open-prompts': []
}>()

const composerShellRef = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const settingsButtonRef = ref<HTMLButtonElement | null>(null)
const isDragging = ref(false)
const settingsOpen = ref(false)
let textareaResizeFrame = 0
let composerResizeObserver: ResizeObserver | null = null

const modeOptions: Array<{ label: string; value: StudioComposeMode }> = [
  { label: '画图', value: 'image' },
  { label: '对话', value: 'chat' },
  { label: '搜索', value: 'search' },
]

const textValue = computed({
  get: () => props.text,
  set: (value: string) => emit('update:text', value),
})

const modeValue = computed({
  get: () => props.mode,
  set: (value: string | number) => emit('update:mode', normalizeModeValue(value)),
})

const chatModelValue = computed({
  get: () => props.chatModel,
  set: (value: string | string[]) => emit('update:chatModel', String(Array.isArray(value) ? value[0] : value || 'auto')),
})

const chatReasoningEffortValue = computed({
  get: () => props.chatReasoningEffort || 'default',
  set: (value: string | string[]) => {
    const next = String(Array.isArray(value) ? value[0] : value || 'default')
    emit('update:chatReasoningEffort', next === 'default' ? '' : next)
  },
})

function normalizeModeValue(value: string | number): StudioComposeMode {
  if (value === 'chat' || value === 'search' || value === 'image') return value
  return 'image'
}

function modeIcon(mode: StudioComposeMode) {
  if (mode === 'image') return 'lucide:image'
  if (mode === 'search') return 'lucide:search'
  return 'lucide:message-circle'
}

const imageModelValue = computed({
  get: () => props.imageForm.model,
  set: (value: string | string[]) => emit('update:imageModel', String(Array.isArray(value) ? value[0] : value || '')),
})

const chatModelSelectOptions = computed(() => props.chatModelOptions.map((model) => ({
  label: model === 'auto' ? '自动模型' : model,
  value: model,
})))

const chatReasoningEffortOptions = [
  { label: '默认思考', value: 'default' },
  { label: '低', value: 'low' },
  { label: '中', value: 'medium' },
  { label: '高', value: 'high' },
  { label: '超高', value: 'extended' },
]

const imageModelSelectOptions = computed(() => props.imageModelOptions.map((model) => ({
  label: model,
  value: model,
})))

const sizePresets = computed(() => resolveImageSizePresets(props.imageForm.model))
const selectedPreset = computed(() => sizePresets.value.find((preset) => preset.value === props.imageForm.size))
const selectedRatio = computed(() => selectedPreset.value?.ratio || 'auto')
const selectedResolution = computed(() => selectedPreset.value?.resolution || 'auto')
const ratioOptions = computed(() => {
  const seen = new Set<string>()
  return sizePresets.value
    .filter((preset) => {
      if (seen.has(preset.ratio)) return false
      seen.add(preset.ratio)
      return true
    })
    .map((preset) => ({ label: preset.ratio === 'auto' ? '自动' : preset.ratio, value: preset.ratio }))
})
const resolutionOptions = computed(() => {
  const order: ImageSizeResolution[] = ['auto', '1K', '2K', '4K']
  const values = new Set(sizePresets.value.map((preset) => preset.resolution))
  return order.filter((value) => values.has(value)).map((value) => ({ label: value === 'auto' ? '自动' : value, value }))
})
const selectedSizeDetailLabel = computed(() => formatImageSizeLabel(props.imageForm.size))
const imageSummaryLabel = computed(() => {
  const count = props.imageForm.n > 1 ? ` · ${props.imageForm.n} 张` : ''
  return `${formatImageSizeLabel(props.imageForm.size)}${count}`
})
const imagePlaceholder = computed(() => props.references.length ? '描述你想如何修改参考图' : '输入你想生成的画面，也可以粘贴或拖入参考图')
const placeholderText = computed(() => {
  if (props.mode === 'image') return imagePlaceholder.value
  if (props.mode === 'search') return '输入搜索问题，Enter 搜索，Shift+Enter 换行'
  return '输入消息，Enter 发送，Shift+Enter 换行'
})

function toggleSettings() {
  settingsOpen.value = !settingsOpen.value
}

function resizeTextarea() {
  if (typeof window === 'undefined') return
  if (textareaResizeFrame) window.cancelAnimationFrame(textareaResizeFrame)
  textareaResizeFrame = window.requestAnimationFrame(() => {
    textareaResizeFrame = 0
    const element = textareaRef.value
    if (!element) return
    element.style.height = 'auto'
    const maxHeight = Number.parseFloat(window.getComputedStyle(element).maxHeight) || 192
    const nextHeight = Math.min(element.scrollHeight, maxHeight)
    element.style.height = `${nextHeight}px`
    element.style.overflowY = element.scrollHeight > maxHeight + 1 ? 'auto' : 'hidden'
  })
}

function scheduleTextareaResize() {
  void nextTick(resizeTextarea)
}

function syncComposerHeight() {
  const shell = composerShellRef.value
  const parent = shell?.parentElement
  if (!shell || !parent) return
  parent.style.setProperty('--studio-composer-height', `${Math.ceil(shell.offsetHeight)}px`)
}

function selectRatio(ratio: string) {
  const auto = sizePresets.value.find((preset) => preset.value === DEFAULT_IMAGE_SIZE)
  if (ratio === 'auto') {
    emit('update:imageSize', auto?.value || DEFAULT_IMAGE_SIZE)
    return
  }
  const exact = selectedResolution.value !== 'auto'
    ? sizePresets.value.find((preset) => preset.ratio === ratio && preset.resolution === selectedResolution.value)
    : undefined
  const next = exact || sizePresets.value.find((preset) => preset.ratio === ratio) || auto
  emit('update:imageSize', next?.value || DEFAULT_IMAGE_SIZE)
}

function selectResolution(resolution: ImageSizeResolution) {
  const auto = sizePresets.value.find((preset) => preset.value === DEFAULT_IMAGE_SIZE)
  if (resolution === 'auto') {
    emit('update:imageSize', auto?.value || DEFAULT_IMAGE_SIZE)
    return
  }
  const exact = selectedRatio.value !== 'auto'
    ? sizePresets.value.find((preset) => preset.ratio === selectedRatio.value && preset.resolution === resolution)
    : undefined
  const next = exact || sizePresets.value.find((preset) => preset.resolution === resolution) || auto
  emit('update:imageSize', next?.value || DEFAULT_IMAGE_SIZE)
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  emit('add-files', Array.from(input.files || []))
  input.value = ''
}

function handlePaste(event: ClipboardEvent) {
  if (props.mode !== 'image') return
  const files = Array.from(event.clipboardData?.files || []).filter(isImageFile)
  if (!files.length) return
  event.preventDefault()
  emit('add-files', files)
}

function handleDrop(event: DragEvent) {
  isDragging.value = false
  if (props.mode !== 'image') return
  emit('add-files', Array.from(event.dataTransfer?.files || []))
}

function handleDragLeave(event: DragEvent) {
  const current = event.currentTarget as HTMLElement
  if (event.relatedTarget instanceof Node && current.contains(event.relatedTarget)) return
  isDragging.value = false
}

function isImageFile(file: File) {
  return file.type.startsWith('image/') || /\.(avif|bmp|gif|heic|heif|ico|jpe?g|png|svg|tiff?|webp)$/i.test(file.name)
}

function handleOutsideClick(event: MouseEvent) {
  if (!settingsOpen.value) return
  const target = event.target as Node
  if (settingsButtonRef.value?.contains(target)) return
  settingsOpen.value = false
}

if (typeof window !== 'undefined') {
  window.addEventListener('click', handleOutsideClick)
}

onMounted(() => {
  scheduleTextareaResize()
  syncComposerHeight()
  if (typeof ResizeObserver !== 'undefined' && composerShellRef.value) {
    composerResizeObserver = new ResizeObserver(syncComposerHeight)
    composerResizeObserver.observe(composerShellRef.value)
  }
})

watch(
  () => [props.text, props.mode, props.references.length, props.isEditing],
  scheduleTextareaResize,
  { flush: 'post' },
)

onBeforeUnmount(() => {
  if (typeof window === 'undefined') return
  if (textareaResizeFrame) window.cancelAnimationFrame(textareaResizeFrame)
  composerResizeObserver?.disconnect()
  composerResizeObserver = null
  composerShellRef.value?.parentElement?.style.removeProperty('--studio-composer-height')
  window.removeEventListener('click', handleOutsideClick)
})
</script>

<style scoped>
.studio-composer-shell {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 20;
  width: 100%;
  background: transparent;
  flex: 0 0 auto;
  pointer-events: none;
}

.studio-composer-shell::before {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 3.65rem;
  pointer-events: none;
  background: hsl(var(--card));
  content: '';
}

.chat-input-panel {
  position: relative;
  z-index: 1;
  width: 100%;
  box-sizing: border-box;
  background: transparent;
  padding: 0.35rem 1rem 0.55rem;
  pointer-events: none;
  transition: border-color 0.15s, background 0.15s;
}

.chat-input-panel.is-dragging {
  pointer-events: auto;
  background: hsl(var(--secondary) / 0.72);
}

.chat-input-panel-shell {
  position: relative;
  z-index: 1;
  display: flex;
  width: min(100%, 48rem);
  margin: 0 auto;
  flex-direction: column;
  gap: 0.6rem;
  border: 1px solid hsl(var(--border) / 0.82);
  border-radius: 1.4rem;
  background: hsl(var(--background));
  padding: 0.55rem;
  pointer-events: auto;
}

.chat-editing-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  border: 1px solid hsl(var(--primary) / 0.18);
  border-radius: 1rem;
  background: hsl(var(--primary) / 0.07);
  padding: 0.45rem 0.65rem;
  color: hsl(var(--foreground));
  font-size: 0.78rem;
}

.chat-editing-info {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 0.45rem;
}

.chat-editing-info span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-editing-cancel {
  flex: 0 0 auto;
  border: 0;
  background: transparent;
  color: hsl(var(--primary));
  font-size: 0.76rem;
  font-weight: 700;
  cursor: pointer;
}

.chat-input-actions {
  display: flex;
  min-height: 2.25rem;
  align-items: flex-end;
  justify-content: space-between;
  gap: 0.75rem;
  border-top: 1px solid hsl(var(--border) / 0.52);
  padding-top: 0.55rem;
}

.chat-input-action-row {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.375rem;
}

.chat-settings-anchor {
  position: relative;
  display: inline-flex;
}

.chat-input-action {
  display: inline-flex;
  box-sizing: border-box;
  min-height: 2rem;
  align-items: center;
  justify-content: center;
  gap: 0.3125rem;
  overflow: hidden;
  border: 1px solid transparent;
  border-radius: 999px;
  background: hsl(var(--secondary) / 0.58);
  color: hsl(var(--muted-foreground));
  padding: 0.3rem 0.7rem;
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1rem;
  transition: border-color 0.15s, background 0.15s, color 0.15s;
}

.chat-input-action:hover,
.chat-input-action:focus-visible,
.chat-input-action-active {
  border-color: hsl(var(--foreground) / 0.22);
  background: hsl(var(--secondary));
  color: hsl(var(--foreground));
}

.chat-input-action:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.chat-input-action .icon {
  display: inline-flex;
  width: 1rem;
  height: 1rem;
  flex: 0 0 1rem;
  align-items: center;
  justify-content: center;
}

.chat-input-action .text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-select-wrap {
  display: inline-flex;
  min-width: 0;
  max-width: min(18rem, 45vw);
}

.chat-select-wrap--effort {
  min-width: 0;
  max-width: 9rem;
}

.chat-input-status {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
  color: hsl(var(--muted-foreground));
  font-size: 0.6875rem;
}

.chat-input-submit-row {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
}

.chat-input-count {
  flex: 0 0 auto;
  border: 1px solid hsl(var(--border) / 0.64);
  border-radius: 999px;
  background: hsl(var(--secondary) / 0.48);
  padding: 0.125rem 0.5rem;
  color: hsl(var(--muted-foreground));
  font-weight: 650;
}

.chat-input-panel-inner {
  position: relative;
  display: block;
  min-height: 2.7rem;
  cursor: text;
  border: 0;
  border-radius: 1rem;
  background: transparent;
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
}

.chat-input-panel-inner:focus-within {
  background: transparent;
  box-shadow: none;
}

.chat-input-panel-inner-attach {
  min-height: 7.5rem;
}

.chat-input {
  width: 100%;
  height: 2.7rem;
  min-height: 2.7rem;
  max-height: 8.5rem;
  resize: none;
  overflow-y: hidden;
  border: 0;
  border-radius: 1rem;
  background: transparent;
  padding: 0.15rem 0.25rem 0.15rem 0.25rem;
  color: hsl(var(--foreground));
  font-family: inherit;
  font-size: 0.9375rem;
  line-height: 1.45;
  outline: none;
}

.chat-input-panel-inner-attach .chat-input {
  min-height: 2.7rem;
  padding-top: 0.15rem;
  padding-bottom: 0.2rem;
}

.chat-input::placeholder {
  color: hsl(var(--muted-foreground) / 0.62);
  font-family: inherit;
  font-weight: 400;
  letter-spacing: 0;
  opacity: 1;
}

.attach-images {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  overflow-x: auto;
  overflow-y: hidden;
  margin-bottom: 0.45rem;
  padding: 0.1rem 0 0.15rem;
}

.chat-attachment-preview {
  position: relative;
  width: 4rem;
  height: 4rem;
  flex: 0 0 auto;
  overflow: hidden;
  border: 1px solid hsl(var(--border));
  border-radius: 1rem;
  background: hsl(var(--card));
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
}

.studio-reference-preview {
  display: flex;
  width: 100%;
  height: 100%;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: hsl(var(--secondary) / 0.65);
  color: hsl(var(--muted-foreground));
}

.studio-reference-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.chat-attachment-remove {
  position: absolute;
  top: 0.25rem;
  right: 0.25rem;
  display: inline-flex;
  width: 1.5rem;
  height: 1.5rem;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgb(15 23 42 / 0.72);
  color: white;
  opacity: 0;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.12);
  transition: opacity 0.15s, background 0.15s;
}

.chat-attachment-preview:hover .chat-attachment-remove,
.chat-attachment-remove:focus-visible {
  opacity: 1;
}

.chat-attachment-remove:hover {
  background: rgb(220 38 38);
}

.chat-input-send {
  display: inline-flex;
  width: 2.35rem;
  height: 2.35rem;
  flex: 0 0 2.35rem;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 0;
  font: inherit;
  font-size: 0.75rem;
  font-weight: 650;
  line-height: 1;
  outline: none;
  box-shadow: 0 10px 24px -18px rgb(15 23 42 / 0.84);
  transition: transform 0.15s, border-color 0.15s, background 0.15s, color 0.15s, opacity 0.15s, box-shadow 0.15s;
}

.chat-input-send:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.chat-input-send-ready {
  background: hsl(var(--foreground));
  color: hsl(var(--background));
}

.chat-input-send-idle {
  border-color: hsl(var(--border) / 0.72);
  background: hsl(var(--secondary) / 0.78);
  color: hsl(var(--muted-foreground));
  box-shadow: none;
}

.chat-input-send-ready:hover,
.chat-input-send-ready:focus-visible {
  background: hsl(var(--foreground) / 0.88);
  box-shadow: 0 14px 28px -18px rgb(15 23 42 / 0.96);
  transform: translateY(-1px);
}

.chat-input-send-danger {
  border-color: rgb(248 113 113 / 0.32);
  background: rgb(254 242 242);
  color: rgb(220 38 38);
}

.chat-input-send-label {
  display: none;
}

.studio-size-popover {
  position: absolute;
  z-index: 260;
  right: 0;
  bottom: calc(100% + 0.5rem);
  width: min(28rem, calc(100vw - 3rem));
  max-height: min(34rem, calc(100dvh - 8rem));
  overflow-y: auto;
  border: 1px solid hsl(var(--border));
  border-radius: 1rem;
  background: hsl(var(--card));
  padding: 0.9rem;
  box-shadow: var(--shadow-floating);
}

.studio-size-section + .studio-size-section {
  margin-top: 0.85rem;
}

.studio-size-label {
  margin-bottom: 0.45rem;
  color: hsl(var(--muted-foreground));
  font-size: 0.75rem;
  font-weight: 700;
}

.studio-choice-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.45rem;
}

.studio-choice-grid.is-ratio {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.studio-choice-button {
  min-height: 2.125rem;
  border: 1px solid hsl(var(--border));
  border-radius: 999px;
  background: hsl(var(--background));
  color: hsl(var(--muted-foreground));
  font-size: 0.8125rem;
  font-weight: 600;
  transition: border-color 0.15s, background 0.15s, color 0.15s;
}

.studio-choice-button:hover,
.studio-choice-button.is-active {
  border-color: hsl(var(--foreground) / 0.22);
  background: hsl(var(--foreground));
  color: hsl(var(--background));
}

.studio-size-current {
  margin-top: 0.5rem;
  color: hsl(var(--muted-foreground));
  font-size: 0.75rem;
}

.studio-drop-overlay {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  background: hsl(var(--card) / 0.92);
  color: hsl(var(--foreground));
  font-size: 0.875rem;
  font-weight: 700;
  backdrop-filter: blur(8px);
}

@media (max-width: 720px) {
  .chat-input-panel {
    padding: 0.35rem 0.625rem 0.5rem;
  }

  .chat-input-panel-shell {
    border-radius: 1.2rem;
    padding: 0.5rem;
  }

  .chat-input-actions {
    align-items: flex-start;
    flex-direction: column;
    gap: 0.55rem;
  }

  .chat-input-action-row {
    width: 100%;
    flex-wrap: nowrap;
    overflow-x: auto;
    padding-bottom: 0.125rem;
  }

  .chat-input-status {
    width: 100%;
    justify-content: space-between;
  }

  .chat-input-submit-row {
    width: 100%;
    justify-content: space-between;
  }

  .chat-select-wrap {
    min-width: 8rem;
  }

  .studio-size-popover {
    position: fixed;
    right: 1rem;
    bottom: 5.75rem;
    left: 1rem;
    width: auto;
    max-height: min(30rem, calc(100dvh - 7rem));
  }

  .studio-choice-grid,
  .studio-choice-grid.is-ratio {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .chat-input {
    height: 3rem;
    min-height: 3rem;
    max-height: 7.5rem;
    padding-right: 0.25rem;
    font-size: 1rem;
  }

  .chat-input-panel-inner {
    min-height: 3rem;
  }

  .chat-input-panel-inner-attach {
    min-height: 8.5rem;
  }

  .attach-images {
    width: 100%;
  }
}
</style>
