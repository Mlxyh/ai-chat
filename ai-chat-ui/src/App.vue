<template>
  <div class="app-shell">
    <main v-if="!currentUser" class="auth-page">
      <section class="auth-panel">
        <div class="auth-brand">
          <p class="eyebrow">AI Chat</p>
          <h1>登录后开始对话</h1>
          <p>使用自己的 API Key 选择模型，聊天请求由后端安全转发。</p>
        </div>

        <div class="auth-tabs" role="tablist">
          <button :class="{ active: authMode === 'login' }" @click="switchAuthMode('login')">登录</button>
          <button :class="{ active: authMode === 'register' }" @click="switchAuthMode('register')">注册</button>
        </div>

        <form class="auth-form" @submit.prevent="submitAuth">
          <label>
            用户名
            <input v-model.trim="authForm.username" autocomplete="username" placeholder="3-32位用户名" />
          </label>
          <label>
            密码
            <input
              v-model="authForm.password"
              :autocomplete="authMode === 'login' ? 'current-password' : 'new-password'"
              type="password"
              placeholder="至少6位密码"
            />
          </label>

          <p v-if="authError" class="form-error">{{ authError }}</p>
          <button class="primary-action" type="submit" :disabled="authLoading">
            {{ authLoading ? '处理中...' : authMode === 'login' ? '登录' : '注册并登录' }}
          </button>
        </form>
      </section>
    </main>

    <main v-else class="chat-layout">
      <aside class="settings-panel">
        <div class="panel-header">
          <div>
            <p class="eyebrow">当前账号</p>
            <h2>{{ currentUser.username }}</h2>
          </div>
          <button class="ghost-button" @click="logout">退出</button>
        </div>

        <section class="settings-section">
          <label class="field-label">模型服务</label>
          <div class="provider-grid">
            <button
              v-for="option in providerOptions"
              :key="option.value"
              :class="{ active: provider === option.value }"
              @click="provider = option.value"
            >
              {{ option.label }}
            </button>
          </div>
        </section>

        <section class="settings-section">
          <label class="field-label" for="apiKey">API Key</label>
          <input
            id="apiKey"
            v-model.trim="activeSettings.apiKey"
            type="password"
            autocomplete="off"
            placeholder="sk-..."
          />
        </section>

        <section class="settings-section">
          <label class="field-label" for="baseUrl">Base URL</label>
          <input id="baseUrl" v-model.trim="activeSettings.baseUrl" placeholder="https://api.example.com/v1" />
        </section>

        <section class="settings-section">
          <label class="field-label" for="modelName">模型名称</label>
          <input id="modelName" v-model.trim="activeSettings.modelName" placeholder="gpt-4o-mini" />
        </section>

        <p class="settings-note">API Key 仅保存在当前浏览器，不会保存到后端数据库。</p>
      </aside>

      <section class="chat-panel">
        <header class="chat-header">
          <div>
            <p class="eyebrow">{{ activeProviderLabel }}</p>
            <h1>{{ activeSettings.modelName || '未选择模型' }}</h1>
          </div>
          <button class="ghost-button" @click="clearHistory">清空对话</button>
        </header>

        <div ref="chatRef" class="chat-messages">
          <div v-if="messages.length === 0" class="empty-state">
            <h2>开始新的对话</h2>
            <p>填写 API Key 并确认模型后，输入问题即可发送。</p>
          </div>

          <div v-for="(msg, index) in messages" :key="index" :class="['message-row', msg.role]">
            <div class="message-bubble">
              <div v-if="msg.done" v-html="msg.content || ''"></div>
              <div v-else class="streaming-text">{{ msg.content || '' }}</div>
            </div>
          </div>

          <div v-if="loading" class="message-row ai">
            <div class="message-bubble typing">思考中...</div>
          </div>
        </div>

        <p v-if="errorMsg" class="chat-error">{{ errorMsg }}</p>

        <form class="composer" @submit.prevent="send">
          <textarea
            ref="textareaRef"
            v-model="text"
            rows="1"
            placeholder="输入你的问题，Enter 发送，Shift+Enter 换行"
            @input="autoResize"
            @keydown.enter.exact.prevent="send"
          ></textarea>
          <button v-if="streaming" type="button" class="danger-button" @click="stop">停止</button>
          <button v-else class="primary-action compact" type="submit" :disabled="loading">发送</button>
        </form>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'

const API_URL = import.meta.env.VITE_API_URL || '/api'
const AUTH_TOKEN_KEY = 'auth-token'
const AUTH_USER_KEY = 'auth-user'

