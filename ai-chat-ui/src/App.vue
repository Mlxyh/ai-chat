<template>
  <div class="app-shell">
    <main v-if="!currentUser" class="auth-page">
      <section class="hero-panel">
        <div class="brand-mark">
          <span>AI</span>
        </div>
        <p class="eyebrow">Private model gateway</p>
        <h1>把你的 API Key 接入一个高级 AI 工作台</h1>
        <p class="hero-copy">登录后选择模型服务，使用自己的密钥发起流式对话。密钥只保存在当前浏览器，后端只做鉴权和转发。</p>
        <div class="capability-row">
          <span>OpenAI-compatible</span>
          <span>Streaming chat</span>
          <span>Local key storage</span>
        </div>
      </section>

      <section class="auth-panel">
        <div class="panel-topline">
          <div>
            <p class="eyebrow">Account access</p>
            <h2>{{ authMode === 'login' ? '欢迎回来' : '创建账号' }}</h2>
          </div>
          <div class="status-pill">Secure</div>
        </div>

        <div class="auth-tabs" role="tablist">
          <button :class="{ active: authMode === 'login' }" @click="switchAuthMode('login')">登录</button>
          <button :class="{ active: authMode === 'register' }" @click="switchAuthMode('register')">注册</button>
        </div>

        <form class="auth-form" @submit.prevent="submitAuth">
          <label>
            用户名
            <input v-model.trim="authForm.username" autocomplete="username" placeholder="username" />
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
            {{ authLoading ? '处理中...' : authMode === 'login' ? '进入工作台' : '注册并进入' }}
          </button>
        </form>
      </section>
    </main>

    <main v-else class="chat-layout">
      <aside class="settings-panel">
        <div class="panel-topline">
          <div>
            <p class="eyebrow">Workspace</p>
            <h2>{{ currentUser.username }}</h2>
          </div>
          <button class="ghost-button compact-button" @click="logout">退出</button>
        </div>

        <section class="settings-section">
          <div class="section-title">
            <span>模型服务</span>
            <span class="status-dot ready">Ready</span>
          </div>
          <div class="provider-stack">
            <button
              v-for="option in providerOptions"
              :key="option.value"
              :class="{ active: provider === option.value }"
              @click="provider = option.value"
            >
              <span>{{ option.label }}</span>
              <small>{{ option.description }}</small>
            </button>
          </div>
        </section>

        <section class="settings-section secret-section">
          <div class="section-title">
            <label for="apiKey">API Key</label>
            <button class="link-button" type="button" @click="showApiKey = !showApiKey">
              {{ showApiKey ? '隐藏' : '显示' }}
            </button>
          </div>
          <input
            id="apiKey"
            v-model.trim="activeSettings.apiKey"
            :type="showApiKey ? 'text' : 'password'"
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

        <div class="security-note">
          <strong>Local only</strong>
          <span>API Key 只保存在当前浏览器。后端会拒绝 HTTP、本机和内网 Base URL。</span>
        </div>
      </aside>

      <section class="chat-panel">
        <header class="chat-header">
          <div>
            <p class="eyebrow">{{ viewMode === 'agent' ? 'Agent workspace' : activeProviderLabel }}</p>
            <h1>{{ viewMode === 'agent' ? 'AI 超级智能体' : activeSettings.modelName || '未选择模型' }}</h1>
          </div>
          <div class="header-actions">
            <div class="view-tabs">
              <button :class="{ active: viewMode === 'agent' }" @click="viewMode = 'agent'">智能体任务</button>
              <button :class="{ active: viewMode === 'chat' }" @click="viewMode = 'chat'">聊天</button>
            </div>
            <span class="connection-pill">{{ connectionLabel }}</span>
            <button v-if="viewMode === 'chat'" class="ghost-button compact-button" @click="clearHistory">清空</button>
          </div>
        </header>

        <div v-if="viewMode === 'agent'" class="agent-workspace">
          <section class="agent-create">
            <div>
              <p class="eyebrow">Mission control</p>
              <h2>告诉智能体你要完成什么</h2>
              <p>系统会先生成计划，等待你确认后再逐步执行文本型任务。</p>
            </div>
            <textarea
              v-model="agentGoal"
              rows="3"
              placeholder="例如：帮我分析这个项目还能怎么优化，并输出开发任务清单"
            ></textarea>
            <p v-if="agentError" class="chat-error inline-error">{{ agentError }}</p>
            <button class="primary-action" type="button" :disabled="agentLoading" @click="createAgentTask">
              {{ agentLoading ? '正在规划...' : '创建智能体任务' }}
            </button>
          </section>

          <section class="agent-board">
            <aside class="task-list">
              <div class="section-title">
                <span>任务历史</span>
                <button class="link-button" type="button" @click="loadAgentTasks">刷新</button>
              </div>
              <button
                v-for="task in agentTasks"
                :key="task.id"
                :class="['task-card', { active: selectedTask?.id === task.id }]"
                type="button"
                @click="selectAgentTask(task.id)"
              >
                <span>{{ task.title }}</span>
                <small>{{ task.status }}</small>
              </button>
              <p v-if="agentTasks.length === 0" class="muted-copy">暂无任务。创建一个目标开始。</p>
            </aside>

            <article v-if="selectedTask" class="task-detail">
              <div class="task-detail-head">
                <div>
                  <p class="eyebrow">{{ selectedTask.status }}</p>
                  <h2>{{ selectedTask.title }}</h2>
                </div>
                <div class="task-actions">
                  <button
                    v-if="selectedTask.status === 'waiting_confirmation'"
                    class="primary-action compact-button"
                    type="button"
                    :disabled="agentLoading"
                    @click="confirmAgentTask"
                  >
                    确认执行此计划
                  </button>
                  <button
                    v-if="selectedTask.status === 'running'"
                    class="primary-action compact-button"
                    type="button"
                    :disabled="agentLoading"
                    @click="runAgentTask"
                  >
                    继续下一步
                  </button>
                  <button
                    v-if="!['completed', 'failed'].includes(selectedTask.status)"
                    class="ghost-button compact-button"
                    type="button"
                    :disabled="agentLoading"
                    @click="cancelAgentTask"
                  >
                    取消任务
                  </button>
                </div>
              </div>

              <div class="mission-card">
                <strong>目标</strong>
                <p>{{ selectedTask.goal }}</p>
              </div>
              <div class="mission-card">
                <strong>计划</strong>
                <p>{{ selectedTask.plan }}</p>
              </div>

              <div class="timeline">
                <div v-for="step in selectedTask.steps" :key="step.id" :class="['timeline-step', step.status]">
                  <div class="step-index">{{ step.step_order }}</div>
                  <div class="step-body">
                    <div class="step-head">
                      <strong>{{ step.title }}</strong>
                      <span>{{ step.status }} · {{ step.tool_name }}</span>
                    </div>
                    <p v-if="step.input" class="muted-copy">{{ step.input }}</p>
                    <div v-if="step.output" class="step-output" v-html="renderMarkdown(step.output)"></div>
                    <p v-if="step.error" class="form-error">{{ step.error }}</p>
                  </div>
                </div>
              </div>

              <div v-if="selectedTask.final_result" class="final-result">
                <p class="eyebrow">Final delivery</p>
                <div v-html="renderMarkdown(selectedTask.final_result)"></div>
              </div>
            </article>

            <article v-else class="task-detail empty-task">
              <h2>等待任务</h2>
              <p>创建任务后，智能体会在这里展示计划、步骤和最终交付物。</p>
            </article>
          </section>
        </div>

        <div v-else ref="chatRef" class="chat-messages">
          <div v-if="messages.length === 0" class="empty-state">
            <div class="empty-orbit"></div>
            <h2>Ready for intelligence</h2>
            <p>配置 API Key 和模型后，开始一次安全的流式对话。</p>
            <div class="prompt-chips">
              <button type="button" @click="usePrompt('帮我把这个项目的部署步骤整理成清单')">部署清单</button>
              <button type="button" @click="usePrompt('分析一下这个产品还可以优化哪些体验')">产品优化</button>
              <button type="button" @click="usePrompt('写一个简洁的项目 README 结构')">README 结构</button>
            </div>
          </div>

          <div v-for="(msg, index) in messages" :key="index" :class="['message-row', msg.role]">
            <div class="message-meta">{{ msg.role === 'user' ? 'You' : 'Assistant' }}</div>
            <div class="message-bubble">
              <div v-if="msg.done" v-html="msg.content || ''"></div>
              <div v-else class="streaming-text">{{ msg.content || '' }}</div>
            </div>
          </div>

          <div v-if="loading" class="message-row ai">
            <div class="message-meta">Assistant</div>
            <div class="message-bubble typing">思考中<span></span><span></span><span></span></div>
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
          <button v-else class="primary-action send-button" type="submit" :disabled="loading">发送</button>
        </form>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'

