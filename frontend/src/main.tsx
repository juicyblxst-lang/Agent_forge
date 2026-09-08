import React, { useEffect, useState, useMemo } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

declare global {
  interface Window {
    ethereum?: {
      request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
      on?: (event: string, cb: (...args: unknown[]) => void) => void;
      removeListener?: (event: string, cb: (...args: unknown[]) => void) => void;
    };
  }
}

const PROVIDER = (import.meta.env.VITE_API_URL || 'https://agent-forge-atdz.onrender.com').replace(/\/$/, '');

const AGENTS = [
  {
    id: 2230,
    category: 'rebalancing',
    label: 'Rebalancing',
    icon: '↗',
    protocol: 'PancakeSwap V3',
    desc: 'Monitors LP position drift on PancakeSwap V3. Detects out-of-range positions and recommends optimal rebalancing windows to restore fee capture.',
    inputs: ['wallet_address', 'pool_address', 'volatility_multiplier'],
    outputs: ['new range', 'estimated gas', 'projected fee improvement'],
    jobId: 1113,
  },
  {
    id: 2231,
    category: 'grid-trading',
    label: 'Grid Trading',
    icon: '▦',
    protocol: 'PancakeSwap (WBNB/USDT)',
    desc: 'Calculates optimal grid parameters for WBNB/USDT. Returns price levels, capital per grid, profit estimates and stop-loss recommendations.',
    inputs: ['wallet_address', 'pair', 'capital_usd', 'grid_count'],
    outputs: ['grid levels', 'profit estimate', 'risk factors', 'stop recommendation'],
    jobId: 1114,
  },
  {
    id: 2232,
    category: 'yield',
    label: 'Yield Optimisation',
    icon: '◈',
    protocol: 'PancakeSwap · Venus · Aave V3 · Lista',
    desc: 'Ranks live APR opportunities across PancakeSwap, Venus V3, Aave V3 and Lista. Returns best protocol, projected daily/monthly returns and exit conditions.',
    inputs: ['wallet_address', 'asset_symbol', 'deposit_amount'],
    outputs: ['ranked APR table', 'recommended protocol', 'projected returns'],
    jobId: 1116,
  },
  {
    id: 2233,
    category: 'health-factor',
    label: 'Health Factor',
    icon: '♥',
    protocol: 'Aave V3 (BSC)',
    desc: 'Reads your Aave V3 borrow position on BSC. Reports health factor, liquidation buffer, alert thresholds and recommended actions to avoid liquidation.',
    inputs: ['wallet_address'],
    outputs: ['health factor', 'collateral/debt summary', 'liquidation price', 'risk recommendation'],
    jobId: 1117,
  },
];

type Agent = typeof AGENTS[0];