const providerOptions = [
  {
    value: 'deepseek',
    label: 'DeepSeek',
    defaults: {
      apiKey: '',
      baseUrl: 'https://api.deepseek.com',
      modelName: 'deepseek-chat',
    },
  },
  {
    value: 'openai',
    label: 'OpenAI',
    defaults: {
      apiKey: '',
      baseUrl: 'https://api.openai.com/v1',
      modelName: 'gpt-4o-mini',
    },
  },
  {
    value: 'qwen',
    label: '通义千问',
    defaults: {
      apiKey: '',
      baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
      modelName: 'qwen-plus',
    },
  },
  {
    value: 'custom',
    label: '自定义',
    defaults: {
      apiKey: '',
      baseUrl: '',
      modelName: '',
    },
  },
]

hljs.configure({ ignoreUnescapedHTML: true })

marked.setOptions({
  highlight: (code) => hljs.highlightAuto(code).value,
})

window.copyCode = (btn) => {
  const code = btn.parentElement.querySelector('code')?.innerText || ''
  navigator.clipboard.writeText(code).then(() => {
    btn.textContent = '已复制'
    setTimeout(() => (btn.textContent = '复制'), 1600)
  })
}

const renderMarkdown = (value) => {
  if (!value) return ''
  try {
    let html = marked.parse(value)
    html = html.replace(
      /<pre>/g,
      '<div class="code-block"><button class="copy-btn" onclick="copyCode(this)">复制</button><pre>',
    )
    html = html.replace(/<\/pre>/g, '</pre></div>')
    return html
  } catch {
    return value
  }
}

const authMode = ref('login')
const authLoading = ref(false)
const authError = ref('')
const authForm = reactive({ username: '', password: '' })
const token = ref(localStorage.getItem(AUTH_TOKEN_KEY) || '')
const savedUser = localStorage.getItem(AUTH_USER_KEY)
const currentUser = ref(savedUser ? JSON.parse(savedUser) : null)

const provider = ref('deepseek')
const settings = ref(buildDefaultSettings())
const text = ref('')
const messages = ref([])
const loading = ref(false)
const streaming = ref(false)
const errorMsg = ref('')
const chatRef = ref(null)
const textareaRef = ref(null)
let abortController = null

const activeSettings = computed(() => settings.value[provider.value])
const activeProviderLabel = computed(() => {
  return providerOptions.find((item) => item.value === provider.value)?.label || '自定义'
})

function buildDefaultSettings() {
  return Object.fromEntries(providerOptions.map((item) => [item.value, { ...item.defaults }]))
}

function userStorageKey(name) {
  return currentUser.value ? `${name}:${currentUser.value.username}` : name
}

function switchAuthMode(mode) {
  authMode.value = mode
  authError.value = ''
}

async function apiFetch(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  }
  if (token.value) headers.Authorization = `Bearer ${token.value}`

  const response = await fetch(`${API_URL}${path}`, { ...options, headers })
  const contentType = response.headers.get('content-type') || ''
  const payload = contentType.includes('application/json') ? await response.json() : null
  if (!response.ok) {
    throw new Error(payload?.detail || `请求失败 ${response.status}`)
  }
  return payload
}

async function submitAuth() {
  authError.value = ''
  if (!authForm.username || !authForm.password) {
    authError.value = '请输入用户名和密码'
    return
  }

  authLoading.value = true
  try {
    const payload = await apiFetch(`/auth/${authMode.value}`, {
      method: 'POST',
      body: JSON.stringify(authForm),
    })
    setSession(payload.token, payload.user)
  } catch (error) {
    authError.value = error.message
  } finally {
    authLoading.value = false
  }
}

function setSession(nextToken, user) {
  token.value = nextToken
  currentUser.value = user
  localStorage.setItem(AUTH_TOKEN_KEY, nextToken)
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user))
  authForm.password = ''
  loadUserData()
}

async function restoreSession() {
  if (!token.value) return
  try {
    const payload = await apiFetch('/auth/me')
    setSession(token.value, payload.user)
  } catch {
    logout()
  }
}

function logout() {
  token.value = ''
  currentUser.value = null
  messages.value = []
  localStorage.removeItem(AUTH_TOKEN_KEY)
  localStorage.removeItem(AUTH_USER_KEY)
}

function loadUserData() {
  const savedSettings = localStorage.getItem(userStorageKey('model-settings'))
  const mergedSettings = buildDefaultSettings()
  if (savedSettings) {
    const parsed = JSON.parse(savedSettings)
    for (const key of Object.keys(mergedSettings)) {
      mergedSettings[key] = { ...mergedSettings[key], ...(parsed[key] || {}) }
    }
  }
  settings.value = mergedSettings

  provider.value = localStorage.getItem(userStorageKey('selected-provider')) || 'deepseek'
  const savedMessages = localStorage.getItem(userStorageKey('chat-messages'))
  messages.value = savedMessages ? JSON.parse(savedMessages) : []
}

