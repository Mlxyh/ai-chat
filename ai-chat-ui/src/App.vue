<template>
  <div class="app">

    <!-- 顶部 -->
    <div class="header">
      <div class="title">AI Assistant</div>
      <div class="header-right">
        <select v-model="model">
          <option value="deepseek">DeepSeek</option>
          <option value="openai">OpenAI</option>
          <option value="qwen">通义千问</option>
        </select>
        <button class="clear-btn" @click="clearHistory" title="清空对话">清空</button>
      </div>
    </div>

    <!-- 聊天区 -->
    <div class="chat" ref="chatRef">
      <div v-if="messages.length === 0" class="empty-hint">
        选择模型，开始对话
      </div>

      <div
        v-for="(msg, i) in messages"
        :key="i"
        :class="['msg', msg.role]"
      >
        <div class="bubble">
          <div v-if="msg.done" v-html="msg.content || ''"></div>
          <div v-else class="streaming-text">{{ msg.content || '' }}</div>
        </div>
      </div>

      <div v-if="loading" class="msg ai">
        <div class="bubble typing">
          思考中<span class="dots">...</span>
        </div>
      </div>

      <div v-if="errorMsg" class="msg ai">
        <div class="bubble error-bubble">⚠️ {{ errorMsg }}</div>
      </div>
    </div>

    <!-- 输入区 -->
    <div class="input-box">
      <textarea
        v-model="text"
        @keydown.enter.exact.prevent="send"
        @input="autoResize"
        ref="textareaRef"
        placeholder="输入你的问题... (Enter发送，Shift+Enter换行)"
        rows="1"
      ></textarea>
      <button v-if="streaming" class="stop-btn" @click="stop">停止</button>
      <button v-else @click="send" :disabled="loading">发送</button>
    </div>

  </div>
</template>

<script setup>
import { ref, nextTick, watch } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'

const API_URL = import.meta.env.VITE_API_URL || 'http://47.100.215.128:8000'

hljs.configure({ ignoreUnescapedHTML: true })

marked.setOptions({
  highlight: (code) => hljs.highlightAuto(code).value
})

window.copyCode = (btn) => {
  const code = btn.parentElement.querySelector('code').innerText
  navigator.clipboard.writeText(code).then(() => {
    btn.textContent = '已复制!'
    setTimeout(() => btn.textContent = '复制', 2000)
  })
}

const renderMarkdown = (text) => {
  if (!text) return ''
  try {
    let html = marked.parse(text.replace(/pythonprint/g, 'print'))
    html = html.replace(/<pre>/g, '<div class="code-block"><button class="copy-btn" onclick="copyCode(this)">复制</button><pre>')
    html = html.replace(/<\/pre>/g, '</pre></div>')
    return html
  } catch (e) {
    return text
  }
}

const saved = localStorage.getItem('chat-messages')
const text = ref('')
const messages = ref(saved ? JSON.parse(saved) : [])
const model = ref('deepseek')
const loading = ref(false)
const streaming = ref(false)
const errorMsg = ref('')
const chatRef = ref(null)
const textareaRef = ref(null)
let abortController = null

watch(messages, (val) => {
  localStorage.setItem('chat-messages', JSON.stringify(val))
}, { deep: true })

const scrollToBottom = async () => {
  await nextTick()
  if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight
}

const autoResize = () => {
  const ta = textareaRef.value
  if (!ta) return
  ta.style.height = 'auto'
  ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'
}

const clearHistory = () => {
  messages.value = []
  errorMsg.value = ''
}

