<script setup>
import { ref, nextTick } from 'vue'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'

const md = new MarkdownIt({
  highlight: (str, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value
      } catch {}
    }
    return ''
  }
})

const messages = ref([])
const inputText = ref('')
const chatContainer = ref(null)
const isLoading = ref(false)

const sendMessage = async () => {
  if (!inputText.value.trim() || isLoading.value) return

  const userMessage = inputText.value
  messages.value.push({ role: 'user', content: userMessage })
  inputText.value = ''
  isLoading.value = true

  await nextTick()
  scrollToBottom()

  // 模拟 AI 回复
  setTimeout(() => {
    messages.value.push({
      role: 'assistant',
      content: '这是一个演示回复。你可以在这里集成真实的 AI API。\n\n```javascript\nconst example = "支持代码高亮";\nconsole.log(example);\n```'
    })
    isLoading.value = false
    nextTick(() => scrollToBottom())
  }, 1000)
}

const scrollToBottom = () => {
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

const handleKeydown = (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}
</script>

<template>
  <div class="chat-container">
    <div class="chat-header">
      <h1>AI Chat</h1>
    </div>

    <div class="chat-messages" ref="chatContainer">
      <div v-if="messages.length === 0" class="empty-state">
        <div class="welcome">
          <h2>你好，我能帮你什么？</h2>
          <div class="suggestions">
            <button @click="inputText = '帮我写一段代码'">帮我写一段代码</button>
            <button @click="inputText = '解释一个概念'">解释一个概念</button>
            <button @click="inputText = '翻译文本'">翻译文本</button>
          </div>
        </div>
      </div>

      <div v-for="(msg, idx) in messages" :key="idx" :class="['message', msg.role]">
        <div class="message-content">
          <div class="avatar">{{ msg.role === 'user' ? '你' : 'AI' }}</div>
          <div class="text" v-html="md.render(msg.content)"></div>
        </div>
      </div>

      <div v-if="isLoading" class="message assistant">
        <div class="message-content">
          <div class="avatar">AI</div>
          <div class="text loading">
            <span></span><span></span><span></span>
          </div>
        </div>
      </div>
    </div>

    <div class="chat-input">
      <textarea
        v-model="inputText"
        @keydown="handleKeydown"
        placeholder="输入消息... (Enter 发送，Shift+Enter 换行)"
        rows="1"
      ></textarea>
      <button @click="sendMessage" :disabled="!inputText.trim() || isLoading">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
          <path d="M7 11L12 6L17 11M12 18V7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
    </div>
  </div>
</template>
