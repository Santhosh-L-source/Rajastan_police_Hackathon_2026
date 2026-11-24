import React, { useState, useEffect, useRef, useCallback } from 'react'
import CytoscapeComponent from 'react-cytoscapejs'
import dagre from 'cytoscape-dagre'
import Cytoscape from 'cytoscape'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'

Cytoscape.use(dagre)

const API_BASE = 'http://localhost:8000'

/* ────── Types ────── */

interface Case {
  id: number
  case_id: string
  title: string
  description: string
  analyzed_at: string | null
}

interface Suspect {
  account: string
  suspicion_score: number
  risk_level: string
  explanation: string
  estimated_recovery?: number
  total_inflow?: number
  total_outflow?: number
  fan_in?: number
  fan_out?: number
  pass_through_ratio?: number
  hop?: number
  net_balance?: number
}

/* ────── Helpers ────── */

const isExit = (id: string) =>
  id.startsWith('ATM') || id.startsWith('CRYPTO') || id.startsWith('EXTERNAL')
const isVictim = (id: string) => id.startsWith('VICTIM')

const hopLabel = (hop: number | undefined) => {
  if (hop === undefined || hop < 0) return ''
  if (hop === 0) return 'Victim'
  if (hop >= 4) return 'Exit'
  return `Hop ${hop}`
}

const fmtRs = (n: number) => {
  if (n >= 100000) return `₹${(n / 100000).toFixed(2)} L`
  if (n >= 1000) return `₹${(n / 1000).toFixed(1)} K`
  return `₹${n.toFixed(0)}`
}

const fmtLakh = (v: number) => `₹${(v / 100000).toFixed(2)} L`

const shortLabel = (id: string) =>
  id.length > 18 ? id.substring(0, 16) + '…' : id

const bankFromAccount = (a: string): string => {
  const u = a.toUpperCase()
  if (u.includes('ICICI')) return 'ICICI Bank'
  if (u.includes('HDFC')) return 'HDFC Bank'
  if (u.includes('MULE_L1')) return 'Paytm PB'
  if (u.startsWith('VICTIM')) return 'SBI'
  if (u.startsWith('ATM')) return 'ATM'
  if (u.startsWith('CRYPTO')) return 'Crypto'
  return 'Unknown'
}

/* ────── App ────── */