watch(
  settings,
  (value) => {
    if (currentUser.value) {
      localStorage.setItem(userStorageKey('model-settings'), JSON.stringify(value))
    }
  },
  { deep: true },
)

watch(provider, (value) => {
  if (currentUser.value) localStorage.setItem(userStorageKey('selected-provider'), value)
})

watch(
  messages,
  (value) => {
    if (currentUser.value) {
      localStorage.setItem(userStorageKey('chat-messages'), JSON.stringify(value))
    }
  },
  { deep: true },
)

const scrollToBottom = async () => {
  await nextTick()
  if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight
}

function autoResize() {
  const textarea = textareaRef.value
  if (!textarea) return
  textarea.style.height = 'auto'
  textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`
}

function clearHistory() {
  messages.value = []
  errorMsg.value = ''
}

function stop() {
  if (abortController) abortController.abort()
  streaming.value = false
  loading.value = false
  const last = messages.value[messages.value.length - 1]
  if (last?.role === 'ai' && !last.done) {
    last.content = renderMarkdown(last.raw)
    last.done = true
    messages.value = [...messages.value]
  }
}

function validateChatSettings() {
  if (!activeSettings.value.apiKey) return '请先填写当前模型的 API Key'
  if (!activeSettings.value.baseUrl) return '请先填写 Base URL'
  if (!activeSettings.value.modelName) return '请先填写模型名称'
  return ''
}

async function send() {
  const userInput = text.value.trim()
  if (!userInput || loading.value) return

  const settingsError = validateChatSettings()
  if (settingsError) {
    errorMsg.value = settingsError
    return
  }

  text.value = ''
  if (textareaRef.value) textareaRef.value.style.height = 'auto'
  errorMsg.value = ''

  messages.value.push({ role: 'user', content: userInput, done: true })
  const aiMsg = { role: 'ai', content: '', raw: '', done: false }
  messages.value.push(aiMsg)

  loading.value = true
  streaming.value = false
  abortController = new AbortController()
  scrollToBottom()

  try {
    const response = await fetch(`${API_URL}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token.value}`,
      },
      body: JSON.stringify({
        provider: provider.value,
        message: userInput,
        session_id: userStorageKey('default-session'),
        api_key: activeSettings.value.apiKey,
        base_url: activeSettings.value.baseUrl,
        model_name: activeSettings.value.modelName,
      }),
      signal: abortController.signal,
    })

    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload?.detail || `服务器错误 ${response.status}`)
    }

    loading.value = false
    streaming.value = true

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          aiMsg.raw += line.slice(6)
          aiMsg.content = aiMsg.raw
          messages.value = [...messages.value]
          scrollToBottom()
        }
      }
    }
  } catch (error) {
    if (error.name !== 'AbortError') {
      errorMsg.value = error.message || '连接失败，请检查网络或稍后重试'
      messages.value.splice(-2, 2)
      if (error.message.includes('登录')) logout()
    }
  } finally {
    loading.value = false
    streaming.value = false
    abortController = null
    if (!aiMsg.done) {
      aiMsg.content = renderMarkdown(aiMsg.raw)
      aiMsg.done = true
      messages.value = [...messages.value]
    }
  }
}

onMounted(() => {
  if (currentUser.value) loadUserData()
  restoreSession()
})
</script>

<style>
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: #eef1f5;
  color: #172033;
  font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
}

button,
input,
textarea {
  font: inherit;
}

button {
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.62;
}

.app-shell {
  min-height: 100vh;
}

.auth-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: #e9edf3;
}

.auth-panel {
  width: min(440px, 100%);
  background: #ffffff;
  border: 1px solid #d8dee8;
  border-radius: 8px;
  padding: 28px;
  box-shadow: 0 18px 45px rgba(23, 32, 51, 0.10);
}

.auth-brand h1,
.chat-header h1,
.panel-header h2,
.empty-state h2 {
  margin: 0;
  letter-spacing: 0;
}

.auth-brand h1 {
  font-size: 28px;
  line-height: 1.2;
}

.auth-brand p:last-child {
  margin: 10px 0 0;
  color: #5c667a;
  line-height: 1.6;
}

.eyebrow {
  margin: 0 0 6px;
  color: #53627c;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
}

.auth-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin: 26px 0 18px;
  padding: 4px;
  background: #eef1f5;
  border-radius: 8px;
}

.auth-tabs button,
.provider-grid button {
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #53627c;
  min-height: 38px;
  font-weight: 700;
}

.auth-tabs button.active,
.provider-grid button.active {
  background: #ffffff;
  color: #0f172a;
  box-shadow: 0 1px 2px rgba(23, 32, 51, 0.12);
}

.auth-form,
.settings-section {
  display: grid;
  gap: 12px;
}

.auth-form label,
.settings-section label {
  display: grid;
  gap: 7px;
  color: #344055;
  font-size: 14px;
  font-weight: 700;
}

input,
textarea {
  width: 100%;
  border: 1px solid #cbd3df;
  border-radius: 8px;
  background: #ffffff;
  color: #172033;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}

input {
  min-height: 44px;
  padding: 10px 12px;
}

textarea {
  min-height: 48px;
  max-height: 180px;
  padding: 12px 14px;
  resize: none;
  line-height: 1.5;
}

input:focus,
textarea:focus {
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.13);
}

.primary-action,
.ghost-button,
.danger-button {
  border: 0;
  border-radius: 8px;
  min-height: 42px;
  padding: 0 16px;
  font-weight: 800;
}

.primary-action {
  background: #2563eb;
  color: #ffffff;
}

.primary-action:hover:not(:disabled) {
  background: #1d4ed8;
}

.primary-action.compact,
.danger-button {
  min-width: 78px;
  height: 48px;
}

.ghost-button {
  background: #eef1f5;
  color: #243044;
}

.ghost-button:hover {
  background: #e1e7f0;
}

.danger-button {
  background: #dc2626;
  color: #ffffff;
}

.form-error,
.chat-error {
  margin: 0;
  color: #b91c1c;
  font-size: 14px;
}

.chat-layout {
  height: 100vh;
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  background: #eef1f5;
}

.settings-panel {
  display: flex;
  flex-direction: column;
  gap: 22px;
  padding: 22px;
  border-right: 1px solid #d8dee8;
  background: #f8fafc;
  overflow-y: auto;
}

.panel-header,
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.panel-header h2 {
  font-size: 20px;
}

.provider-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 6px;
  background: #e9edf3;
  border-radius: 8px;
}

.field-label {
  color: #344055;
  font-size: 13px;
  font-weight: 800;
}

.settings-note {
  margin: auto 0 0;
  color: #667085;
  font-size: 13px;
  line-height: 1.6;
}

.chat-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #ffffff;
}

.chat-header {
  min-height: 74px;
  padding: 16px 22px;
  border-bottom: 1px solid #d8dee8;
}

.chat-header h1 {
  font-size: 20px;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 22px;
}

.empty-state {
  height: 100%;
  display: grid;
  place-content: center;
  text-align: center;
  color: #667085;
}

.empty-state h2 {
  color: #172033;
  font-size: 24px;
}

.empty-state p {
  margin: 10px 0 0;
}

.message-row {
  display: flex;
  margin: 14px 0;
}

.message-row.user {
  justify-content: flex-end;
}

.message-row.ai {
  justify-content: flex-start;
}

.message-bubble {
  max-width: min(760px, 78%);
  padding: 13px 16px;
  border-radius: 8px;
  line-height: 1.65;
  word-break: break-word;
}

.message-row.user .message-bubble {
  background: #2563eb;
  color: #ffffff;
}

.message-row.ai .message-bubble {
  background: #f4f6fa;
  border: 1px solid #e3e8f0;
  color: #172033;
}

.message-bubble p {
  margin: 0 0 12px;
}

.message-bubble p:last-child {
  margin-bottom: 0;
}

.message-bubble pre {
  overflow-x: auto;
  margin: 10px 0;
  padding: 14px;
  border-radius: 8px;
  background: #111827;
  color: #f8fafc;
}

.message-bubble code {
  font-family: "SF Mono", Consolas, "Liberation Mono", monospace;
  font-size: 13px;
}

.code-block {
  position: relative;
}

.copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  border: 0;
  border-radius: 6px;
  background: #334155;
  color: #ffffff;
  min-height: 28px;
  padding: 0 10px;
  font-size: 12px;
}

.typing,
.streaming-text {
  white-space: pre-wrap;
}

.chat-error {
  padding: 0 22px 12px;
}

.composer {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  padding: 16px 22px;
  border-top: 1px solid #d8dee8;
  background: #ffffff;
}

@media (max-width: 860px) {
  .chat-layout {
    height: auto;
    min-height: 100vh;
    grid-template-columns: 1fr;
  }

  .settings-panel {
    border-right: 0;
    border-bottom: 1px solid #d8dee8;
  }

  .chat-panel {
    min-height: 70vh;
  }

  .message-bubble {
    max-width: 92%;
  }
}

@media (max-width: 560px) {
  .auth-page,
  .settings-panel,
  .chat-messages,
  .chat-header,
  .composer {
    padding-left: 14px;
    padding-right: 14px;
  }

  .auth-panel {
    padding: 22px;
  }

  .composer {
    flex-direction: column;
    align-items: stretch;
  }

  .primary-action.compact,
  .danger-button {
    width: 100%;
  }
}
</style>