const API_URL = import.meta.env.VITE_API_URL || '/api'
const AUTH_TOKEN_KEY = 'auth-token'
const AUTH_USER_KEY = 'auth-user'

const providerOptions = [
  {
    value: 'deepseek',
    label: 'DeepSeek',
    description: '速度快，适合中文与代码',
    defaults: {
      apiKey: '',
      baseUrl: 'https://api.deepseek.com',
      modelName: 'deepseek-chat',
    },
  },
  {
    value: 'openai',
    label: 'OpenAI',
    description: '通用推理与创作',
    defaults: {
      apiKey: '',
      baseUrl: 'https://api.openai.com/v1',
      modelName: 'gpt-4o-mini',
    },
  },
  {
    value: 'qwen',
    label: '通义千问',
    description: '国内服务兼容模式',
    defaults: {
      apiKey: '',
      baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
      modelName: 'qwen-plus',
    },
  },
  {
    value: 'custom',
    label: '自定义',
    description: 'OpenAI-compatible endpoint',
    defaults: {
      apiKey: '',
      baseUrl: '',
      modelName: '',
    },
  },
]

hljs.configure({ ignoreUnescapedHTML: true })

const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  highlight(code) {
    try {
      return hljs.highlightAuto(code).value
    } catch {
      return ''
    }
  },
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
    let html = markdown.render(value)
    html = html.replace(
      /<pre><code/g,
      '<div class="code-block"><button class="copy-btn" onclick="copyCode(this)">复制</button><pre><code',
    )
    html = html.replace(/<\/code><\/pre>/g, '</code></pre></div>')
    return html
  } catch {
    return escapeHtml(value)
  }
}