const stop = () => {
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

const send = async () => {
  if (!text.value.trim() || loading.value) return

  const userInput = text.value
  text.value = ''
  if (textareaRef.value) textareaRef.value.style.height = 'auto'
  errorMsg.value = ''

  messages.value.push({ role: 'user', content: userInput })
  const aiMsg = { role: 'ai', content: '', raw: '', done: false }
  messages.value.push(aiMsg)

  loading.value = true
  streaming.value = false
  scrollToBottom()

  abortController = new AbortController()

  try {
    const response = await fetch(`${API_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: userInput, model: model.value }),
      signal: abortController.signal
    })

    if (!response.ok) throw new Error(`服务器错误 ${response.status}`)

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
  } catch (e) {
    if (e.name !== 'AbortError') {
      errorMsg.value = '连接失败，请检查网络或稍后重试'
      messages.value.pop()
      messages.value.pop()
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
</script>

<style>
.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.clear-btn {
  padding: 8px 14px;
  background: rgba(255, 255, 255, 0.15);
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 12px;
  color: white;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.clear-btn:hover {
  background: rgba(255, 80, 80, 0.4);
  transform: translateY(-2px);
}

.empty-hint {
  text-align: center;
  color: rgba(255, 255, 255, 0.5);
  margin-top: 40vh;
  font-size: 16px;
}

.stop-btn {
  padding: 14px 20px;
  background: rgba(255, 80, 80, 0.7) !important;
  box-shadow: 0 4px 15px rgba(255, 80, 80, 0.4) !important;
}

.stop-btn:hover {
  background: rgba(255, 80, 80, 0.9) !important;
  box-shadow: 0 6px 20px rgba(255, 80, 80, 0.6) !important;
}

.error-bubble {
  background: rgba(255, 80, 80, 0.15) !important;
  border: 1px solid rgba(255, 80, 80, 0.3) !important;
  color: #ff6b6b !important;
}

textarea {
  flex: 1;
  padding: 14px 18px;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 16px;
  color: white;
  font-size: 15px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  resize: none;
  line-height: 1.5;
  transition: all 0.3s ease;
  overflow-y: hidden;
}

textarea::placeholder {
  color: rgba(255, 255, 255, 0.6);
}

textarea:focus {
  outline: none;
  background: rgba(255, 255, 255, 0.25);
  border-color: rgba(255, 255, 255, 0.5);
  box-shadow: 0 0 20px rgba(255, 255, 255, 0.2);
}

.code-block {
  position: relative;
  margin: 10px 0;
}

.copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 4px 10px !important;
  font-size: 12px !important;
  background: rgba(102, 126, 234, 0.8) !important;
  border-radius: 6px !important;
  box-shadow: none !important;
  transform: none !important;
  cursor: pointer;
  z-index: 1;
  border: none;
  color: white;
}

.copy-btn:hover {
  background: rgba(102, 126, 234, 1) !important;
  transform: none !important;
}

body {
  margin: 0;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  overflow: hidden;
}

body::before {
  content: '';
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background:
    radial-gradient(circle at 20% 50%, rgba(120, 119, 198, 0.3), transparent 50%),
    radial-gradient(circle at 80% 80%, rgba(255, 119, 198, 0.3), transparent 50%),
    radial-gradient(circle at 40% 20%, rgba(138, 119, 255, 0.3), transparent 50%);
  animation: gradientShift 15s ease infinite;
  pointer-events: none;
}

@keyframes gradientShift {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.8; transform: scale(1.1); }
}

.app {
  height: 100vh;
  display: flex;
  flex-direction: column;
  position: relative;
  z-index: 1;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(20px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
}

.title {
  font-size: 24px;
  font-weight: 700;
  background: linear-gradient(135deg, #fff 0%, #f0f0f0 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: -0.5px;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

select {
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 12px;
  color: white;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.3s ease;
}

select:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

select option {
  background: #667eea;
  color: white;
}

.chat {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  scroll-behavior: smooth;
}

.chat::-webkit-scrollbar {
  width: 8px;
}

.chat::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 10px;
}

.chat::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.3);
  border-radius: 10px;
}

.chat::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.5);
}

.msg {
  display: flex;
  margin: 16px 0;
  animation: slideIn 0.4s ease;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.msg.user {
  justify-content: flex-end;
}

.msg.ai {
  justify-content: flex-start;
}

.bubble {
  max-width: 70%;
  padding: 14px 18px;
  border-radius: 18px;
  line-height: 1.6;
  font-size: 15px;
  position: relative;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
  transition: all 0.3s ease;
}

.bubble:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15);
}

.msg.user .bubble {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-bottom-right-radius: 4px;
}

.msg.ai .bubble {
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: #333;
  border-bottom-left-radius: 4px;
}

.input-box {
  display: flex;
  gap: 12px;
  padding: 20px 24px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(20px);
  border-top: 1px solid rgba(255, 255, 255, 0.2);
}

input {
  flex: 1;
  padding: 14px 18px;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.3);
  border-radius: 16px;
  color: white;
  font-size: 15px;
  transition: all 0.3s ease;
}

input::placeholder {
  color: rgba(255, 255, 255, 0.6);
}

input:focus {
  outline: none;
  background: rgba(255, 255, 255, 0.25);
  border-color: rgba(255, 255, 255, 0.5);
  box-shadow: 0 0 20px rgba(255, 255, 255, 0.2);
}

button {
  padding: 14px 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border: none;
  border-radius: 16px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
}

button:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
}

button:active {
  transform: translateY(0);
}

.typing {
  display: flex;
  align-items: center;
  gap: 8px;
}

.typing .dots {
  display: inline-flex;
  gap: 4px;
}

.typing .dots::after {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #667eea;
  animation: bounce 1.4s infinite ease-in-out;
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0);
    opacity: 0.5;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

/* 代码块样式 */
.bubble pre {
  background: rgba(0, 0, 0, 0.05);
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0;
}

.bubble code {
  font-family: 'Courier New', monospace;
  font-size: 13px;
}
</style>