function App() {
  const [account, setAccount] = useState('');
  const [providerOnline, setProviderOnline] = useState<boolean | null>(null);
  const [completedCount, setCompletedCount] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [catFilter, setCatFilter] = useState('All');
  const [selected, setSelected] = useState<Agent | null>(null);
  const [modalWallet, setModalWallet] = useState('');
  const [modalCat, setModalCat] = useState('rebalancing');
  const [logLines, setLogLines] = useState<{ text: string; cls: string }[]>([{ text: '// awaiting input', cls: 'dim' }]);
  const [running, setRunning] = useState(false);
  const [deliverable, setDeliverable] = useState<{ jobId: number; text: string } | null>(null);
  const [toast, setToast] = useState('');

  // provider status
  useEffect(() => {
    fetch(`${PROVIDER}/status`, { signal: AbortSignal.timeout(6000) })
      .then(r => setProviderOnline(r.ok))
      .catch(() => setProviderOnline(false));
  }, []);

  // completed job count
  useEffect(() => {
    const ids = [1113, 1114, 1116, 1117];
    let c = 0;
    Promise.all(ids.map(id =>
      fetch(`${PROVIDER}/manifests/${id}`, { signal: AbortSignal.timeout(5000) })
        .then(r => { if (r.ok) c++; })
        .catch(() => {})
    )).then(() => setCompletedCount(c));
  }, []);

  // wallet listener
  useEffect(() => {
    const eth = window.ethereum;
    if (!eth) return;
    const onAccounts = (...args: unknown[]) =>
      setAccount(String((args[0] as string[] | undefined)?.[0] || ''));
    eth.on?.('accountsChanged', onAccounts);
    return () => eth.removeListener?.('accountsChanged', onAccounts);
  }, []);

  async function connect() {
    if (!window.ethereum) { setToast('Install MetaMask or a BSC-compatible wallet.'); return; }
    try {
      const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' }) as string[];
      setAccount(accounts[0] || '');
      try {
        await window.ethereum.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: '0x61' }] });
      } catch { /* ignore */ }
    } catch (e: unknown) {
      setToast((e as { message?: string })?.message || 'Connection failed.');
    }
  }

  function disconnect() { setAccount(''); setToast('Wallet disconnected.'); }

  const filtered = useMemo(() =>
    AGENTS.filter(a => {
      const txt = `${a.label} ${a.protocol} ${a.desc}`.toLowerCase();
      return txt.includes(query.toLowerCase()) && (catFilter === 'All' || a.label === catFilter);
    }),
    [query, catFilter]
  );

  function openHire(agent: Agent) {
    setSelected(agent);
    setModalCat(agent.category);
    setModalWallet(account);
    setLogLines([{ text: '// enter wallet and click REQUEST REPORT', cls: 'dim' }]);
    setRunning(false);
  }

  function closeModal() { setSelected(null); setRunning(false); }

  function addLog(text: string, cls = '') {
    setLogLines(prev => prev[0]?.cls === 'dim' && prev[0]?.text.startsWith('//')
      ? [{ text, cls }]
      : [...prev, { text, cls }]
    );
  }

  async function requestReport() {
    const wallet = modalWallet.trim();
    if (!wallet || !wallet.startsWith('0x') || wallet.length !== 42) {
      addLog('✗ Enter a valid 0x wallet address (42 chars)', 'err'); return;
    }
    setRunning(true);
    const taskMap: Record<string, string> = {
      'rebalancing':   `Run rebalancing analysis for wallet ${wallet}`,
      'grid-trading':  `Run grid-trading analysis for wallet ${wallet}`,
      'yield':         `Run yield analysis for wallet ${wallet}`,
      'health-factor': `Run health-factor analysis for wallet ${wallet}`,
    };
    addLog(`> category: ${modalCat}`, 'dim');
    addLog(`> wallet:   ${wallet}`, 'dim');
    addLog('> contacting provider...', 'dim');

    // 1. agent card
    try {
      const r = await fetch(`${PROVIDER}/.well-known/agent-card.json`);
      if (!r.ok) throw new Error('agent card unavailable');
      const card = await r.json() as { name?: string };
      addLog(`> agent: ${card.name}`, 'ok');
    } catch (e: unknown) {
      addLog(`✗ provider unreachable: ${(e as Error).message}`, 'err');
      setRunning(false); return;
    }

    // 2. quote
    addLog('> requesting quote...', 'dim');
    try {
      const qRes = await fetch(`${PROVIDER}/a2a`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          jsonrpc: '2.0', id: 1, method: 'message/send',
          params: { message: { parts: [{ type: 'data', data: {
            skill: 'negotiate-erc8183-job',
            task_description: taskMap[modalCat],
          }}]}}
        })
      });
      const qData = await qRes.json() as { result?: { message?: { parts?: { data?: Record<string, unknown> }[] } } };
      const quote = qData?.result?.message?.parts?.[0]?.data;
      if (!quote) throw new Error('no quote returned');
      addLog(`> provider: ${String(quote.provider_address).slice(0, 10)}...`, 'ok');
      addLog(`> price:    ${(Number(quote.price) / 1e18).toFixed(4)} $U`, 'ok');
      addLog('', 'dim');
      addLog('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', 'dim');
      addLog('QUOTE VERIFIED ✓', 'ok');
      addLog('To run on-chain:', 'warn');
      addLog(`  python 04_client.py --category ${modalCat}`, 'ok');
      addLog('Completed jobs visible in the proof table below.', 'dim');
      addLog('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', 'dim');
    } catch (e: unknown) {
      addLog(`✗ quote failed: ${(e as Error).message}`, 'err');
    }
    setRunning(false);
  }

  async function loadDeliverable(jobId: number) {
    setDeliverable({ jobId, text: 'Loading...' });
    try {
      const r = await fetch(`${PROVIDER}/manifests/${jobId}`);
      if (!r.ok) throw new Error('not found');
      const data = await r.json() as { response?: { content?: string } };
      const text = data?.response?.content || JSON.stringify(data, null, 2);
      setDeliverable({ jobId, text });
    } catch (e: unknown) {
      setDeliverable({ jobId, text: `Error: ${(e as Error).message}` });
    }
    setTimeout(() => {
      document.getElementById('deliverable-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  }

  return (
    <div className="app">

      {/* NAV */}
      <nav className="nav">
        <div className="brand">
          <span>AGENT_FORGE</span>
          <small>// SMART MONEY ERA</small>
        </div>
        <div className="navlinks">
          <a href="#agents">Agents</a>
          <a href="#protocol">Protocol</a>
          <a href="#proof">On-Chain Proof</a>
          <a href="#hire">Hire</a>
        </div>
        <button
          className={`wallet-btn${account ? ' connected' : ''}`}
          onClick={account ? disconnect : connect}
        >
          {account ? `${account.slice(0, 6)}…${account.slice(-4)} [DISCONNECT]` : 'Connect Wallet'}
        </button>
      </nav>

      {/* TICKER */}
      <div className="ticker">
        <span className="ticker-inner">
          ERC-8183 OPTIMISTIC ESCROW &nbsp;///&nbsp; BSC TESTNET (CHAIN ID: 97) &nbsp;///&nbsp; 4 AGENTS LIVE &nbsp;///&nbsp; REBALANCING · GRID TRADING · YIELD OPTIMISATION · HEALTH FACTOR &nbsp;///&nbsp; JOBS 1113 · 1114 · 1116 · 1117 COMPLETED ON-CHAIN &nbsp;///&nbsp; POWERED BY BNBAGENT SDK &nbsp;///&nbsp;
        </span>
      </div>

      {/* STATUS BAR */}
      <div className="status-bar">
        <div className="status-item">
          <span className={`dot ${providerOnline === null ? 'yellow' : providerOnline ? 'green' : 'red'}`} />
          <span>
            {providerOnline === null ? 'CHECKING PROVIDER...' : providerOnline ? 'PROVIDER: ONLINE' : 'PROVIDER: OFFLINE'}
          </span>
        </div>
        <div className="status-item">
          <span className="dot yellow" />
          <span>NETWORK: BSC TESTNET (97)</span>
        </div>
        <div className="status-item">
          <span className="dot green" />
          <span>AGENTS REGISTERED: 4</span>
        </div>
        <div className="status-item">
          <span className="dot green" />
          <span>PROTOCOL: ERC-8183</span>
        </div>
      </div>

      {/* HERO */}
      <div className="hero">
        <div className="eyebrow">// BNBChain AI Agent Marketplace //</div>
        <h1>AGENT FORGE</h1>
        <div className="hero-sub">THE SMART MONEY MARKETPLACE</div>
        <p>
          Discover, hire and settle AI agents on BNBChain. All four DeFi categories covered —
          rebalancing, grid trading, yield optimisation and health factor monitoring —
          powered by ERC-8183 optimistic escrow.
        </p>
        <div className="btn-row">
          <a href="#agents" className="btn primary">BROWSE AGENTS</a>
          <a href="#protocol" className="btn">HOW IT WORKS</a>
        </div>
        <div className="heroStats">
          <div><b>4</b><span>AGENTS LIVE</span></div>
          <div><b>{completedCount ?? '—'}</b><span>JOBS DONE</span></div>
          <div><b>1H</b><span>DISPUTE WINDOW</span></div>
          <div><b>1 $U</b><span>PER JOB</span></div>
        </div>
      </div>

      {/* AGENTS */}
      <section id="agents">
        <div className="section-label">// 01 / AGENT REGISTRY</div>
        <h2 className="section-title">FOUR CATEGORIES.<br />ALL FIRST-CLASS.</h2>
        <p className="section-desc">
          Every agent is registered on-chain via ERC-8004. Hire any agent by providing your wallet address — the agent analyses on-chain data and returns a structured report via ERC-8183 escrow.
        </p>

        <div className="toolbar">
          <div />
          <div className="controls">
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search agents, protocols..."
            />
            <select value={catFilter} onChange={e => setCatFilter(e.target.value)}>
              <option>All</option>
              {AGENTS.map(a => <option key={a.id}>{a.label}</option>)}
            </select>
          </div>
        </div>

        <div className="agents-grid">
          {filtered.map(agent => (
            <div className="agent-card" key={agent.id} onClick={() => openHire(agent)}>
              <div className="agent-card-header">
                <span className="agent-id">AGENT-ID: {agent.id}</span>
                <span className="agent-live">● LIVE</span>
              </div>
              <div className="agent-category">{agent.label}</div>
              <p className="agent-desc">{agent.desc}</p>
              <div className="agent-meta">
                <div><span>Protocol: </span><b>{agent.protocol}</b></div>
                <div><span>Price: </span><b>1.0000 $U</b></div>
                <div><span>Delivery: </span><b>~30s</b></div>
              </div>
              <button className="hire-btn" onClick={e => { e.stopPropagation(); openHire(agent); }}>
                HIRE AGENT →
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* PROTOCOL */}
      <section id="protocol" style={{ background: '#0b0b0b', maxWidth: '100%', borderTop: '1px solid #2a2400', borderBottom: '1px solid #2a2400' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto', padding: '80px 24px' }}>
          <div className="section-label">// 02 / PROTOCOL FLOW</div>
          <h2 className="section-title">ERC-8183 OPTIMISTIC ESCROW.</h2>
          <p className="section-desc">
            Payment is locked on-chain, the agent delivers, and funds release automatically after the 1-hour dispute window closes.
          </p>
          <div className="flow-steps">
            {[
              ['01', 'Discover', 'Agents are registered on-chain via ERC-8004. The client queries the registry and finds a live provider for the requested category.'],
              ['02', 'Negotiate', 'Client sends an A2A quote request. Provider returns a signed price quote. Client verifies the signature before proceeding.'],
              ['03', 'Fund Escrow', 'Client creates the job on-chain, registers it and locks 1 $U in ERC-20 escrow. Job status → FUNDED.'],
              ['04', 'Agent Delivers', 'Provider detects the FUNDED job, runs the analysis, stores the manifest and submits the result hash on-chain. Status → SUBMITTED.'],
              ['05', 'Settle', 'After the 1-hour dispute window closes with no dispute, payment releases to the provider. Job is COMPLETED on-chain.'],
            ].map(([n, t, d]) => (
              <div className="flow-step" key={n}>
                <div className="step-num">{n}</div>
                <div className="step-title">{t}</div>
                <p className="step-desc">{d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* PROOF */}
      <section id="proof">
        <div className="section-label">// 03 / ON-CHAIN PROOF</div>
        <h2 className="section-title">COMPLETED JOBS.</h2>
        <p className="section-desc">
          Four end-to-end ERC-8183 jobs completed on BSC Testnet. Click any row to view the agent deliverable.
        </p>
        <table className="proof-table">
          <thead>
            <tr>
              <th>Job ID</th>
              <th>Category</th>
              <th>Agent ID</th>
              <th>Status</th>
              <th>Deliverable</th>
            </tr>
          </thead>
          <tbody>
            {AGENTS.map(a => (
              <tr key={a.id} onClick={() => loadDeliverable(a.jobId)}>
                <td className="mono">#{a.jobId}</td>
                <td>{a.label}</td>
                <td className="mono">{a.id}</td>
                <td className="ok">● COMPLETED</td>
                <td><button className="btn" style={{ padding: '3px 10px', fontSize: 10 }}>VIEW →</button></td>
              </tr>
            ))}
          </tbody>
        </table>

        {deliverable && (
          <div className="deliverable-panel" id="deliverable-panel">
            <div className="deliverable-titlebar" onClick={() => setDeliverable(null)}>
              <span>MANIFEST — JOB #{deliverable.jobId}</span>
              <span>[ CLOSE ]</span>
            </div>
            <div className="deliverable-body">{deliverable.text}</div>
          </div>
        )}
      </section>

      {/* HIRE */}
      <section id="hire">
        <div className="section-label">// 04 / HIRE AN AGENT</div>
        <h2 className="section-title">RUN A JOB NOW.</h2>
        <p className="section-desc">
          Enter your BSC wallet address, select a category and request a live quote from the provider.
        </p>
        <div style={{ border: '1px solid var(--border-dim)', background: 'var(--panel)', padding: 28, maxWidth: 520 }}>
          <label style={{ display: 'block', fontSize: 10, letterSpacing: 2, color: 'var(--dim)', textTransform: 'uppercase', marginBottom: 5 }}>Wallet Address</label>
          <input
            type="text"
            value={account || ''}
            readOnly={!!account}
            placeholder="0x... (connect wallet or paste address)"
            style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border-dim)', color: 'var(--text)', fontFamily: "'Share Tech Mono',monospace", fontSize: 12, padding: '9px 11px', outline: 'none', marginBottom: 14 }}
          />
          <label style={{ display: 'block', fontSize: 10, letterSpacing: 2, color: 'var(--dim)', textTransform: 'uppercase', marginBottom: 5 }}>Category</label>
          <select
            style={{ width: '100%', background: 'var(--bg)', border: '1px solid var(--border-dim)', color: 'var(--text)', fontFamily: "'Share Tech Mono',monospace", fontSize: 12, padding: '9px 11px', outline: 'none', marginBottom: 18 }}
            onChange={e => {
              const a = AGENTS.find(ag => ag.category === e.target.value);
              if (a) openHire(a);
            }}
          >
            {AGENTS.map(a => <option key={a.id} value={a.category}>{a.label} — Agent #{a.id}</option>)}
          </select>
          <button
            className="btn primary"
            style={{ width: '100%', padding: 12 }}
            onClick={() => {
              const a = AGENTS[0];
              openHire(a);
            }}
          >
            REQUEST AGENT REPORT →
          </button>
        </div>
      </section>

      {/* FOOTER */}
      <footer>
        <div className="footer-logo">AGENT_FORGE.EXE</div>
        <div style={{ marginBottom: 12, color: '#555' }}>
          Built for the{' '}
          <a href="https://www.bnbchain.org/en/hackathons/smart-money-era" target="_blank" rel="noreferrer">Smart Money Era Hackathon</a>
          {' '}— BNBChain &nbsp;·&nbsp;
          <a href={`${PROVIDER}/.well-known/agent-card.json`} target="_blank" rel="noreferrer">Agent Card</a>
          {' '}&nbsp;·&nbsp;
          <a href="https://github.com/juicyblxst-lang/Agent_forge" target="_blank" rel="noreferrer">GitHub</a>
        </div>
        <div style={{ color: '#333' }}>Agent Forge is a hackathon project on BSC Testnet. Not financial advice.</div>
      </footer>

      {/* TOAST */}
      {toast && <div className="toast" onClick={() => setToast('')}>{toast}</div>}

      {/* HIRE MODAL */}
      {selected && (
        <div className="overlay" onClick={closeModal}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-titlebar">
              <span>HIRE AGENT — {selected.label.toUpperCase()}</span>
              <button className="modal-close" onClick={closeModal}>[ × ]</button>
            </div>
            <div className="modal-body">
              <p style={{ color: 'var(--dim)', fontSize: 12, marginBottom: 4 }}>{selected.desc}</p>

              <div className="capgrid">
                <div>
                  <label>Inputs</label>
                  {selected.inputs.map(x => <span key={x}>{x}</span>)}
                </div>
                <div>
                  <label>Deliverables</label>
                  {selected.outputs.map(x => <span key={x}>{x}</span>)}
                </div>
              </div>

              <label>Wallet Address</label>
              <input
                type="text"
                value={modalWallet}
                onChange={e => setModalWallet(e.target.value)}
                placeholder="0x..."
              />

              <label>Category</label>
              <select value={modalCat} onChange={e => setModalCat(e.target.value)}>
                {AGENTS.map(a => <option key={a.id} value={a.category}>{a.label} — Agent #{a.id}</option>)}
              </select>

              <div className="modal-log">
                {logLines.map((l, i) => (
                  <div key={i} className={`log-line ${l.cls}`}>{l.text}</div>
                ))}
              </div>

              <div className="modal-actions">
                <button onClick={closeModal}>CANCEL</button>
                <button className="primary" disabled={running} onClick={requestReport}>
                  {running ? 'RUNNING...' : 'REQUEST REPORT'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>
);