const escapeHtml = (value) => {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

const readJsonStorage = (key, fallback) => {
  const saved = localStorage.getItem(key)
  if (!saved) return fallback
  try {
    return JSON.parse(saved)
  } catch {
    localStorage.removeItem(key)
    return fallback
  }
}

const safeMessage = (error, fallback = '连接失败，请检查网络或稍后重试') => {
  return typeof error?.message === 'string' && error.message ? error.message : fallback
}

const authMode = ref('login')
const authLoading = ref(false)
const authError = ref('')
const authForm = reactive({ username: '', password: '' })
const token = ref(localStorage.getItem(AUTH_TOKEN_KEY) || '')
const currentUser = ref(readJsonStorage(AUTH_USER_KEY, null))

const provider = ref('deepseek')
const settings = ref(buildDefaultSettings())
const showApiKey = ref(false)
const viewMode = ref('agent')
const text = ref('')
const messages = ref([])
const agentGoal = ref('')
const agentTasks = ref([])
const selectedTask = ref(null)
const agentLoading = ref(false)
const agentError = ref('')
const loading = ref(false)
const streaming = ref(false)
const errorMsg = ref('')
const chatRef = ref(null)
const textareaRef = ref(null)
let abortController = null

const activeSettings = computed(() => settings.value[provider.value] || settings.value.deepseek)
const activeProviderLabel = computed(() => {
  return providerOptions.find((item) => item.value === provider.value)?.label || '自定义'
})
const connectionLabel = computed(() => {
  if (!activeSettings.value.apiKey) return 'Missing API Key'
  if (!activeSettings.value.baseUrl || !activeSettings.value.modelName) return 'Incomplete'
  return 'Configured'
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
    authError.value = safeMessage(error, '登录失败，请稍后重试')
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
  loadAgentTasks()
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
  const mergedSettings = buildDefaultSettings()
  const parsedSettings = readJsonStorage(userStorageKey('model-settings'), null)
  if (parsedSettings && typeof parsedSettings === 'object') {
    for (const key of Object.keys(mergedSettings)) {
      mergedSettings[key] = { ...mergedSettings[key], ...(parsedSettings[key] || {}) }
    }
  }
  settings.value = mergedSettings

  const savedProvider = localStorage.getItem(userStorageKey('selected-provider'))
  provider.value = providerOptions.some((item) => item.value === savedProvider) ? savedProvider : 'deepseek'
  messages.value = readJsonStorage(userStorageKey('chat-messages'), [])
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

function usePrompt(prompt) {
  text.value = prompt
  nextTick(autoResize)
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

function agentPayload(extra = {}) {
  return {
    provider: provider.value,
    api_key: activeSettings.value.apiKey,
    base_url: activeSettings.value.baseUrl,
    model_name: activeSettings.value.modelName,
    ...extra,
  }
}

async function loadAgentTasks() {
  if (!currentUser.value) return
  try {
    const payload = await apiFetch('/agent/tasks')
    agentTasks.value = payload.tasks || []
    if (!selectedTask.value && agentTasks.value.length > 0) {
      await selectAgentTask(agentTasks.value[0].id)
    }
  } catch (error) {
    agentError.value = safeMessage(error, '任务列表加载失败')
  }
}

async function selectAgentTask(taskId) {
  try {
    const payload = await apiFetch(`/agent/tasks/${taskId}`)
    selectedTask.value = payload.task
  } catch (error) {
    agentError.value = safeMessage(error, '任务详情加载失败')
  }
}

async function createAgentTask() {
  agentError.value = ''
  const settingsError = validateChatSettings()
  if (settingsError) {
    agentError.value = settingsError
    return
  }
  if (!agentGoal.value.trim()) {
    agentError.value = '请输入任务目标'
    return
  }

  agentLoading.value = true
  try {
    const payload = await apiFetch('/agent/tasks', {
      method: 'POST',
      body: JSON.stringify(agentPayload({ goal: agentGoal.value.trim() })),
    })
    selectedTask.value = payload.task
    agentGoal.value = ''
    await loadAgentTasks()
  } catch (error) {
    agentError.value = safeMessage(error, '智能体任务创建失败')
  } finally {
    agentLoading.value = false
  }
}

async function confirmAgentTask() {
  if (!selectedTask.value) return
  agentError.value = ''
  agentLoading.value = true
  try {
    const payload = await apiFetch(`/agent/tasks/${selectedTask.value.id}/confirm`, { method: 'POST' })
    selectedTask.value = payload.task
    await loadAgentTasks()
  } catch (error) {
    agentError.value = safeMessage(error, '任务确认失败')
  } finally {
    agentLoading.value = false
  }
}

async function runAgentTask() {
  if (!selectedTask.value) return
  agentError.value = ''
  const settingsError = validateChatSettings()
  if (settingsError) {
    agentError.value = settingsError
    return
  }

  agentLoading.value = true
  try {
    const payload = await apiFetch(`/agent/tasks/${selectedTask.value.id}/run`, {
      method: 'POST',
      body: JSON.stringify(agentPayload()),
    })
    selectedTask.value = payload.task
    await loadAgentTasks()
  } catch (error) {
    agentError.value = safeMessage(error, '任务执行失败')
  } finally {
    agentLoading.value = false
  }
}

async function cancelAgentTask() {
  if (!selectedTask.value) return
  agentError.value = ''
  agentLoading.value = true
  try {
    const payload = await apiFetch(`/agent/tasks/${selectedTask.value.id}/cancel`, { method: 'POST' })
    selectedTask.value = payload.task
    await loadAgentTasks()
  } catch (error) {
    agentError.value = safeMessage(error, '任务取消失败')
  } finally {
    agentLoading.value = false
  }
}

function handleSseLine(line, aiMsg) {
  if (!line.startsWith('data: ')) return
  const raw = line.slice(6)
  let payload = null
  try {
    payload = JSON.parse(raw)
  } catch (error) {
    if (raw) {
      aiMsg.raw += raw
      aiMsg.content = aiMsg.raw
    }
    return
  }

  if (payload.type === 'error') {
    throw new Error(payload.content || '模型服务连接失败')
  }
  if (payload.type === 'chunk') {
    aiMsg.raw += payload.content || ''
    aiMsg.content = aiMsg.raw
  }
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

  messages.value.push({ role: 'user', content: escapeHtml(userInput), done: true })
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
        handleSseLine(line, aiMsg)
        messages.value = [...messages.value]
        scrollToBottom()
      }
    }
  } catch (error) {
    const errorName = error?.name
    const errorMessage = safeMessage(error)
    if (errorName !== 'AbortError') {
      errorMsg.value = errorMessage
      messages.value.splice(-2, 2)
      if (errorMessage.includes('登录')) logout()
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
  loadAgentTasks()
})
</script>

<style>
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: #070a12;
  color: #eef4ff;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
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
  opacity: 0.58;
}

.app-shell {
  min-height: 100vh;
  background:
    radial-gradient(circle at 15% 10%, rgba(80, 187, 255, 0.22), transparent 34%),
    radial-gradient(circle at 82% 0%, rgba(145, 92, 255, 0.24), transparent 34%),
    linear-gradient(135deg, #070a12 0%, #0a1020 44%, #101827 100%);
}

.auth-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(380px, 460px);
  gap: 36px;
  align-items: center;
  padding: clamp(24px, 6vw, 76px);
}

.hero-panel {
  max-width: 760px;
}

.brand-mark {
  width: 64px;
  height: 64px;
  display: grid;
  place-items: center;
  border: 1px solid rgba(144, 205, 255, 0.45);
  border-radius: 18px;
  background: linear-gradient(145deg, rgba(70, 144, 255, 0.22), rgba(255, 255, 255, 0.08));
  box-shadow: 0 0 40px rgba(78, 168, 255, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.22);
  color: #dff3ff;
  font-weight: 900;
  letter-spacing: 0;
}

.eyebrow {
  margin: 0 0 8px;
  color: #83d8ff;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-panel .eyebrow {
  margin-top: 28px;
}

.hero-panel h1 {
  max-width: 720px;
  margin: 0;
  font-size: clamp(42px, 6vw, 76px);
  line-height: 0.98;
  letter-spacing: 0;
}

.hero-copy {
  max-width: 640px;
  margin: 24px 0 0;
  color: #a8b7d8;
  font-size: 18px;
  line-height: 1.75;
}

.capability-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 34px;
}

