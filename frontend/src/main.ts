/**
 * DataMind — Talk to Your Data
 * Main Frontend Application Logic
 */

import './index.css'

// ─── Interfaces ───

interface HealthResponse {
  status: string
  snowflake_connected: boolean
  gemma_available: boolean
  snowflake_message: string
  gemma_message: string
}

interface ColumnInfo {
  column_name: string
  data_type: string
  is_nullable: boolean
  comment?: string | null
}

interface TableInfo {
  table_name: string
  row_count?: number | null
  columns: ColumnInfo[]
  comment?: string | null
}

interface SchemaInfo {
  database_name: string
  schema_name: string
  tables: TableInfo[]
  discovered_at?: string
}

interface SchemaExplorerResponse {
  connected: boolean
  schema_info?: SchemaInfo | null
  database?: string | null
  schema_name?: string | null
  error?: string | null
}

interface EvidenceDetail {
  executed_sql?: string | null
  proposed_sql?: string | null
  source_tables?: string[]
  referenced_columns?: string[]
  applied_filters?: string[]
  assumptions?: string[]
  query_id?: string | null
  execution_duration_ms?: number | null
  row_count?: number | null
  warnings?: string[]
  limitations?: string[]
  execution_status?: string | null
}

interface AnswerResponse {
  question: string
  status: 'success' | 'clarification_needed' | 'empty_result' | 'unsupported' | 'error'
  answer: string
  interpretation?: string | null
  data?: Record<string, any>[] | null
  columns?: string[] | null
  evidence?: EvidenceDetail | null
  clarification_options?: string[] | null
  error?: string | null
  error_type?: string | null
}

interface ExampleQuestion {
  question: string
  category: string
}

// ─── Application State ───

interface AppState {
  health: HealthResponse | null
  schema: SchemaExplorerResponse | null
  examples: ExampleQuestion[]
  currentQuestion: string
  isLoading: boolean
  loadingStep: number
  loadingInterval: number | null
  currentAnswer: AnswerResponse | null
  activeTab: 'table' | 'chart'
  schemaFilter: string
  expandedTables: Record<string, boolean>
  evidenceOpen: {
    sql: boolean
    sources: boolean
    meta: boolean
    limitations: boolean
  }
}

const state: AppState = {
  health: null,
  schema: null,
  examples: [],
  currentQuestion: '',
  isLoading: false,
  loadingStep: 0,
  loadingInterval: null,
  currentAnswer: null,
  activeTab: 'table',
  schemaFilter: '',
  expandedTables: {},
  evidenceOpen: {
    sql: true,
    sources: true,
    meta: true,
    limitations: false,
  },
}

const API_BASE = '/api'

// ─── API Methods ───

async function fetchHealth(): Promise<HealthResponse> {
  try {
    const res = await fetch(`${API_BASE}/health`)
    if (!res.ok) throw new Error(`HTTP error ${res.status}`)
    return await res.json()
  } catch (err) {
    return {
      status: 'degraded',
      snowflake_connected: false,
      gemma_available: false,
      snowflake_message: 'Cannot reach backend server. Ensure backend is running on port 8000.',
      gemma_message: 'Cannot reach backend server.',
    }
  }
}

async function fetchSchema(refresh = false): Promise<SchemaExplorerResponse> {
  try {
    const url = refresh ? `${API_BASE}/schema/refresh` : `${API_BASE}/schema`
    const method = refresh ? 'POST' : 'GET'
    const res = await fetch(url, { method })
    if (!res.ok) throw new Error(`HTTP error ${res.status}`)
    return await res.json()
  } catch (err) {
    return {
      connected: false,
      error: 'Failed to load database schema from backend.',
    }
  }
}

async function fetchExamples(): Promise<ExampleQuestion[]> {
  try {
    const res = await fetch(`${API_BASE}/examples`)
    if (!res.ok) throw new Error(`HTTP error ${res.status}`)
    const data = await res.json()
    return data.examples || []
  } catch (err) {
    return [
      { question: 'Which countries had the highest GDP in the latest available year?', category: 'Ranking' },
      { question: 'What is the average life expectancy by continent?', category: 'Aggregation' },
      { question: 'Compare the population of the top 5 most populated countries over time.', category: 'Comparison' },
      { question: 'Which country has the highest CO2 emissions per capita?', category: 'Filtering' },
      { question: 'Show the trend of global GDP from 2000 to 2020.', category: 'Time Series' },
    ]
  }
}

