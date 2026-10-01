<template>
  <section class="page">
    <header class="page-head">
      <div>
        <h2>运营概览</h2>
        <p class="page-desc">汇总各业务模块的关键指标，先看总量再看异常；灌木面积每次刷新都按补植明细重算。</p>
      </div>
      <button class="btn" type="button" @click="load">刷新看板</button>
    </header>
    <div class="stat-row">
      <article v-for="card in cards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>

    <div v-if="shrub" class="shrub-panel">
      <h3>灌木养护面积（按补植明细重算）</h3>
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">灌木总数</span>
          <strong class="stat-value">{{ shrub['灌木总数'] }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">待修剪</span>
          <strong class="stat-value">{{ shrub['待修剪'] }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">病虫害</span>
          <strong class="stat-value">{{ shrub['病虫害'] }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">已补植</span>
          <strong class="stat-value">{{ shrub['已补植'] }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">在养面积(㎡)</span>
          <strong class="stat-value">{{ shrub['在养面积'] }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">累计补植面积(㎡)</span>
          <strong class="stat-value">{{ shrub['补植面积合计'] }}</strong>
        </article>
      </div>
    </div>

    <table class="data-table">
      <thead>
        <tr><th>业务模块</th><th>今日新增</th><th>待处理</th><th>异常量</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in moduleRows" :key="row.name">
          <td>{{ row.name }}</td>
          <td>{{ row.created }}</td>
          <td>{{ row.pending }}</td>
          <td>{{ row.abnormal }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { fetchJson } from '@/api/client'

type ShrubSummary = {
  灌木总数: number
  待修剪: number
  病虫害: number
  已补植: number
  在养面积: number
  补植面积合计: number
}
type Overview = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
  shrub?: ShrubSummary
}

const cards = ref<Overview['cards']>([])
const moduleRows = ref<Overview['modules']>([])
const shrub = ref<ShrubSummary | null>(null)

async function load() {
  try {
    const payload = await fetchJson<Overview>('/api/overview')
    cards.value = payload.cards
    moduleRows.value = payload.modules
    shrub.value = payload.shrub ?? null
  } catch {
    cards.value = [
      { label: '业务模块', value: 0 },
      { label: '今日新增', value: 0 },
    ]
    moduleRows.value = []
  }
}

onMounted(load)
</script>

<style scoped>
.shrub-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 14px;
}
.shrub-panel h3 {
  margin: 0 0 10px;
  font-size: 14px;
}
</style>
