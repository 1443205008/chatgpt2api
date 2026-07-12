import { ref } from 'vue'

import { accountsApi } from '@/api/accounts'
import { accountImportsApi } from '@/api/accountImports'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'
import type { useAccountBulkProgressRuntime } from './accountBulkProgressRuntime'

export type AccountImportMode = 'oauth_login' | 'access_token' | 'session_json' | 'cpa_json' | 'remote_cpa' | 'sub2api' | 'totp_csv'

const IMPORT_BATCH_SIZE = 20

type AccountImportRuntimeOptions = {
  bulkProgress: ReturnType<typeof useAccountBulkProgressRuntime>
  normalizeErrorMessage: (error: unknown) => string
  setError: (prefix: string, error: unknown, notify?: boolean) => void
  loadData: (options?: { silentErrorToast?: boolean }) => Promise<void>
}

function uniqueTokens(tokens: string[]) {
  return Array.from(new Set(tokens.map((token) => token.trim()).filter(Boolean)))
}

function parseTokenLines(text: string) {
  return uniqueTokens(
    text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#')),
  )
}

function parseSessionJsonTokens(rawText: string) {
  const text = rawText.trim()
  if (!text) throw new Error('请先粘贴 Session JSON')
  const parsed = JSON.parse(text)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Session JSON 格式不正确')
  }
  const source = parsed as Record<string, unknown>
  const token = String(source.accessToken || source.access_token || '').trim()
  if (!token) throw new Error('Session JSON 中没有找到 accessToken')
  return [token]
}

function tokenFromCPAAccount(value: unknown): string {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return ''
  const source = value as Record<string, unknown>
  return String(source.access_token || source.accessToken || '').trim()
}

function parseCPAJsonTokens(rawText: string, label: string) {
  const text = rawText.trim()
  if (!text) throw new Error(`${label} 是空文件`)
  const parsed = JSON.parse(text)
  const candidates: unknown[] = []

  if (Array.isArray(parsed)) {
    candidates.push(...parsed)
  } else if (parsed && typeof parsed === 'object') {
    if (tokenFromCPAAccount(parsed)) {
      candidates.push(parsed)
    } else {
      const source = parsed as Record<string, unknown>
      for (const key of ['accounts', 'items', 'data', 'results']) {
        const rows = source[key]
        if (Array.isArray(rows)) candidates.push(...rows)
      }
    }
  }

  const tokens = uniqueTokens(candidates.map(tokenFromCPAAccount).filter(Boolean))
  if (!tokens.length) throw new Error(`${label} 中没有找到 access_token`)
  return tokens
}

