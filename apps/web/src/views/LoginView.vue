<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const email = ref('reader@demo.lawfocus')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref<string | null>(null)

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

async function onSubmit() {
  submitting.value = true
  errorMessage.value = null
  try {
    await auth.login(email.value, password.value)
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } catch {
    errorMessage.value = '登录失败：邮箱或密码不正确'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <form class="login-card" @submit.prevent="onSubmit">
      <h1>登录（演示环境）</h1>
      <label>
        邮箱
        <input v-model="email" type="email" required />
      </label>
      <label>
        密码
        <input v-model="password" type="password" required />
      </label>
      <button :disabled="submitting" type="submit">{{ submitting ? '登录中…' : '登录' }}</button>
      <p v-if="errorMessage" class="error" role="alert">{{ errorMessage }}</p>
      <p class="hint">演示账号密码由部署方通过 LAWFOCUS_DEMO_PASSWORD 环境变量设置。</p>
    </form>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
.login-card {
  background: #fff;
  padding: 32px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  width: 320px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 14px;
}
input {
  padding: 8px;
  border: 1px solid #ccc;
  border-radius: 4px;
}
button {
  padding: 10px;
  background: #1f2d3d;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
button:disabled {
  opacity: 0.6;
  cursor: default;
}
.error {
  color: #c0392b;
  font-size: 13px;
}
.hint {
  color: #888;
  font-size: 12px;
}
</style>