.capability-row span,
.status-pill,
.connection-pill,
.status-dot {
  border: 1px solid rgba(130, 216, 255, 0.25);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.07);
  color: #d5e8ff;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 800;
}

.auth-panel,
.settings-panel,
.chat-panel {
  border: 1px solid rgba(143, 166, 214, 0.22);
  background: rgba(11, 17, 31, 0.78);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(22px);
}

.auth-panel {
  border-radius: 22px;
  padding: 28px;
}

.panel-topline,
.chat-header,
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.panel-topline h2,
.chat-header h1,
.empty-state h2 {
  margin: 0;
  letter-spacing: 0;
}

.panel-topline h2 {
  font-size: 24px;
}

.auth-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin: 28px 0 18px;
  padding: 5px;
  border: 1px solid rgba(143, 166, 214, 0.18);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.05);
}

.auth-tabs button,
.provider-stack button,
.prompt-chips button {
  border: 0;
  color: #a8b7d8;
  background: transparent;
}

.auth-tabs button {
  min-height: 42px;
  border-radius: 10px;
  font-weight: 800;
}

.auth-tabs button.active {
  background: linear-gradient(135deg, rgba(42, 135, 255, 0.92), rgba(126, 87, 255, 0.85));
  color: #ffffff;
}

.auth-form,
.settings-section {
  display: grid;
  gap: 12px;
}

