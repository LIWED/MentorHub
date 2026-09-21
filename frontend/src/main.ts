import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import 'highlight.js/styles/github.css'
import './assets/styles/neumorphism.css'

import App from './App.vue'
import router from './router'
import MarkdownRenderer from './components/chat/MarkdownRenderer.vue'

const app = createApp(App)

// 注册所有 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

// 注册全局 Markdown 渲染组件，确保所有聊天与问答模块均可直接使用
app.component('MarkdownRenderer', MarkdownRenderer)

// 全局错误兜底：防止 Vue 调度器或组件更新过程中的错误以 unhandled rejection 形式
// 崩溃整个应用。具体恢复逻辑由 AppLayout 的 onErrorCaptured 处理。
app.config.errorHandler = (err, _instance, info) => {
  console.error('[EduAgent] Vue error:', info, err)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: undefined })

app.mount('#app')
