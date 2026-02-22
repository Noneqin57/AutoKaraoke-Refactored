import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'

// 样式导入
import './styles/variables.css'
import './styles/themes/light.css'
import './styles/themes/dark.css'
import './styles/base.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