.auth-form label,
.field-label,
.section-title label,
.section-title span:first-child {
  color: #d9e6ff;
  font-size: 13px;
  font-weight: 800;
}

.auth-form label {
  display: grid;
  gap: 8px;
}

input,
textarea {
  width: 100%;
  border: 1px solid rgba(143, 166, 214, 0.24);
  border-radius: 14px;
  background: rgba(5, 10, 20, 0.72);
  color: #eef4ff;
  outline: none;
  transition: border-color 0.18s, box-shadow 0.18s, background 0.18s;
}

input {
  min-height: 46px;
  padding: 11px 13px;
}

textarea {
  min-height: 52px;
  max-height: 180px;
  padding: 14px 16px;
  resize: none;
  line-height: 1.55;
}

input::placeholder,
textarea::placeholder {
  color: #63708d;
}

input:focus,
textarea:focus {
  border-color: rgba(118, 213, 255, 0.78);
  background: rgba(9, 16, 31, 0.92);
  box-shadow: 0 0 0 4px rgba(53, 159, 255, 0.15);
}

.primary-action,
.ghost-button,
.danger-button {
  border: 0;
  border-radius: 14px;
  min-height: 44px;
  padding: 0 18px;
  font-weight: 900;
}

.primary-action {
  background: linear-gradient(135deg, #46a5ff, #7c5cff);
  color: #ffffff;
  box-shadow: 0 16px 38px rgba(72, 123, 255, 0.26);
}

.primary-action:hover:not(:disabled) {
  filter: brightness(1.08);
}

.ghost-button {
  border: 1px solid rgba(143, 166, 214, 0.22);
  background: rgba(255, 255, 255, 0.07);
  color: #dce8ff;
}

.ghost-button:hover {
  background: rgba(255, 255, 255, 0.11);
}

.compact-button,
.danger-button,
.send-button {
  min-height: 42px;
}

.danger-button {
  background: #ef4444;
  color: #ffffff;
}

.link-button {
  border: 0;
  background: transparent;
  color: #83d8ff;
  font-size: 12px;
  font-weight: 800;
}

.form-error,
.chat-error {
  margin: 0;
  color: #ff9a9a;
  font-size: 14px;
}

.chat-layout {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  gap: 16px;
  padding: 16px;
}

.settings-panel {
  display: flex;
  flex-direction: column;
  gap: 24px;
  min-height: calc(100vh - 32px);
  border-radius: 24px;
  padding: 22px;
  overflow-y: auto;
}

.provider-stack {
  display: grid;
  gap: 10px;
}

.provider-stack button {
  display: grid;
  gap: 4px;
  min-height: 68px;
  padding: 13px;
  text-align: left;
  border: 1px solid rgba(143, 166, 214, 0.18);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.045);
}