export function useAccountImportRuntime(options: AccountImportRuntimeOptions) {
  const importBusy = ref(false)
  const showImportModal = ref(false)
  const importMode = ref<AccountImportMode>('access_token')
  const oauthEmailHint = ref('')
  const oauthCallbackText = ref('')
  const oauthSessionId = ref('')
  const oauthAuthorizeUrl = ref('')
  const oauthRedirectUriPrefix = ref('')
  const manualTokenText = ref('')
  const sessionJsonText = ref('')
  const toast = useToast()
  const confirmDialog = useConfirmDialog()

  const importModeOptions = [
    { label: 'OAuth 登录已有账号', value: 'oauth_login' },
    { label: '导入 Access Token', value: 'access_token' },
    { label: '导入 Session JSON', value: 'session_json' },
    { label: '导入 CPA JSON 文件', value: 'cpa_json' },
    { label: '从远程 CPA 服务器导入', value: 'remote_cpa' },
    { label: '从 Sub2API 服务器导入', value: 'sub2api' },
    { label: '导入 TOTP 凭证', value: 'totp_csv' },
  ] as const

  function setImportMode(mode: AccountImportMode) {
    importMode.value = mode
  }

  async function openImportModal(mode: AccountImportMode = 'access_token') {
    showImportModal.value = true
    setImportMode(mode)
  }

  function closeImportModal() {
    if (importBusy.value) return
    showImportModal.value = false
  }

  async function promptRemoveImportedAbnormalAccounts(importedTokens: string[], errorCount: number) {
    if (errorCount <= 0 || options.bulkProgress.bulkStopRequested.value) return

    let preview: Awaited<ReturnType<typeof accountsApi.cleanupImportedAbnormalAccounts>>
    try {
      preview = await accountsApi.cleanupImportedAbnormalAccounts(importedTokens, false)
    } catch (error) {
      options.setError('检查本次异常账号失败，已先保留', error)
      return
    }

    if (!preview.abnormal) {
      toast.info('本次导入有刷新异常，但没有找到可清理的异常账号，可能未写入本地或状态已变化')
      return
    }

    const confirmed = await confirmDialog.ask({
      title: '移除本次异常账号？',
      message: `本次导入刷新返回 ${errorCount} 条异常。\n后端确认 ${preview.abnormal} 个本次导入账号当前状态为异常，是否直接删除？\n\n只会删除本次导入且状态为异常的账号，正常、限流和历史账号会保留。`,
      confirmText: `删除 ${preview.abnormal} 个`,
      cancelText: '先保留',
    })

    if (!confirmed) return

    try {
      const result = await accountsApi.cleanupImportedAbnormalAccounts(importedTokens, true)
      toast.success(`已移除 ${result.removed || 0} 个本次异常账号`)
    } catch (error) {
      options.setError('移除本次异常账号失败', error)
    } finally {
      await options.loadData({ silentErrorToast: true })
    }
  }

  async function importTokenBatch(tokens: string[], sourceType: string, title: string) {
    const normalizedTokens = uniqueTokens(tokens)
    if (!normalizedTokens.length) {
      toast.warning('没有可导入的 access token')
      return
    }

    const confirmed = await confirmDialog.ask({
      title,
      message: `即将导入 ${normalizedTokens.length} 个账号，已存在账号会刷新远端信息。是否继续？`,
      confirmText: '确认导入',
      cancelText: '取消',
    })
    if (!confirmed) return

    importBusy.value = true
    options.bulkProgress.start(title, normalizedTokens.length, 'mutation')
    let addedCount = 0
    let skippedCount = 0
    let refreshedCount = 0
    let processed = 0
    const errors: string[] = []
    try {
      for (let index = 0; index < normalizedTokens.length; index += IMPORT_BATCH_SIZE) {
        if (options.bulkProgress.bulkStopRequested.value) break
        const batch = normalizedTokens.slice(index, index + IMPORT_BATCH_SIZE)
        try {
          const result = await accountsApi.importAccounts(
            batch.map((accessToken) => ({
              access_token: accessToken,
              type: 'free',
              source_type: sourceType,
            })),
            sourceType,
            { refresh: true, returnItems: false },
          )
          addedCount += Number(result.added || 0)
          skippedCount += Number(result.skipped || 0)
          refreshedCount += Number(result.refreshed || 0)
          errors.push(...(Array.isArray(result.errors) ? result.errors.filter(Boolean) : []))
        } catch (error) {
          errors.push(`${batch[0]?.slice(0, 6) || '-'}... 等 ${batch.length} 个账号：${options.normalizeErrorMessage(error)}`)
        } finally {
          processed = Math.min(normalizedTokens.length, processed + batch.length)
          options.bulkProgress.update({
            total: normalizedTokens.length,
            processed,
            done: processed >= normalizedTokens.length,
            total_quota: 0,
          })
        }
      }

      await options.loadData({ silentErrorToast: true })
      const stopped = options.bulkProgress.bulkStopRequested.value && processed < normalizedTokens.length
      options.bulkProgress.finish({
        total: normalizedTokens.length,
        processed,
        total_quota: 0,
      })
      if (stopped) {
        toast.warning(`${title}已停止：已处理 ${processed}/${normalizedTokens.length} 个`)
      } else if (errors.length > 0) {
        toast.warning(`${title}完成：新增 ${addedCount}，跳过 ${skippedCount}，刷新 ${refreshedCount}，失败 ${errors.length}`)
      } else {
        toast.success(`${title}完成：新增 ${addedCount}，跳过 ${skippedCount}，刷新 ${refreshedCount}`)
      }
      if (addedCount + skippedCount + refreshedCount > 0) {
        manualTokenText.value = ''
        sessionJsonText.value = ''
      }
      if (!stopped && errors.length > 0) {
        await promptRemoveImportedAbnormalAccounts(normalizedTokens, errors.length)
      }
    } catch (error) {
      options.bulkProgress.finish({
        total: normalizedTokens.length,
        processed,
        error: options.normalizeErrorMessage(error),
        total_quota: 0,
      })
      options.setError(`${title}失败`, error)
    } finally {
      importBusy.value = false
      options.bulkProgress.end()
    }
  }

  async function importManualTokenText() {
    await importTokenBatch(parseTokenLines(manualTokenText.value), 'manual', '导入 Access Token')
  }

  async function importTokenTextFile(file: File | null | undefined) {
    if (!file) return
    const text = await file.text()
    manualTokenText.value = text
    await importManualTokenText()
  }

  async function importSessionJson() {
    await importTokenBatch(parseSessionJsonTokens(sessionJsonText.value), 'session_json', '导入 Session JSON')
  }

  async function importTotpCsv() {
    const raw = manualTokenText.value.trim()
    if (!raw) {
      toast.warning('请先粘贴 TOTP 凭证内容')
      return
    }
    importBusy.value = true
    try {
      const result = await accountsApi.importTotpCsv(raw)
      const msg = result.skipped_count > 0
        ? `更新 ${result.updated} 个账号，${result.skipped_count} 个邮箱未匹配到账号`
        : `已更新 ${result.updated} 个账号的密码和 MFA 密钥`
      if (result.updated > 0) {
        toast.success(msg)
      } else {
        toast.warning(msg)
      }
      manualTokenText.value = ''
      showImportModal.value = false
      await options.loadData({ silentErrorToast: true })
    } catch (error) {
      options.setError('导入 TOTP 凭证失败', error)
    } finally {
      importBusy.value = false
    }
  }

  async function startOAuthLogin() {
    importBusy.value = true
    try {
      const result = await accountImportsApi.startOAuthLogin(oauthEmailHint.value)
      oauthSessionId.value = String(result.session_id || '')
      oauthAuthorizeUrl.value = String(result.authorize_url || '')
      oauthRedirectUriPrefix.value = String(result.redirect_uri_prefix || '')
      oauthCallbackText.value = ''
      if (!oauthSessionId.value || !oauthAuthorizeUrl.value) {
        throw new Error('后端没有返回完整的 OAuth 授权会话')
      }
      window.open(oauthAuthorizeUrl.value, '_blank', 'noopener,noreferrer')
      toast.success('OAuth 授权链接已生成')
    } catch (error) {
      options.setError('生成 OAuth 授权链接失败', error)
    } finally {
      importBusy.value = false
    }
  }

  function openOAuthAuthorizeUrl() {
    if (!oauthAuthorizeUrl.value) {
      void startOAuthLogin()
      return
    }
    window.open(oauthAuthorizeUrl.value, '_blank', 'noopener,noreferrer')
  }

  async function copyOAuthAuthorizeUrl() {
    const value = oauthAuthorizeUrl.value.trim()
    if (!value) {
      toast.warning('请先生成 OAuth 授权链接')
      return
    }
    try {
      await navigator.clipboard.writeText(value)
      toast.success('授权链接已复制')
    } catch (error) {
      options.setError('复制 OAuth 授权链接失败', error)
    }
  }

  async function finishOAuthLogin() {
    const sessionId = oauthSessionId.value.trim()
    const callback = oauthCallbackText.value.trim()
    if (!sessionId) {
      toast.warning('请先生成 OAuth 授权链接')
      return
    }
    if (!callback) {
      toast.warning('请先粘贴 callback URL 或 code')
      return
    }

    importBusy.value = true
    try {
      const result = await accountImportsApi.finishOAuthLogin(sessionId, callback)
      await options.loadData({ silentErrorToast: true })
      const added = Number(result.added || 0)
      const skipped = Number(result.skipped || 0)
      const refreshed = Number(result.refreshed || 0)
      const errors = Array.isArray(result.errors) ? result.errors.length : 0
      if (errors > 0) {
        toast.warning(`OAuth 登录导入完成：新增 ${added}，跳过 ${skipped}，刷新 ${refreshed}，异常 ${errors}`)
      } else {
        toast.success(`OAuth 登录导入完成：新增 ${added}，跳过 ${skipped}，刷新 ${refreshed}`)
      }
      oauthEmailHint.value = ''
      oauthCallbackText.value = ''
      oauthSessionId.value = ''
      oauthAuthorizeUrl.value = ''
      oauthRedirectUriPrefix.value = ''
    } catch (error) {
      options.setError('OAuth 登录导入失败', error)
    } finally {
      importBusy.value = false
    }
  }

  async function importLocalCPAFiles(files: FileList | File[] | null | undefined) {
    const fileList = Array.from(files || [])
    if (!fileList.length) return
    importBusy.value = true
    try {
      const tokens: string[] = []
      for (const file of fileList) {
        const text = await file.text()
        tokens.push(...parseCPAJsonTokens(text, file.name))
      }
      importBusy.value = false
      await importTokenBatch(tokens, 'cpa_json', '导入 CPA JSON 文件')
    } catch (error) {
      options.setError('导入 CPA JSON 文件失败', error)
    } finally {
      importBusy.value = false
    }
  }

  return {
    importBusy,
    showImportModal,
    importMode,
    importModeOptions,
    oauthEmailHint,
    oauthCallbackText,
    oauthSessionId,
    oauthAuthorizeUrl,
    oauthRedirectUriPrefix,
    manualTokenText,
    sessionJsonText,
    setImportMode,
    openImportModal,
    closeImportModal,
    importManualTokenText,
    importTokenTextFile,
    importSessionJson,
    startOAuthLogin,
    openOAuthAuthorizeUrl,
    copyOAuthAuthorizeUrl,
    finishOAuthLogin,
    importLocalCPAFiles,
    importTotpCsv,
  }
}