function App() {
  const [activeTab, setActiveTab] = useState('graph')
  const [cases, setCases] = useState<Case[]>([])
  const [selectedCase, setSelectedCase] = useState<Case | null>(null)
  const [suspects, setSuspects] = useState<Suspect[]>([])
  const [freezeRankings, setFreezeRankings] = useState<any[]>([])
  const [recoveryCurve, setRecoveryCurve] = useState<any[]>([])
  const [graphData, setGraphData] = useState<any>(null)
  const [selectedNode, setSelectedNode] = useState<Suspect | null>(null)
  const [selectedAccounts, setSelectedAccounts] = useState<Set<string>>(new Set())
  const [infraClusters, setInfraClusters] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [graphEdges, setGraphEdges] = useState<any[]>([])

  // AI Assistant state
  const [aiQuery, setAiQuery] = useState('')
  const [aiMessages, setAiMessages] = useState<{ role: string; text: string }[]>([])
  const [aiLoading, setAiLoading] = useState(false)

  const cyRef = useRef<any>(null)

  useEffect(() => { loadCases() }, [])

  const loadCases = async () => {
    try {
      const res = await fetch(`${API_BASE}/cases`)
      const data = await res.json()
      setCases(data)
      const c = data.find((c: Case) => c.case_id === 'case_001')
      if (c?.analyzed_at) setTimeout(() => selectCase(c), 500)
      else if (data.length > 0 && data[0].analyzed_at) setTimeout(() => selectCase(data[0]), 500)
    } catch (err) { console.error('Failed to load cases:', err) }
  }

  const selectCase = async (c: Case) => {
    setSelectedCase(c); setActiveTab('graph'); setSelectedNode(null)
    if (c.analyzed_at) await loadCaseData(c.case_id)
  }

  const loadCaseData = async (caseId: string) => {
    setLoading(true)
    try {
      const [suspectsRes, freezeRes, graphRes, infraRes] = await Promise.all([
        fetch(`${API_BASE}/cases/${caseId}/suspects`),
        fetch(`${API_BASE}/cases/${caseId}/freeze-priority`),
        fetch(`${API_BASE}/cases/${caseId}/graph`),
        fetch(`${API_BASE}/cases/${caseId}/infra/clusters`).catch(() => ({ ok: false } as any)),
      ])

      const suspectsData = await suspectsRes.json()
      const freezeData = await freezeRes.json()
      const graphJson = await graphRes.json()

      setSuspects(suspectsData.suspects)
      setFreezeRankings(freezeData.rankings)
      setGraphEdges(graphJson.edges)

      const curveData = freezeData.recovery_curve.map((pt: number[]) => ({
        accounts: pt[0],
        recovery: Math.round(pt[1]),
      }))
      setRecoveryCurve(curveData)

      // Pre-select top 5 accounts
      const top5 = new Set<string>(freezeData.rankings.slice(0, 5).map((r: any) => r.account))
      setSelectedAccounts(top5)

      if (infraRes.ok) {
        const infraData = await (infraRes as Response).json()
        setInfraClusters(infraData.clusters || [])
      }

      /* ── Build Cytoscape elements ── */
      const suspectMap = new Map(suspectsData.suspects.map((s: Suspect) => [s.account, s]))

      const elements = {
        nodes: graphJson.nodes.map((n: any) => {
          const suspect = suspectMap.get(n.id) as Suspect | undefined
          const risk = suspect?.risk_level || 'LOW'
          const hop = suspect?.hop

          // Colour
          let color = '#6b7280' // grey / LOW
          if (isVictim(n.id)) color = '#2563eb' // blue
          else if (isExit(n.id)) color = '#6b7280'
          else if (risk === 'HIGH') color = '#dc2626'
          else if (risk === 'MEDIUM') color = '#ea580c'

          // Size – victim larger
          const size = isVictim(n.id) ? 140 : isExit(n.id) ? 95 : 105

          // Shape – exit nodes are square
          const shape = isExit(n.id) ? 'rectangle' : 'ellipse'

          return {
            data: {
              id: n.id,
              label: shortLabel(n.id),
              suspicion_score: suspect?.suspicion_score ?? 0,
              risk_level: risk,
              color,
              size,
              shape,
              hop: hop ?? -1,
              ...suspect,
            },
          }
        }),
        edges: graphJson.edges.map((e: any) => ({
          data: {
            source: e.source,
            target: e.target,
            amount: e.amount,
            label: '', // shown on selection/hover
          },
        })),
      }

      setGraphData(elements)
    } catch (err) { console.error('Failed to load case data:', err) }
    finally { setLoading(false) }
  }

  const handleNodeClick = (nodeId: string) => {
    const suspect = suspects.find(s => s.account === nodeId)
    setSelectedNode(suspect || null)

    // Show amounts on connected edges and refit after panel opens
    if (cyRef.current) {
      const cy = cyRef.current
      cy.edges().style({ label: '' })
      const node = cy.getElementById(nodeId)
      node.connectedEdges().style({
        label: (ele: any) => fmtRs(ele.data('amount')),
        'font-size': 16,
        'font-weight': 'bold',
        'text-background-color': '#ffffff',
        'text-background-opacity': 0.95,
        'text-background-padding': '4px',
        color: '#0f172a',
      })
      setTimeout(() => {
        cy.resize()
        cy.fit(35)
        addHopLabels(cy)
      }, 150)
    }
  }

  const toggleAccountSelection = (account: string) => {
    const n = new Set(selectedAccounts)
    if (n.has(account)) n.delete(account); else n.add(account)
    setSelectedAccounts(n)
  }

  const calculateSelectedRecovery = () =>
    freezeRankings.filter(r => selectedAccounts.has(r.account))
      .reduce((sum, r) => sum + (r.estimated_recovery || 0), 0)

  /* ── AI Assistant ── */
  const submitAiQuery = async (query: string) => {
    if (!query.trim() || !selectedCase) return
    setAiMessages(prev => [...prev, { role: 'user', text: query }])
    setAiQuery('')
    setAiLoading(true)
    try {
      const res = await fetch(`${API_BASE}/cases/${selectedCase.case_id}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      })
      const data = await res.json()
      setAiMessages(prev => [...prev, { role: 'assistant', text: data.answer }])
    } catch {
      setAiMessages(prev => [...prev, { role: 'assistant', text: 'Error contacting the analysis engine.' }])
    } finally { setAiLoading(false) }
  }

  /* ── Cytoscape stylesheet ── */
  const cytoscapeStylesheet: any[] = [
    {
      selector: 'node',
      style: {
        'background-color': 'data(color)',
        label: 'data(label)',
        width: 'data(size)',
        height: 'data(size)',
        shape: 'data(shape)',
        'font-size': 22,
        'font-weight': 'bold',
        'font-family': 'system-ui, sans-serif',
        'text-valign': 'bottom',
        'text-halign': 'center',
        'text-margin-y': 10,
        color: '#0f172a',
        'text-background-color': '#ffffff',
        'text-background-opacity': 0.92,
        'text-background-padding': '5px',
        'text-background-shape': 'roundrectangle',
        'border-width': 3,
        'border-color': '#171717',
      },
    },
    {
      selector: 'node:selected',
      style: {
        'border-width': 5,
        'border-color': '#2563eb',
        'text-background-color': '#dbeafe',
      },
    },
    {
      selector: 'edge',
      style: {
        width: 2.5,
        'line-color': '#64748b',
        'target-arrow-color': '#64748b',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'arrow-scale': 1.2,
      },
    },
  ]

  const cytoscapeLayout = {
    name: 'dagre',
    rankDir: 'LR',
    nodeSep: 55,
    rankSep: 400,
    animate: false,
    fit: true,
    padding: 35,
  }

  /* ── Hop header labels (positioned after layout) ── */
  const addHopLabels = useCallback((cy: any) => {
    // Remove existing overlays
    cy.container()?.querySelectorAll('.hop-label')?.forEach((el: any) => el.remove())

    const hopGroups: { [hop: number]: { x: number; label: string } } = {}
    cy.nodes().forEach((n: any) => {
      const hop = n.data('hop')
      if (hop < 0) return
      const pos = n.renderedPosition()
      const label = hop === 0 ? 'Victim' : hop >= 4 ? 'Exit' : `Hop ${hop}`
      if (!hopGroups[hop]) hopGroups[hop] = { x: pos.x, label }
      else hopGroups[hop].x = (hopGroups[hop].x + pos.x) / 2
    })

    Object.values(hopGroups).forEach(({ x, label }) => {
      const el = document.createElement('div')
      el.className = 'hop-label'
      el.style.cssText = `position:absolute;top:12px;left:${x}px;transform:translateX(-50%);
        font-size:12px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:0.08em;
        pointer-events:none;font-family:system-ui,sans-serif;white-space:nowrap;`
      el.textContent = label
      cy.container()?.appendChild(el)
    })
  }, [])

  /* ── Render ── */

  const TABS = [
    { id: 'graph', label: 'Money Trail Graph' },
    { id: 'freeze', label: 'Freeze Priority' },
    { id: 'infra', label: 'Infrastructure' },
    { id: 'ai', label: 'AI Assistant' },
  ]

  return (
    <div className="min-h-screen bg-neutral-100">
      {/* Header */}
      <header className="bg-neutral-900 border-b-2 border-red-700 px-6 py-4">
        <div className="flex items-baseline justify-between">
          <div className="flex items-baseline gap-4">
            <h1 className="text-2xl font-bold text-white tracking-tight">FINTRACE</h1>
            <span className="text-sm text-neutral-400 uppercase tracking-wide">Financial Intelligence System</span>
          </div>
          {selectedCase && (
            <div className="text-right">
              <div className="font-mono text-sm text-neutral-100">{selectedCase.case_id}</div>
              <div className="text-xs text-neutral-400">{selectedCase.title}</div>
            </div>
          )}
        </div>
      </header>

      {/* Tabs */}
      <div className="bg-white border-b border-neutral-300">
        <div className="flex gap-1 px-6">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-3 text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-neutral-900 text-white'
                  : 'text-neutral-600 hover:text-neutral-900 hover:bg-neutral-50'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <main className="p-6">

        {/* ═══════════════════════════════════════════════════════════
            TAB 1 – MONEY TRAIL GRAPH
           ═══════════════════════════════════════════════════════════ */}
        {activeTab === 'graph' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-neutral-900">Transaction Network</h2>
              <div className="flex gap-4 text-xs font-mono">
                <div className="flex items-center gap-2">
                  <div className="w-4 h-4 rounded-full bg-blue-600 border-2 border-neutral-900" />
                  <span>VICTIM</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-red-600 border border-neutral-900 rounded-full" />
                  <span>HIGH ≥75</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-orange-600 border border-neutral-900 rounded-full" />
                  <span>MEDIUM</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-neutral-500 border border-neutral-900 rounded-full" />
                  <span>LOW</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-neutral-500 border border-neutral-900" /> {/* square */}
                  <span>EXIT (ATM/crypto)</span>
                </div>
              </div>
            </div>

            <div className="flex gap-4">
              <div
                className={`bg-white border border-neutral-300 relative ${selectedNode ? 'w-2/3' : 'w-full'}`}
                style={{ height: '700px' }}
              >
                {loading && (
                  <div className="flex items-center justify-center h-full text-neutral-500">
                    Loading graph data…
                  </div>
                )}
                {!loading && graphData && (
                  <CytoscapeComponent
                    elements={CytoscapeComponent.normalizeElements(graphData)}
                    stylesheet={cytoscapeStylesheet}
                    layout={cytoscapeLayout}
                    style={{ width: '100%', height: '100%' }}
                    cy={(cy) => {
                      cyRef.current = cy
                      cy.on('tap', 'node', (evt) => handleNodeClick(evt.target.id()))
                      setTimeout(() => { cy.fit(60); addHopLabels(cy) }, 200)
                    }}
                  />
                )}
                {!loading && !graphData && (
                  <div className="flex items-center justify-center h-full text-neutral-500">
                    Loading case data…
                  </div>
                )}
              </div>

              {selectedNode && (
                <div className="w-1/3 bg-white border border-neutral-300 p-5 overflow-y-auto" style={{ height: '700px' }}>
                  <div className="mb-5">
                    <div className="text-xs font-mono text-neutral-500 uppercase tracking-wide mb-1">Selected Account</div>
                    <div className="font-mono text-sm font-bold text-neutral-900 break-all">{selectedNode.account}</div>
                  </div>

                  <div className="space-y-4 text-sm">
                    <div>
                      <div className="text-xs font-mono text-neutral-500 uppercase">Risk Level</div>
                      <div className={`inline-block px-2 py-1 mt-1 text-xs font-mono font-bold ${
                        selectedNode.risk_level === 'HIGH' ? 'bg-red-100 text-red-800 border border-red-300' :
                        selectedNode.risk_level === 'MEDIUM' ? 'bg-orange-100 text-orange-800 border border-orange-300' :
                        'bg-neutral-100 text-neutral-800 border border-neutral-300'
                      }`}>
                        {selectedNode.risk_level}
                      </div>
                    </div>

                    <div>
                      <div className="text-xs font-mono text-neutral-500 uppercase">Suspicion Score</div>
                      <div className="font-mono text-2xl font-bold text-neutral-900">{selectedNode.suspicion_score.toFixed(1)}</div>
                    </div>

                    {selectedNode.hop !== undefined && selectedNode.hop >= 0 && (
                      <div>
                        <div className="text-xs font-mono text-neutral-500 uppercase">Hop from Victim</div>
                        <div className="font-mono font-bold text-neutral-900">{hopLabel(selectedNode.hop)}</div>
                      </div>
                    )}

                    {selectedNode.total_inflow !== undefined && (
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <div className="text-xs font-mono text-neutral-500 uppercase">Total Inflow</div>
                          <div className="font-mono font-bold text-neutral-900">{fmtRs(selectedNode.total_inflow!)}</div>
                        </div>
                        <div>
                          <div className="text-xs font-mono text-neutral-500 uppercase">Total Outflow</div>
                          <div className="font-mono font-bold text-neutral-900">{fmtRs(selectedNode.total_outflow ?? 0)}</div>
                        </div>
                      </div>
                    )}

                    {selectedNode.net_balance !== undefined && (
                      <div>
                        <div className="text-xs font-mono text-neutral-500 uppercase">Remaining Balance</div>
                        <div className="font-mono font-bold text-neutral-900">{fmtRs(Math.max(selectedNode.net_balance, 0))}</div>
                      </div>
                    )}

                    {selectedNode.explanation && (
                      <div className="pt-2 border-t border-neutral-200">
                        <div className="text-xs font-mono text-neutral-500 uppercase mb-1">Why Flagged</div>
                        <div className="text-sm text-neutral-700 leading-relaxed">{selectedNode.explanation}</div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ═══════════════════════════════════════════════════════════
            TAB 2 – FREEZE PRIORITY
           ═══════════════════════════════════════════════════════════ */}
        {activeTab === 'freeze' && (
          <div>
            <h2 className="text-xl font-bold text-neutral-900 mb-4">Freeze Priority Rankings</h2>

            {/* Recovery total */}
            <div className="bg-white border border-neutral-300 p-3 mb-3 flex items-center justify-between">
              <div>
                <div className="text-xs font-mono text-neutral-500 uppercase tracking-wide mb-0.5">Selected Recovery Total</div>
                <div className="text-2xl font-mono font-bold text-neutral-900">
                  {fmtRs(calculateSelectedRecovery())}
                </div>
              </div>
              <div className="text-right text-xs text-neutral-500 font-mono">
                Victim loss: ₹5,00,000 · Accounts selected: {selectedAccounts.size}
              </div>
            </div>

            {/* Table – top 10 only */}
            <div className="bg-white border border-neutral-300 mb-3">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-neutral-900 text-white font-mono text-xs uppercase">
                    <th className="px-3 py-2 text-center w-10">Select</th>
                    <th className="px-3 py-2 text-left w-10">Rank</th>
                    <th className="px-3 py-2 text-left">Account</th>
                    <th className="px-3 py-2 text-left">Bank</th>
                    <th className="px-3 py-2 text-right">Score</th>
                    <th className="px-3 py-2 text-right">Remaining Amt</th>
                    <th className="px-3 py-2 text-right">Est. Recovery</th>
                  </tr>
                </thead>
                <tbody className="font-mono text-xs">
                  {freezeRankings.slice(0, 10).map((rank, idx) => (
                    <tr key={idx} className={`border-b border-neutral-200 hover:bg-neutral-50 ${selectedAccounts.has(rank.account) ? 'bg-blue-50' : ''}`}>
                      <td className="px-3 py-1.5 text-center">
                        <input
                          type="checkbox"
                          checked={selectedAccounts.has(rank.account)}
                          onChange={() => toggleAccountSelection(rank.account)}
                          className="w-4 h-4"
                        />
                      </td>
                      <td className="px-3 py-1.5 text-neutral-500">{idx + 1}</td>
                      <td className="px-3 py-1.5 font-bold">{rank.account}</td>
                      <td className="px-3 py-1.5 text-neutral-600">{rank.bank || bankFromAccount(rank.account)}</td>
                      <td className="px-3 py-1.5 text-right font-bold">{rank.freeze_priority_score.toFixed(1)}</td>
                      <td className="px-3 py-1.5 text-right">{fmtRs(rank.remaining_balance ?? 0)}</td>
                      <td className="px-3 py-1.5 text-right font-bold">{fmtRs(rank.estimated_recovery || 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Cash-out points note */}
            <div className="bg-neutral-50 border border-neutral-300 p-2.5 mb-3 text-xs font-mono text-neutral-600">
              <span className="font-bold uppercase">Cash-out exit points (excluded):</span>{' '}
              ATM_WITHDRAWAL, CRYPTO_EXCHANGE, ATM_WITHDRAWAL_2 — funds already exited the banking system.
            </div>

            {/* Recovery curve */}
            {recoveryCurve.length > 0 && (
              <div>
                <h3 className="text-base font-bold text-neutral-900 mb-2">Recovery Curve</h3>
                <div className="bg-white border border-neutral-300 p-3" style={{ height: '260px' }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={recoveryCurve} margin={{ top: 8, right: 20, bottom: 22, left: 15 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#d1d5db" />
                      <XAxis
                        dataKey="accounts"
                        stroke="#171717"
                        style={{ fontSize: 11, fontFamily: 'monospace' }}
                        label={{ value: 'Accounts frozen (by priority)', position: 'insideBottom', offset: -12, style: { fontSize: 12, fontFamily: 'system-ui, sans-serif', fontWeight: 600 } }}
                      />
                      <YAxis
                        stroke="#171717"
                        style={{ fontSize: 11, fontFamily: 'monospace' }}
                        tickFormatter={(v: number) => `₹${(v / 100000).toFixed(1)}L`}
                        label={{ value: 'Estimated recovery (Rs)', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle', fontSize: 12, fontFamily: 'system-ui, sans-serif', fontWeight: 600 } }}
                      />
                      <Tooltip
                        contentStyle={{ backgroundColor: '#fff', border: '1px solid #171717', fontFamily: 'monospace', fontSize: 11 }}
                        formatter={(v: number) => [fmtLakh(v), 'Recovery']}
                      />
                      <Line type="monotone" dataKey="recovery" stroke="#171717" strokeWidth={2} dot={{ r: 3 }} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ═══════════════════════════════════════════════════════════
            TAB 3 – INFRASTRUCTURE
           ═══════════════════════════════════════════════════════════ */}
        {activeTab === 'infra' && (
          <div>
            <h2 className="text-xl font-bold text-neutral-900 mb-4">Infrastructure Clusters</h2>

            {infraClusters.length === 0 && (
              <div className="bg-white border border-neutral-300 p-8 text-center text-neutral-500">
                No infrastructure data available
              </div>
            )}

            {infraClusters.length > 0 && (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                {infraClusters.map((cluster, idx) => (
                  <div key={idx} className="bg-white border border-neutral-300 p-5">
                    {/* Title row */}
                    <div className="flex items-start justify-between mb-4">
                      <div className="font-mono font-bold text-lg text-neutral-900">{cluster.cluster_id}</div>
                      <div className="text-xs font-mono px-2 py-1 bg-red-100 text-red-800 border border-red-300">
                        Score {cluster.score.toFixed(0)} · {cluster.size} domains
                      </div>
                    </div>

                    {/* Metadata grid */}
                    <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs mb-4">
                      <div>
                        <span className="font-mono text-neutral-500 uppercase">Shared IP</span>
                        <div className="font-mono font-bold text-neutral-900">{cluster.shared_ip || '–'}</div>
                      </div>
                      <div>
                        <span className="font-mono text-neutral-500 uppercase">Name Server</span>
                        <div className="font-mono font-bold text-neutral-900">{cluster.name_server || '–'}</div>
                      </div>
                      <div>
                        <span className="font-mono text-neutral-500 uppercase">Registrar</span>
                        <div className="font-mono font-bold text-neutral-900">{cluster.registrar || '–'}</div>
                      </div>
                      <div>
                        <span className="font-mono text-neutral-500 uppercase">Creation Window</span>
                        <div className="font-mono font-bold text-neutral-900">{cluster.creation_window || '–'}</div>
                      </div>
                      <div>
                        <span className="font-mono text-neutral-500 uppercase">Hosting ASN</span>
                        <div className="font-mono font-bold text-neutral-900">{cluster.asn || '–'}</div>
                      </div>
                      <div>
                        <span className="font-mono text-neutral-500 uppercase">Linked UPI</span>
                        <div className="font-mono font-bold text-red-700">
                          {cluster.linked_upis?.length > 0 ? cluster.linked_upis.join(', ') : '–'}
                        </div>
                      </div>
                    </div>

                    {/* Typosquat matches */}
                    {cluster.typosquats?.length > 0 && (
                      <div className="text-xs mb-3">
                        <span className="font-mono text-neutral-500 uppercase">Typosquat Matches</span>
                        <div className="mt-1 space-y-1">
                          {cluster.typosquats.slice(0, 3).map((t: any, ti: number) => (
                            <div key={ti} className="font-mono text-neutral-800">
                              {t.a} ≈ {t.b} <span className="text-neutral-400">({(t.sim * 100).toFixed(0)}%)</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Domain list */}
                    <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-neutral-200">
                      {cluster.domains.map((domain: any, dIdx: number) => (
                        <span
                          key={dIdx}
                          className="inline-block px-3 py-1 text-xs font-mono bg-red-50 text-red-900 border border-red-200"
                        >
                          {domain.domain}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ═══════════════════════════════════════════════════════════
            TAB 4 – AI ASSISTANT
           ═══════════════════════════════════════════════════════════ */}
        {activeTab === 'ai' && (
          <div>
            <h2 className="text-xl font-bold text-neutral-900 mb-4">AI Assistant</h2>

            {/* Chat area */}
            <div className="bg-white border border-neutral-300 p-5 mb-4" style={{ minHeight: '400px', maxHeight: '500px', overflowY: 'auto' }}>
              {aiMessages.length === 0 && (
                <div className="text-neutral-400 text-sm text-center py-20">Ask a question about this case to get started.</div>
              )}
              {aiMessages.map((msg, i) => (
                <div key={i} className={`mb-4 ${msg.role === 'user' ? 'text-right' : ''}`}>
                  <div
                    className={`inline-block max-w-[80%] px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap ${
                      msg.role === 'user'
                        ? 'bg-neutral-900 text-white'
                        : 'bg-neutral-100 text-neutral-900 border border-neutral-300'
                    }`}
                  >
                    {msg.text.split(/(\*\*.*?\*\*)/g).map((part, pi) =>
                      part.startsWith('**') && part.endsWith('**')
                        ? <strong key={pi}>{part.slice(2, -2)}</strong>
                        : <span key={pi}>{part}</span>
                    )}
                  </div>
                </div>
              ))}
              {aiLoading && (
                <div className="text-sm text-neutral-500 animate-pulse">Analyzing…</div>
              )}
            </div>

            {/* Example chips */}
            <div className="flex flex-wrap gap-2 mb-3">
              {[
                'Which accounts received money from the scam victim within 1 hour?',
                'Show the path between the victim and ATM_WITHDRAWAL',
              ].map((chip, ci) => (
                <button
                  key={ci}
                  onClick={() => submitAiQuery(chip)}
                  className="px-3 py-2 text-xs font-mono bg-neutral-50 border border-neutral-300 text-neutral-700 hover:bg-neutral-100 transition-colors"
                >
                  {chip}
                </button>
              ))}
            </div>

            {/* Input */}
            <div className="flex gap-2">
              <input
                type="text"
                value={aiQuery}
                onChange={(e) => setAiQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') submitAiQuery(aiQuery) }}
                placeholder="Ask about the case…"
                className="flex-1 px-4 py-3 border border-neutral-300 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-neutral-900"
              />
              <button
                onClick={() => submitAiQuery(aiQuery)}
                disabled={aiLoading}
                className="px-6 py-3 bg-neutral-900 text-white text-sm font-bold hover:bg-neutral-700 disabled:opacity-50 transition-colors"
              >
                Ask
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

export default App