.provider-stack button span {
  color: #eef4ff;
  font-weight: 900;
}

.provider-stack button small {
  color: #8fa1c6;
  line-height: 1.35;
}

.provider-stack button.active {
  border-color: rgba(118, 213, 255, 0.65);
  background: linear-gradient(135deg, rgba(50, 143, 255, 0.22), rgba(126, 87, 255, 0.18));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), 0 14px 36px rgba(40, 120, 255, 0.15);
}

.status-dot {
  padding: 5px 9px;
}

.status-dot.ready {
  color: #86efac;
  border-color: rgba(134, 239, 172, 0.28);
}

.security-note {
  display: grid;
  gap: 6px;
  margin-top: auto;
  padding: 14px;
  border: 1px solid rgba(134, 239, 172, 0.20);
  border-radius: 16px;
  background: rgba(17, 112, 74, 0.12);
  color: #93a6c9;
  font-size: 13px;
  line-height: 1.55;
}

.security-note strong {
  color: #b8ffd2;
}

.chat-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: calc(100vh - 32px);
  border-radius: 24px;
  overflow: hidden;
}

.chat-header {
  min-height: 76px;
  padding: 18px 22px;
  border-bottom: 1px solid rgba(143, 166, 214, 0.16);
}

.chat-header h1 {
  font-size: 22px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.view-tabs {
  display: flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid rgba(143, 166, 214, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
}

.view-tabs button {
  min-height: 32px;
  border: 0;
  border-radius: 999px;
  padding: 0 12px;
  background: transparent;
  color: #93a6c9;
  font-weight: 900;
}

.view-tabs button.active {
  background: rgba(131, 216, 255, 0.16);
  color: #eef4ff;
}

.agent-workspace {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px;
  display: grid;
  gap: 18px;
  background:
    linear-gradient(rgba(255, 255, 255, 0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.025) 1px, transparent 1px);
  background-size: 34px 34px;
}

.agent-create,
.task-list,
.task-detail,
.mission-card,
.final-result {
  border: 1px solid rgba(143, 166, 214, 0.18);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.06);
}

.agent-create {
  display: grid;
  grid-template-columns: minmax(220px, 0.85fr) minmax(280px, 1.4fr) auto;
  gap: 14px;
  align-items: end;
  padding: 18px;
}

.agent-create h2,
.task-detail h2 {
  margin: 0;
  letter-spacing: 0;
}

.agent-create p {
  margin: 8px 0 0;
  color: #93a6c9;
  line-height: 1.55;
}

.inline-error {
  grid-column: 1 / -1;
  padding: 0;
}

.agent-board {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 18px;
  min-height: 420px;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
}

.task-card {
  display: grid;
  gap: 5px;
  min-height: 66px;
  padding: 12px;
  text-align: left;
  border: 1px solid rgba(143, 166, 214, 0.14);
  border-radius: 14px;
  background: rgba(5, 10, 20, 0.48);
  color: #eaf2ff;
}

.task-card.active {
  border-color: rgba(118, 213, 255, 0.62);
  background: linear-gradient(135deg, rgba(50, 143, 255, 0.20), rgba(126, 87, 255, 0.16));
}

.task-card span {
  font-weight: 900;
}

.task-card small,
.muted-copy {
  color: #8fa1c6;
  line-height: 1.5;
}

.task-detail {
  display: grid;
  align-content: start;
  gap: 14px;
  padding: 18px;
}

.task-detail-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: start;
}