async function askQuestion(question: string): Promise<AnswerResponse> {
  const res = await fetch(`${API_BASE}/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })

  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}))
    throw new Error(errBody.detail || `Request failed with status ${res.status}`)
  }

  return await res.json()
}

// ─── Rendering Helpers ───

function escapeHtml(text: string | null | undefined): string {
  if (text == null) return ''
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

function formatValue(val: any): string {
  if (val === null || val === undefined) {
    return '<span class="null-value">null</span>'
  }
  if (typeof val === 'number') {
    return val.toLocaleString(undefined, { maximumFractionDigits: 4 })
  }
  if (typeof val === 'boolean') {
    return val ? 'TRUE' : 'FALSE'
  }
  return escapeHtml(String(val))
}

// ─── Chart Generator (Responsive SVG) ───

function generateSVGChart(data: Record<string, any>[], columns: string[]): string {
  if (!data || data.length === 0 || columns.length < 2) {
    return '<div class="empty-state"><p>Insufficient data to render chart.</p></div>'
  }

  // Detect numeric vs categorical columns
  const firstRow = data[0]
  let labelCol = columns[0]
  let valCols: string[] = []

  for (const col of columns) {
    const val = firstRow[col]
    if (typeof val === 'number') {
      valCols.push(col)
    } else if (!valCols.includes(col) && valCols.length === 0) {
      labelCol = col
    }
  }

  if (valCols.length === 0) {
    return '<div class="empty-state"><p>No numerical columns available for chart visualization.</p></div>'
  }

  // Chart configuration
  const primaryValCol = valCols[0]
  const chartData = data.slice(0, 15) // Limit to top 15 for clean visualization
  const width = 760
  const height = 340
  const margin = { top: 30, right: 30, bottom: 65, left: 75 }
  const innerWidth = width - margin.left - margin.right
  const innerHeight = height - margin.top - margin.bottom

  const values = chartData.map(d => Number(d[primaryValCol]) || 0)
  const maxVal = Math.max(...values, 1)
  const minVal = Math.min(0, Math.min(...values))
  const range = maxVal - minVal || 1

  const barWidth = Math.max(12, Math.min(45, (innerWidth / chartData.length) - 10))

  // Gridlines and Y ticks
  const ticks = [0, 0.25, 0.5, 0.75, 1.0]
  const gridLines = ticks.map(t => {
    const tickVal = minVal + t * range
    const yPos = innerHeight - ((tickVal - minVal) / range) * innerHeight
    return `
      <line x1="0" y1="${yPos}" x2="${innerWidth}" y2="${yPos}" class="chart-grid" />
      <text x="-10" y="${yPos + 4}" text-anchor="end" class="chart-axis-label">${tickVal >= 1000000 ? (tickVal / 1000000).toFixed(1) + 'M' : tickVal >= 1000 ? (tickVal / 1000).toFixed(1) + 'k' : tickVal.toFixed(1)}</text>
    `
  }).join('')

  // Bars
  const bars = chartData.map((d, i) => {
    const val = Number(d[primaryValCol]) || 0
    const rawLabel = String(d[labelCol] || `Item ${i + 1}`)
    const label = rawLabel.length > 14 ? rawLabel.substring(0, 12) + '…' : rawLabel
    const barHeight = Math.max(2, ((val - Math.max(0, minVal)) / range) * innerHeight)
    const x = i * (innerWidth / chartData.length) + (innerWidth / chartData.length - barWidth) / 2
    const y = innerHeight - barHeight

    return `
      <g class="chart-bar-group">
        <title>${escapeHtml(rawLabel)}: ${val.toLocaleString()}</title>
        <rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="4" fill="url(#chartGrad)" class="chart-bar" />
        <text x="${x + barWidth / 2}" y="${y - 8}" text-anchor="middle" font-size="10" fill="#94a3b8" font-family="JetBrains Mono, monospace">
          ${val >= 1000000 ? (val / 1000000).toFixed(1) + 'M' : val >= 1000 ? (val / 1000).toFixed(1) + 'k' : val.toLocaleString()}
        </text>
        <text x="${x + barWidth / 2}" y="${innerHeight + 18}" text-anchor="end" transform="rotate(-35, ${x + barWidth / 2}, ${innerHeight + 18})" font-size="11" fill="#94a3b8">
          ${escapeHtml(label)}
        </text>
      </g>
    `
  }).join('')

  return `
    <div class="svg-chart-wrapper">
      <svg class="svg-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#818cf8" />
            <stop offset="100%" stop-color="#4f46e5" />
          </linearGradient>
        </defs>
        <g transform="translate(${margin.left}, ${margin.top})">
          <!-- Grid & Y Axis -->
          <g class="chart-axis">${gridLines}</g>
          <!-- Baseline -->
          <line x1="0" y1="${innerHeight}" x2="${innerWidth}" y2="${innerHeight}" stroke="#334155" stroke-width="1.5" />
          <!-- Bars -->
          ${bars}
        </g>
        <!-- Axis Titles -->
        <text x="${width / 2}" y="${height - 5}" text-anchor="middle" font-size="11" fill="#64748b">${escapeHtml(labelCol)}</text>
        <text x="18" y="${height / 2}" text-anchor="middle" transform="rotate(-90, 18, ${height / 2})" font-size="11" fill="#64748b">${escapeHtml(primaryValCol)}</text>
      </svg>
    </div>
  `
}

// ─── Main Render Function ───

function render(): void {
  const app = document.querySelector<HTMLDivElement>('#app')
  if (!app) return

  const { health, schema, examples, currentQuestion, isLoading, loadingStep, currentAnswer, activeTab, schemaFilter } = state

  // Filter schema tables by search term
  const tables = schema?.schema_info?.tables || []
  const filteredTables = tables.filter(t =>
    t.table_name.toLowerCase().includes(schemaFilter.toLowerCase()) ||
    t.columns.some(c => c.column_name.toLowerCase().includes(schemaFilter.toLowerCase()))
  )

  app.innerHTML = `
    <div class="app-container">
      <!-- ─── Header ─── -->
      <header class="app-header">
        <div class="header-content">
          <div class="logo-section">
            <div class="logo-icon">🧠</div>
            <div>
              <div class="logo-text">DataMind</div>
              <div style="font-size: 0.6875rem; color: var(--color-text-muted); letter-spacing: 0.05em; text-transform: uppercase;">
                Talk to Your Data • Gemma + Snowflake
              </div>
            </div>
          </div>

          <div class="header-status">
            <!-- Snowflake Status Badge -->
            <div class="status-badge" title="${escapeHtml(health?.snowflake_message || 'Checking Snowflake...')}">
              <span class="status-dot ${health?.snowflake_connected ? 'connected' : 'disconnected'}"></span>
              <span>Snowflake: ${health?.snowflake_connected ? 'Connected' : 'Offline'}</span>
            </div>

            <!-- Gemma Status Badge -->
            <div class="status-badge" title="${escapeHtml(health?.gemma_message || 'Checking Gemma...')}">
              <span class="status-dot ${health?.gemma_available ? 'connected' : 'disconnected'}"></span>
              <span>Gemma: ${health?.gemma_available ? 'Ready' : 'Unavailable'}</span>
            </div>

            <!-- Refresh Health Action -->
            <button id="btn-refresh-health" class="refresh-btn" title="Refresh service health">
              ↻ Refresh
            </button>
          </div>
        </div>
      </header>

      <!-- ─── Main Content ─── -->
      <main class="main-content">
        <!-- ─── Sidebar: Schema Explorer ─── -->
        <aside class="sidebar">
          <div class="schema-explorer">
            <div class="schema-header">
              <h3>Schema Explorer</h3>
              <button id="btn-refresh-schema" class="refresh-btn" title="Refresh database schema">
                ↻ Refresh
              </button>
            </div>

            <div class="schema-body">
              ${schema?.connected ? `
                <input
                  type="text"
                  id="schema-search-input"
                  class="schema-search"
                  placeholder="Filter tables & columns..."
                  value="${escapeHtml(schemaFilter)}"
                />
                <div style="font-size: var(--text-xs); color: var(--color-text-muted); margin-bottom: var(--space-3); font-family: var(--font-mono);">
                  ${escapeHtml(schema.database || '')}.${escapeHtml(schema.schema_name || 'PUBLIC')}
                </div>
                ${filteredTables.length === 0 ? `
                  <div style="padding: var(--space-4); text-align: center; color: var(--color-text-muted); font-size: var(--text-xs);">
                    No matching tables found.
                  </div>
                ` : filteredTables.map(tbl => `
                  <div class="schema-table">
                    <div class="schema-table-header" data-table="${escapeHtml(tbl.table_name)}">
                      <span class="table-icon">🗄️</span>
                      <span style="flex: 1;">${escapeHtml(tbl.table_name)}</span>
                      <span style="font-size: 0.6875rem; color: var(--color-text-muted); font-family: var(--font-mono);">
                        ${tbl.columns.length} cols
                      </span>
                    </div>
                    ${state.expandedTables[tbl.table_name] ? `
                      <div class="schema-column-list">
                        ${tbl.columns.map(c => `
                          <div class="schema-column" title="${escapeHtml(c.comment || c.data_type)}">
                            <span style="color: var(--color-accent); font-size: 10px;">▪</span>
                            <span style="flex: 1;">${escapeHtml(c.column_name)}</span>
                            <span class="col-type">${escapeHtml(c.data_type)}</span>
                          </div>
                        `).join('')}
                      </div>
                    ` : ''}
                  </div>
                `).join('')}
              ` : `
                <div class="schema-not-connected">
                  <div style="font-size: 2rem; margin-bottom: var(--space-2); opacity: 0.5;">🔒</div>
                  <div style="font-weight: 600; color: var(--color-text-secondary); margin-bottom: var(--space-1);">
                    Snowflake Not Connected
                  </div>
                  <p style="font-size: var(--text-xs); color: var(--color-text-muted); margin-bottom: var(--space-3);">
                    Configure Snowflake credentials in <code>.env</code> to discover schema and run queries.
                  </p>
                  <button id="btn-toggle-setup" class="submit-btn" style="width: 100%; justify-content: center; padding: 6px 12px; font-size: var(--text-xs);">
                    Setup Instructions
                  </button>
                </div>
              `}
            </div>
          </div>

          <!-- Quick System Architecture Info -->
          <div style="background: var(--color-bg-card); border: 1px solid var(--color-border); border-radius: var(--radius-md); padding: var(--space-4); font-size: var(--text-xs); color: var(--color-text-secondary);">
            <div style="font-weight: 600; color: var(--color-text-primary); margin-bottom: var(--space-2); display: flex; align-items: center; gap: 6px;">
              <span>🛡️</span> Zero-Trust Execution Flow
            </div>
            <p style="margin-bottom: var(--space-2); line-height: 1.5;">
              Questions are parsed by <strong>Gemma</strong>, strictly validated against read-only SQL rules with <strong>sqlglot</strong>, and executed against <strong>Snowflake</strong> with automatic limits.
            </p>
            <div style="font-family: var(--font-mono); font-size: 10px; color: var(--color-accent); background: var(--color-bg-primary); padding: 6px; border-radius: 4px;">
              Natural Language → Gemma → SQLGlot → Snowflake → Grounded Evidence
            </div>
          </div>
        </aside>

        <!-- ─── Workspace Area ─── -->
        <section class="workspace">
          <!-- Setup Guide Callout (if degraded) -->
          ${(!health?.snowflake_connected || !health?.gemma_available) ? `
            <div class="setup-guide-card">
              <h4>⚠️ Environment Configuration Required</h4>
              <p style="font-size: var(--text-xs); color: var(--color-text-secondary); margin-bottom: var(--space-3);">
                DataMind strictly queries real data at question time and uses Gemma for analysis. Complete these steps to enable full live querying:
              </p>
              <ol>
                ${!health?.snowflake_connected ? `
                  <li><strong>Configure Snowflake:</strong> Copy <code>.env.example</code> to <code>.env</code> and set <code>SNOWFLAKE_ACCOUNT</code>, <code>SNOWFLAKE_USER</code>, <code>SNOWFLAKE_PASSWORD</code>, <code>SNOWFLAKE_WAREHOUSE</code>, and <code>SNOWFLAKE_DATABASE</code>.</li>
                ` : ''}
                ${!health?.gemma_available ? `
                  <li><strong>Start Gemma via Ollama:</strong> Install Ollama from <a href="https://ollama.com" target="_blank" style="color: var(--color-accent);">ollama.com</a> and run: <code>ollama run gemma3:4b</code> (or set <code>GEMMA_MODEL=gemma3:4b</code>).</li>
                ` : ''}
              </ol>
            </div>
          ` : ''}

          <!-- ─── Question Section ─── -->
          <div class="question-section">
            <h2>Ask Your Data Anything</h2>
            <p class="subtitle">
              Ask natural-language questions about your structured dataset. Results are dynamically queried and verified with complete evidence.
            </p>

            <form id="question-form">
              <div class="question-input-wrapper">
                <textarea
                  id="question-input"
                  class="question-input"
                  placeholder="e.g. Which countries had the highest GDP growth in the latest available year?"
                  rows="2"
                  ${isLoading ? 'disabled' : ''}
                >${escapeHtml(currentQuestion)}</textarea>
                <button
                  type="submit"
                  id="submit-btn"
                  class="submit-btn ${isLoading ? 'loading' : ''}"
                  ${isLoading || !currentQuestion.trim() ? 'disabled' : ''}
                >
                  ${isLoading ? 'Analyzing...' : 'Ask DataMind ✨'}
                </button>
              </div>
            </form>

            <!-- Example Question Chips -->
            ${examples.length > 0 ? `
              <div style="font-size: var(--text-xs); font-weight: 600; color: var(--color-text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: var(--space-2);">
                Suggested Questions
              </div>
              <div class="examples-section">
                ${examples.map(ex => `
                  <button type="button" class="example-chip" data-question="${escapeHtml(ex.question)}">
                    <span style="opacity: 0.6; margin-right: 4px;">${escapeHtml(ex.category)}:</span>
                    ${escapeHtml(ex.question)}
                  </button>
                `).join('')}
              </div>
            ` : ''}
          </div>

          <!-- ─── Loading State ─── -->
          ${isLoading ? `
            <div class="answer-panel">
              <div class="loading-panel">
                <div class="loading-spinner"></div>
                <div class="loading-text" style="font-weight: 600; color: var(--color-text-primary);">
                  Analyzing your data with Gemma & Snowflake...
                </div>
                <div class="loading-steps">
                  <div class="loading-step ${loadingStep >= 0 ? (loadingStep === 0 ? 'active' : 'done') : ''}">
                    <span>${loadingStep > 0 ? '✓' : '●'}</span>
                    <span>Interpreting question with Gemma AI...</span>
                  </div>
                  <div class="loading-step ${loadingStep >= 1 ? (loadingStep === 1 ? 'active' : 'done') : ''}">
                    <span>${loadingStep > 1 ? '✓' : '●'}</span>
                    <span>Validating SQL safety & schema conformance with SQLGlot...</span>
                  </div>
                  <div class="loading-step ${loadingStep >= 2 ? (loadingStep === 2 ? 'active' : 'done') : ''}">
                    <span>${loadingStep > 2 ? '✓' : '●'}</span>
                    <span>Executing query against Snowflake warehouse...</span>
                  </div>
                  <div class="loading-step ${loadingStep >= 3 ? 'active' : ''}">
                    <span>●</span>
                    <span>Synthesizing grounded explanation & assembling evidence...</span>
                  </div>
                </div>
              </div>
            </div>
          ` : ''}

          <!-- ─── Answer & Evidence Panel ─── -->
          ${!isLoading && currentAnswer ? `
            <div class="answer-panel">
              <!-- Answer Header -->
              <div class="answer-header">
                <div class="answer-status-icon ${currentAnswer.status === 'success' ? 'success' : currentAnswer.status === 'clarification_needed' ? 'info' : currentAnswer.status === 'empty_result' ? 'warning' : 'error'}">
                  ${currentAnswer.status === 'success' ? '✓' : currentAnswer.status === 'clarification_needed' ? '❓' : currentAnswer.status === 'empty_result' ? '🔍' : '⚠️'}
                </div>
                <div style="flex: 1;">
                  <div style="font-weight: 600; font-size: var(--text-base); color: var(--color-text-primary);">
                    ${currentAnswer.status === 'success' ? 'Grounded Analysis' : currentAnswer.status === 'clarification_needed' ? 'Clarification Required' : currentAnswer.status === 'empty_result' ? 'No Matching Records' : 'Analysis Notice'}
                  </div>
                  <div style="font-size: var(--text-xs); color: var(--color-text-muted);">
                    Question: "${escapeHtml(currentAnswer.question)}"
                  </div>
                </div>

                <!-- Execution status pill -->
                ${currentAnswer.evidence?.execution_duration_ms ? `
                  <div style="font-size: var(--text-xs); font-family: var(--font-mono); color: var(--color-text-secondary); background: var(--color-bg-elevated); padding: 4px 8px; border-radius: var(--radius-sm); border: 1px solid var(--color-border);">
                    ⏱️ ${currentAnswer.evidence.execution_duration_ms.toFixed(0)} ms
                  </div>
                ` : ''}
              </div>

              <!-- Answer Body -->
              <div class="answer-body">
                <!-- Gemma Interpretation Badge -->
                ${currentAnswer.interpretation ? `
                  <div class="interpretation-badge">
                    <div class="label">🤖 Gemma Interpretation</div>
                    <div>${escapeHtml(currentAnswer.interpretation)}</div>
                  </div>
                ` : ''}

                <!-- Direct Answer Text -->
                <div class="answer-text">
                  <p>${escapeHtml(currentAnswer.answer)}</p>
                </div>

                <!-- Clarification Options -->
                ${currentAnswer.status === 'clarification_needed' && currentAnswer.clarification_options && currentAnswer.clarification_options.length > 0 ? `
                  <div class="clarification-box">
                    <h4>Possible interpretations to choose from:</h4>
                    <div style="display: flex; flex-direction: column; gap: var(--space-2); margin-top: var(--space-2);">
                      ${currentAnswer.clarification_options.map(opt => `
                        <button type="button" class="example-chip clarification-option" data-question="${escapeHtml(opt)}" style="text-align: left;">
                          ➔ ${escapeHtml(opt)}
                        </button>
                      `).join('')}
                    </div>
                  </div>
                ` : ''}

                <!-- Error Box -->
                ${currentAnswer.error ? `
                  <div class="error-box" style="margin-top: var(--space-4);">
                    <h4>${escapeHtml(currentAnswer.error_type || 'Error')}</h4>
                    <p>${escapeHtml(currentAnswer.error)}</p>
                  </div>
                ` : ''}

                <!-- Warnings Box -->
                ${currentAnswer.evidence?.warnings && currentAnswer.evidence.warnings.length > 0 ? `
                  <div class="warning-box">
                    <div style="font-weight: 600; color: var(--color-warning); font-size: var(--text-xs); margin-bottom: 4px;">⚠️ Safety Notices</div>
                    <ul style="padding-left: var(--space-4); font-size: var(--text-xs); color: var(--color-text-secondary);">
                      ${currentAnswer.evidence.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('')}
                    </ul>
                  </div>
                ` : ''}

                <!-- Data Table & Chart Section -->
                ${currentAnswer.data && currentAnswer.data.length > 0 ? `
                  <div class="data-table-section">
                    <div class="data-table-header">
                      <div style="display: flex; align-items: center; gap: var(--space-3);">
                        <h4>Query Results (${currentAnswer.data.length} ${currentAnswer.data.length === 1 ? 'row' : 'rows'})</h4>
                        <!-- View Toggle Tabs -->
                        <div class="view-tabs">
                          <button type="button" id="tab-table" class="tab-btn ${activeTab === 'table' ? 'active' : ''}">Table</button>
                          <button type="button" id="tab-chart" class="tab-btn ${activeTab === 'chart' ? 'active' : ''}">Chart 📊</button>
                        </div>
                      </div>

                      <div style="display: flex; align-items: center; gap: var(--space-2);">
                        <button type="button" id="btn-export-csv" class="refresh-btn" title="Download results as CSV">
                          ⬇️ Export CSV
                        </button>
                      </div>
                    </div>

                    <!-- Table View -->
                    ${activeTab === 'table' ? `
                      <div class="data-table-wrapper">
                        <table class="data-table">
                          <thead>
                            <tr>
                              ${(currentAnswer.columns || Object.keys(currentAnswer.data[0] || {})).map(col => `
                                <th>${escapeHtml(col)}</th>
                              `).join('')}
                            </tr>
                          </thead>
                          <tbody>
                            ${currentAnswer.data.map(row => `
                              <tr>
                                ${(currentAnswer.columns || Object.keys(row)).map(col => `
                                  <td>${formatValue(row[col])}</td>
                                `).join('')}
                              </tr>
                            `).join('')}
                          </tbody>
                        </table>
                      </div>
                    ` : `
                      <!-- Chart View -->
                      <div class="chart-container">
                        ${generateSVGChart(currentAnswer.data, currentAnswer.columns || Object.keys(currentAnswer.data[0] || {}))}
                      </div>
                    `}
                  </div>
                ` : ''}

                <!-- Evidence Inspector (M5 Requirement) -->
                ${currentAnswer.evidence ? `
                  <div class="evidence-panel">
                    <!-- Executed SQL Section -->
                    <div class="evidence-section">
                      <button type="button" class="evidence-toggle" data-target="sql">
                        <span>🔍 Executed SQL Query (${currentAnswer.evidence.executed_sql ? 'Snowflake Executed' : 'Proposed Only'})</span>
                        <span class="chevron ${state.evidenceOpen.sql ? 'open' : ''}">▼</span>
                      </button>
                      ${state.evidenceOpen.sql ? `
                        <div class="evidence-content">
                          <div class="sql-container">
                            <button type="button" id="btn-copy-sql" class="copy-btn" title="Copy SQL query">
                              📋 Copy
                            </button>
                            <pre class="sql-block"><code>${escapeHtml(currentAnswer.evidence.executed_sql || currentAnswer.evidence.proposed_sql || 'No SQL query generated.')}</code></pre>
                          </div>
                        </div>
                      ` : ''}
                    </div>

                    <!-- Source Tables and Filters Section -->
                    <div class="evidence-section">
                      <button type="button" class="evidence-toggle" data-target="sources">
                        <span>📑 Sources, Columns & Filters</span>
                        <span class="chevron ${state.evidenceOpen.sources ? 'open' : ''}">▼</span>
                      </button>
                      ${state.evidenceOpen.sources ? `
                        <div class="evidence-content">
                          <ul class="evidence-list">
                            <li><strong>Referenced Tables:</strong> ${currentAnswer.evidence.source_tables && currentAnswer.evidence.source_tables.length > 0 ? escapeHtml(currentAnswer.evidence.source_tables.join(', ')) : 'None'}</li>
                            <li><strong>Referenced Columns:</strong> ${currentAnswer.evidence.referenced_columns && currentAnswer.evidence.referenced_columns.length > 0 ? escapeHtml(currentAnswer.evidence.referenced_columns.join(', ')) : 'All (*) or aggregated'}</li>
                            ${currentAnswer.evidence.applied_filters && currentAnswer.evidence.applied_filters.length > 0 ? `
                              <li><strong>Applied Filters:</strong> ${escapeHtml(currentAnswer.evidence.applied_filters.join('; '))}</li>
                            ` : ''}
                            ${currentAnswer.evidence.assumptions && currentAnswer.evidence.assumptions.length > 0 ? `
                              <li><strong>Assumptions Made:</strong> ${escapeHtml(currentAnswer.evidence.assumptions.join('; '))}</li>
                            ` : ''}
                          </ul>
                        </div>
                      ` : ''}
                    </div>

                    <!-- Query Metadata Section -->
                    <div class="evidence-section">
                      <button type="button" class="evidence-toggle" data-target="meta">
                        <span>⏱️ Execution Metadata & Audit</span>
                        <span class="chevron ${state.evidenceOpen.meta ? 'open' : ''}">▼</span>
                      </button>
                      ${state.evidenceOpen.meta ? `
                        <div class="evidence-content">
                          <div class="evidence-meta">
                            <div class="evidence-meta-item">
                              <div class="evidence-meta-label">Execution Status</div>
                              <div class="evidence-meta-value">${escapeHtml(currentAnswer.evidence.execution_status || 'unknown')}</div>
                            </div>
                            <div class="evidence-meta-item">
                              <div class="evidence-meta-label">Snowflake Query ID</div>
                              <div class="evidence-meta-value">${escapeHtml(currentAnswer.evidence.query_id || 'N/A')}</div>
                            </div>
                            <div class="evidence-meta-item">
                              <div class="evidence-meta-label">Rows Returned</div>
                              <div class="evidence-meta-value">${currentAnswer.evidence.row_count != null ? currentAnswer.evidence.row_count : (currentAnswer.data ? currentAnswer.data.length : 0)}</div>
                            </div>
                            <div class="evidence-meta-item">
                              <div class="evidence-meta-label">Execution Time</div>
                              <div class="evidence-meta-value">${currentAnswer.evidence.execution_duration_ms ? currentAnswer.evidence.execution_duration_ms.toFixed(1) + ' ms' : 'N/A'}</div>
                            </div>
                          </div>
                        </div>
                      ` : ''}
                    </div>

                    <!-- Limitations Section -->
                    ${currentAnswer.evidence.limitations && currentAnswer.evidence.limitations.length > 0 ? `
                      <div class="evidence-section">
                        <button type="button" class="evidence-toggle" data-target="limitations">
                          <span>⚠️ Data Limitations</span>
                          <span class="chevron ${state.evidenceOpen.limitations ? 'open' : ''}">▼</span>
                        </button>
                        ${state.evidenceOpen.limitations ? `
                          <div class="evidence-content">
                            <ul class="evidence-list">
                              ${currentAnswer.evidence.limitations.map(lim => `<li>${escapeHtml(lim)}</li>`).join('')}
                            </ul>
                          </div>
                        ` : ''}
                      </div>
                    ` : ''}
                  </div>
                ` : ''}
              </div>
            </div>
          ` : ''}

          <!-- ─── Empty State (When no question asked yet) ─── -->
          ${!isLoading && !currentAnswer ? `
            <div class="answer-panel">
              <div class="empty-state">
                <div class="empty-state-icon">💡</div>
                <h3>Ready to Query Your Structured Data</h3>
                <p>
                  Type a question above or click one of the suggested example questions to generate schema-aware SQL, run it on Snowflake, and inspect grounded answers.
                </p>
              </div>
            </div>
          ` : ''}
        </section>
      </main>
    </div>
  `

  attachEventHandlers()
}

// ─── Event Handling ───

function attachEventHandlers(): void {
  // Question form submit
  const form = document.querySelector<HTMLFormElement>('#question-form')
  const textarea = document.querySelector<HTMLTextAreaElement>('#question-input')

  if (textarea) {
    textarea.addEventListener('input', (e) => {
      state.currentQuestion = (e.target as HTMLTextAreaElement).value
      const submitBtn = document.querySelector<HTMLButtonElement>('#submit-btn')
      if (submitBtn) {
        submitBtn.disabled = !state.currentQuestion.trim() || state.isLoading
      }
    })

    textarea.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        if (state.currentQuestion.trim() && !state.isLoading) {
          submitQuestion(state.currentQuestion.trim())
        }
      }
    })
  }

  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault()
      if (state.currentQuestion.trim() && !state.isLoading) {
        submitQuestion(state.currentQuestion.trim())
      }
    })
  }

  // Example question chips
  document.querySelectorAll<HTMLButtonElement>('.example-chip').forEach(btn => {
    btn.addEventListener('click', () => {
      const q = btn.getAttribute('data-question')
      if (q) {
        state.currentQuestion = q
        submitQuestion(q)
      }
    })
  })

  // Refresh Health
  const btnRefreshHealth = document.querySelector<HTMLButtonElement>('#btn-refresh-health')
  if (btnRefreshHealth) {
    btnRefreshHealth.addEventListener('click', async () => {
      btnRefreshHealth.textContent = 'Checking...'
      state.health = await fetchHealth()
      render()
    })
  }

  // Refresh Schema
  const btnRefreshSchema = document.querySelector<HTMLButtonElement>('#btn-refresh-schema')
  if (btnRefreshSchema) {
    btnRefreshSchema.addEventListener('click', async () => {
      btnRefreshSchema.textContent = 'Refreshing...'
      state.schema = await fetchSchema(true)
      render()
    })
  }

  // Schema filter input
  const searchInput = document.querySelector<HTMLInputElement>('#schema-search-input')
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      state.schemaFilter = (e.target as HTMLInputElement).value
      render()
      // Preserve focus
      const updatedInput = document.querySelector<HTMLInputElement>('#schema-search-input')
      if (updatedInput) {
        updatedInput.focus()
        updatedInput.setSelectionRange(state.schemaFilter.length, state.schemaFilter.length)
      }
    })
  }

  // Collapsible table headers
  document.querySelectorAll<HTMLDivElement>('.schema-table-header').forEach(header => {
    header.addEventListener('click', () => {
      const tblName = header.getAttribute('data-table')
      if (tblName) {
        state.expandedTables[tblName] = !state.expandedTables[tblName]
        render()
      }
    })
  })

  // Evidence toggles
  document.querySelectorAll<HTMLButtonElement>('.evidence-toggle').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-target') as keyof typeof state.evidenceOpen
      if (target && target in state.evidenceOpen) {
        state.evidenceOpen[target] = !state.evidenceOpen[target]
        render()
      }
    })
  })

  // View tabs (Table / Chart)
  const tabTable = document.querySelector<HTMLButtonElement>('#tab-table')
  const tabChart = document.querySelector<HTMLButtonElement>('#tab-chart')
  if (tabTable) {
    tabTable.addEventListener('click', () => {
      state.activeTab = 'table'
      render()
    })
  }
  if (tabChart) {
    tabChart.addEventListener('click', () => {
      state.activeTab = 'chart'
      render()
    })
  }

  // Copy SQL button
  const copyBtn = document.querySelector<HTMLButtonElement>('#btn-copy-sql')
  if (copyBtn) {
    copyBtn.addEventListener('click', () => {
      const sql = state.currentAnswer?.evidence?.executed_sql || state.currentAnswer?.evidence?.proposed_sql || ''
      navigator.clipboard.writeText(sql).then(() => {
        copyBtn.textContent = '✓ Copied!'
        setTimeout(() => {
          if (copyBtn) copyBtn.textContent = '📋 Copy'
        }, 2000)
      })
    })
  }

  // Export CSV button
  const exportBtn = document.querySelector<HTMLButtonElement>('#btn-export-csv')
  if (exportBtn && state.currentAnswer?.data && state.currentAnswer.data.length > 0) {
    exportBtn.addEventListener('click', () => {
      const data = state.currentAnswer!.data!
      const columns = state.currentAnswer!.columns || Object.keys(data[0] || {})
      const csvRows = [
        columns.join(','),
        ...data.map(row => columns.map(col => {
          const val = row[col]
          if (val === null || val === undefined) return ''
          const str = String(val).replace(/"/g, '""')
          return `"${str}"`
        }).join(','))
      ]
      const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' })
      const link = document.createElement('a')
      link.href = URL.createObjectURL(blob)
      link.download = `datamind_query_result_${Date.now()}.csv`
      link.click()
    })
  }
}

// ─── Question Submission Workflow ───

async function submitQuestion(question: string): Promise<void> {
  state.isLoading = true
  state.loadingStep = 0
  render()

  // Progressive simulated pipeline step indicators for smooth UX
  if (state.loadingInterval) clearInterval(state.loadingInterval)
  state.loadingInterval = window.setInterval(() => {
    if (state.loadingStep < 3) {
      state.loadingStep++
      render()
    }
  }, 900)

  try {
    const answer = await askQuestion(question)
    state.currentAnswer = answer
  } catch (err: any) {
    state.currentAnswer = {
      question,
      status: 'error',
      answer: 'Failed to process question through DataMind.',
      error: err.message || 'Unknown network or execution error.',
      error_type: 'Execution Failure',
    }
  } finally {
    if (state.loadingInterval) {
      clearInterval(state.loadingInterval)
      state.loadingInterval = null
    }
    state.isLoading = false
    render()
  }
}

// ─── Application Bootstrap ───

async function init(): Promise<void> {
  render()

  // Parallel initial data fetching
  const [health, schema, examples] = await Promise.all([
    fetchHealth(),
    fetchSchema(),
    fetchExamples(),
  ])

  state.health = health
  state.schema = schema
  state.examples = examples

  // Expand first table by default if schema present
  if (schema.schema_info?.tables && schema.schema_info.tables.length > 0) {
    state.expandedTables[schema.schema_info.tables[0].table_name] = true
  }

  render()
}

init()
