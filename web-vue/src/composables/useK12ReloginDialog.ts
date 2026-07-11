import { ref } from 'vue'
import { serializeProxyReference } from '@/api/proxy'
import type { ProxyGroup } from '@/api/proxy'

export type K12ReloginParams = {
  workspaceId: string
  proxy: string
}

export type K12ReloginProxyMode = 'global' | 'direct' | 'group' | 'custom'

// Global singleton state: all callers share the same dialog instance.
const open = ref(false)
const proxyGroups = ref<ProxyGroup[]>([])
const workspaceId = ref('')
const proxyMode = ref<K12ReloginProxyMode>('global')
const selectedProxyGroupId = ref('')
const customProxyInput = ref('')

let resolver: ((value: K12ReloginParams | null) => void) | null = null

export const k12ReloginProxyModeOptions = [
  { label: '使用默认代理', value: 'global' },
  { label: '强制直连', value: 'direct' },
  { label: '代理组（多节点）', value: 'group' },
  { label: '自定义代理', value: 'custom' },
] as const

export function useK12ReloginDialog() {
  function ask(groups: ProxyGroup[]) {
    return new Promise<K12ReloginParams | null>((resolve) => {
      proxyGroups.value = groups
      workspaceId.value = ''
      proxyMode.value = 'global'
      selectedProxyGroupId.value = ''
      customProxyInput.value = ''
      open.value = true
      resolver = resolve
    })
  }

  function confirm() {
    if (!workspaceId.value.trim()) return
    open.value = false
    const proxy = buildProxyValue()
    resolver?.({ workspaceId: workspaceId.value.trim(), proxy })
    resolver = null
  }

  function cancel() {
    open.value = false
    resolver?.(null)
    resolver = null
  }

  function setProxyMode(mode: string) {
    proxyMode.value = (['global', 'direct', 'group', 'custom'].includes(mode)
      ? mode
      : 'global') as K12ReloginProxyMode
  }

  function selectProxyGroup(groupId: string) {
    selectedProxyGroupId.value = groupId.trim()
    proxyMode.value = 'group'
  }

  function setCustomProxyInput(value: string) {
    customProxyInput.value = value.trim()
    proxyMode.value = 'custom'
  }

  function buildProxyValue(): string {
    if (proxyMode.value === 'direct') return serializeProxyReference('direct')
    if (proxyMode.value === 'group') return serializeProxyReference('group', selectedProxyGroupId.value)
    if (proxyMode.value === 'custom') return serializeProxyReference('custom', customProxyInput.value)
    return ''
  }

  const proxyGroupOptions = () => {
    const rows = proxyGroups.value.map((group) => ({
      label: `${group.enabled === false ? '停用 · ' : ''}${group.name || group.id}${Array.isArray(group.nodes) ? ` · ${group.nodes.length} 个节点` : ''}`,
      value: group.id,
    }))
    return [{ label: '选择代理组', value: '' }, ...rows]
  }

  return {
    open,
    workspaceId,
    proxyMode,
    selectedProxyGroupId,
    customProxyInput,
    k12ReloginProxyModeOptions,
    proxyGroupOptions,
    ask,
    confirm,
    cancel,
    setProxyMode,
    selectProxyGroup,
    setCustomProxyInput,
  }
}