.task-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.mission-card,
.final-result {
  padding: 14px;
}

.mission-card strong {
  color: #83d8ff;
}

.mission-card p {
  margin: 8px 0 0;
  color: #dce8ff;
  line-height: 1.65;
}

.timeline {
  display: grid;
  gap: 12px;
}

.timeline-step {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 12px;
}

.step-index {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: rgba(143, 166, 214, 0.15);
  color: #dce8ff;
  font-weight: 900;
}

.timeline-step.completed .step-index {
  background: rgba(34, 197, 94, 0.22);
  color: #b8ffd2;
}

.timeline-step.running .step-index {
  background: rgba(59, 130, 246, 0.28);
  color: #bfdbfe;
}

.timeline-step.failed .step-index {
  background: rgba(239, 68, 68, 0.22);
  color: #fecaca;
}

.step-body {
  padding: 14px;
  border: 1px solid rgba(143, 166, 214, 0.14);
  border-radius: 16px;
  background: rgba(5, 10, 20, 0.48);
}

.step-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.step-head strong {
  color: #eef4ff;
}

.step-head span {
  color: #83d8ff;
  font-size: 12px;
  font-weight: 900;
}

.step-output,
.final-result {
  color: #dfebff;
  line-height: 1.72;
}

.empty-task {
  place-content: center;
  text-align: center;
  color: #93a6c9;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  background:
    linear-gradient(rgba(255, 255, 255, 0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.025) 1px, transparent 1px);
  background-size: 34px 34px;
}

