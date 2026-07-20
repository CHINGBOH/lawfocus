<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const canAudit = computed(() => auth.roleCodes.some((r) => r === 'AUDITOR' || r === 'SYSTEM_ADMIN'))
</script>

<template>
  <header class="app-header">
    <span class="app-title">经济法知识仓库（演示 / MVP 骨架）</span>
    <nav v-if="auth.isAuthenticated" class="app-nav">
      <router-link to="/workbench">工作台</router-link>
      <router-link to="/">法律仓库</router-link>
      <router-link to="/subjects">上市公司</router-link>
      <router-link to="/compliance-checks/new">合规检查</router-link>
      <router-link to="/rules">规则中心</router-link>
      <router-link v-if="canAudit" to="/audit">审计</router-link>
    </nav>
    <button v-if="auth.isAuthenticated" class="logout-btn" @click="auth.logout()">退出登录</button>
  </header>
  <main class="app-main">
    <router-view />
  </main>
</template>

<style>
* {
  box-sizing: border-box;
}
body {
  margin: 0;
  font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: #f5f6f8;
}
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  background: #1f2d3d;
  color: #fff;
  gap: 20px;
}
.app-title {
  font-weight: 600;
  white-space: nowrap;
}
.app-nav {
  display: flex;
  gap: 16px;
  flex: 1;
}
.app-nav a {
  color: #ffffffcc;
  text-decoration: none;
  font-size: 14px;
}
.app-nav a:hover,
.app-nav a.router-link-active {
  color: #fff;
  text-decoration: underline;
}
.logout-btn {
  background: transparent;
  border: 1px solid #ffffff66;
  color: #fff;
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
}
.app-main {
  height: calc(100vh - 48px);
  overflow-y: auto;
}
</style>
