<template>
  <section class="page" data-module="shrub">
    <header class="page-head">
      <div>
        <h2>灌木管理管理</h2>
        <p class="page-desc">维护灌木，围绕灌木编号、品种名称、栽植面积、修剪周期做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记灌木</button>
        <button class="btn" type="button" @click="exportRows">导出灌木管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in statCards" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>灌木编号</span>
        <input v-model="keyword" placeholder="按灌木编号检索" />
      </label>
      <label class="filter-item">
        <span>灌木状态</span>
        <select v-model="status">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p v-if="feedback.ok" class="feedback feedback-ok" role="status">{{ feedback.text }}</p>
    <p v-else-if="feedback.text" class="feedback feedback-err" role="alert">{{ feedback.text }}</p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>修剪</th>
          <th>防治</th>
          <th>补植</th>
          <th>作业操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <RouterLink v-if="column === '灌木编号'" class="link" :to="`/shrub/${row.id}`">
              {{ row[column] ?? '—' }}
            </RouterLink>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td><span class="stage-tag" data-stage="待处理">{{ stageText(row['修剪状态']) }}</span></td>
          <td><span class="stage-tag">{{ stageText(row['防治状态']) }}</span></td>
          <td><span class="stage-tag">{{ stageText(row['补植状态']) }}</span></td>
          <td>
            <WorkflowActions
              :row="row"
              @finished="onFinished"
              @failed="onFailed"
            />
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 4" class="empty-state">暂无灌木管理数据，可先登记灌木</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条灌木管理记录</span>
      <RouterLink class="link" to="/shrub">养护看板面积随补植明细刷新</RouterLink>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'
import WorkflowActions, { type ShrubRow } from './WorkflowActions.vue'

const ENDPOINT = '/api/shrub'
const columns = ['灌木编号', '品种名称', '栽植面积', '修剪周期', '高度范围', '花开季节', '管护人员', '灌木状态']
const statuses = ['正常', '待修剪', '病虫害', '待补植', '补植中', '已补植']

const rows = ref<ShrubRow[]>([])
const total = ref(0)
const keyword = ref('')
const status = ref('')
const feedback = ref<{ ok: boolean; text: string }>({ ok: true, text: '' })

const statCards = ref<{ label: string; value: number | string }[]>([
  { label: '灌木总数', value: 0 },
  { label: '待修剪灌木', value: 0 },
  { label: '病虫害灌木', value: 0 },
  { label: '已补植灌木', value: 0 },
  { label: '在养面积(㎡)', value: 0 },
  { label: '补植面积合计(㎡)', value: 0 },
])

function stageText(stage: unknown): string {
  return String(stage ?? '—')
}

function resetFilters() {
  keyword.value = ''
  status.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  feedback.value = { ok: false, text: '灌木登记入口尚未接入审批流' }
}

function onFinished(message: string) {
  feedback.value = { ok: true, text: message }
  void reload()
}

function onFailed(message: string) {
  feedback.value = { ok: false, text: message }
  void reload()
}

async function reload() {
  const params = new URLSearchParams()
  if (keyword.value.trim()) params.set('keyword', keyword.value.trim())
  if (status.value) params.set('status', status.value)
  params.set('size', '200')
  try {
    const [listRes, statsRes] = await Promise.all([
      request(`${ENDPOINT}?${params.toString()}`),
      request(`${ENDPOINT}/stats`),
    ])
    if (!listRes.ok) throw new Error('灌木列表读取失败')
    if (!statsRes.ok) throw new Error('灌木看板读取失败')
    const payload = await listRes.json()
    const stats = await statsRes.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    statCards.value = [
      { label: '灌木总数', value: stats['灌木总数'] ?? 0 },
      { label: '待修剪灌木', value: stats['待修剪'] ?? 0 },
      { label: '病虫害灌木', value: stats['病虫害'] ?? 0 },
      { label: '已补植灌木', value: stats['已补植'] ?? 0 },
      { label: '在养面积(㎡)', value: stats['在养面积'] ?? 0 },
      { label: '补植面积合计(㎡)', value: stats['补植面积合计'] ?? 0 },
    ]
  } catch (error) {
    feedback.value = {
      ok: false,
      text: error instanceof Error ? error.message : '灌木管理列表读取失败',
    }
  }
}

onMounted(reload)
</script>

<style scoped>
.feedback {
  margin: 0 0 10px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.feedback-ok {
  color: #067647;
  background: #ecfdf3;
  border: 1px solid #abefc6;
}
.feedback-err {
  color: #b42318;
  background: #fef3f2;
  border: 1px solid #fda29b;
}
.stage-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
  border: 1px solid var(--border);
  color: var(--muted);
  white-space: nowrap;
}
</style>