.empty-state {
  min-height: 100%;
  display: grid;
  place-content: center;
  justify-items: center;
  text-align: center;
  color: #93a6c9;
}

.empty-orbit {
  width: 94px;
  height: 94px;
  margin-bottom: 22px;
  border: 1px solid rgba(131, 216, 255, 0.35);
  border-radius: 999px;
  background:
    radial-gradient(circle, rgba(131, 216, 255, 0.95) 0 8px, transparent 9px),
    radial-gradient(circle at 70% 28%, rgba(126, 87, 255, 0.9) 0 7px, transparent 8px),
    rgba(255, 255, 255, 0.04);
  box-shadow: 0 0 60px rgba(74, 168, 255, 0.18);
}

.empty-state h2 {
  color: #eef4ff;
  font-size: 28px;
}

.empty-state p {
  max-width: 520px;
  margin: 10px 0 0;
  line-height: 1.7;
}

.prompt-chips {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
  margin-top: 24px;
}

.prompt-chips button {
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid rgba(143, 166, 214, 0.20);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
}

.message-row {
  display: grid;
  gap: 7px;
  margin: 18px 0;
}

.message-row.user {
  justify-items: end;
}

.message-row.ai {
  justify-items: start;
}

.message-meta {
  color: #7283a5;
  font-size: 12px;
  font-weight: 900;
}

.message-bubble {
  max-width: min(820px, 78%);
  padding: 15px 17px;
  border-radius: 18px;
  line-height: 1.72;
  word-break: break-word;
}

.message-row.user .message-bubble {
  background: linear-gradient(135deg, #328fff, #745cff);
  color: #ffffff;
  box-shadow: 0 18px 44px rgba(58, 115, 255, 0.24);
}

.message-row.ai .message-bubble {
  border: 1px solid rgba(143, 166, 214, 0.18);
  background: rgba(255, 255, 255, 0.07);
  color: #dfebff;
}

.message-bubble p {
  margin: 0 0 12px;
}

.message-bubble p:last-child {
  margin-bottom: 0;
}

.message-bubble a {
  color: #83d8ff;
}

.message-bubble pre {
  overflow-x: auto;
  margin: 12px 0;
  padding: 16px;
  border: 1px solid rgba(143, 166, 214, 0.16);
  border-radius: 14px;
  background: #050914;
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
  border-radius: 8px;
  background: rgba(143, 166, 214, 0.20);
  color: #ffffff;
  min-height: 28px;
  padding: 0 10px;
  font-size: 12px;
}

.typing,
.streaming-text {
  white-space: pre-wrap;
}

.typing span {
  display: inline-block;
  width: 5px;
  height: 5px;
  margin-left: 4px;
  border-radius: 999px;
  background: #83d8ff;
}

.chat-error {
  padding: 0 24px 12px;
}

.composer {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  padding: 18px 22px;
  border-top: 1px solid rgba(143, 166, 214, 0.16);
  background: rgba(7, 10, 18, 0.72);
}

.send-button,
.danger-button {
  width: 86px;
  height: 52px;
}

@media (max-width: 980px) {
  .auth-page {
    grid-template-columns: 1fr;
  }

  .hero-panel {
    max-width: 100%;
  }

  .chat-layout {
    grid-template-columns: 1fr;
  }

  .settings-panel,
  .chat-panel {
    min-height: auto;
  }

  .message-bubble {
    max-width: 92%;
  }
}

@media (max-width: 620px) {
  .auth-page,
  .chat-layout {
    padding: 12px;
  }

  .auth-panel,
  .settings-panel {
    padding: 18px;
  }

  .hero-panel h1 {
    font-size: 40px;
  }

  .chat-header,
  .composer {
    align-items: stretch;
    flex-direction: column;
  }

  .header-actions,
  .composer {
    width: 100%;
  }

  .header-actions,
  .task-detail-head {
    align-items: stretch;
    flex-direction: column;
  }

  .agent-create,
  .agent-board {
    grid-template-columns: 1fr;
  }

  .send-button,
  .danger-button {
    width: 100%;
  }
}
</style>
