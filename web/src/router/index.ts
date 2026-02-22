import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
    history: createWebHistory(),
    routes: [
        {
            path: '/',
            name: 'main',
            component: () => import('@/views/MainView.vue'),
            meta: { title: 'REATK - 歌词生成' }
        },
        {
            path: '/editor',
            name: 'editor',
            component: () => import('@/views/EditorView.vue'),
            meta: { title: 'REATK - 逐行编辑' }
        },
        {
            path: '/editor/word',
            name: 'word-editor',
            component: () => import('@/views/WordEditorView.vue'),
            meta: { title: 'REATK - 逐字编辑' }
        },
        {
            path: '/batch',
            name: 'batch',
            component: () => import('@/views/BatchView.vue'),
            meta: { title: 'REATK - 批量生成' }
        },
        {
            path: '/settings',
            name: 'settings',
            component: () => import('@/views/SettingsView.vue'),
            meta: { title: 'REATK - 设置' }
        }
    ]
})

// 路由导航守卫：更新页面标题
router.beforeEach((to) => {
    document.title = (to.meta.title as string) || 'REATK'
})

export default router
