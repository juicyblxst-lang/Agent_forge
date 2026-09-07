import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

declare global { interface Window { ethereum?: { request: (args: { method: string; params?: unknown[] }) => Promise<unknown>; on?: (event: string, cb: (...args: unknown[]) => void) => void; removeListener?: (event: string, cb: (...args: unknown[]) => void) => void } } }

type Agent = {
  name: string; category: string; description: string; skill: string; risk: string; protocol: string; inputs: string[]; outputs: string[];
};

const agents: Agent[] = [
  { name: 'Smart Money Rebalancing Agent', category: 'Rebalancing', skill: 'negotiate-erc8183-job', risk: 'Medium', protocol: 'PancakeSwap V3', description: 'Automatically manages PancakeSwap V3 LP ranges on BSC. Detects out-of-range positions and resets to an optimal tick band based on current volatility and fee tier. Returns a signed action report with the new range, estimated gas, and projected fee capture improvement.', inputs: ['Wallet address', 'Current LP position'], outputs: ['Range recommendation', 'Estimated gas', 'Projected fee improvement'] },
  { name: 'Smart Money Grid Trading Agent', category: 'Grid Trading', skill: 'negotiate-erc8183-job', risk: 'Medium', protocol: 'PancakeSwap', description: 'Places and manages automated grid orders on PancakeSwap. Buys low and sells high within a configurable price band, capturing spread from sideways markets. Returns a trade log with entry/exit prices and P&L.', inputs: ['Wallet address', 'Trading pair', 'Capital', 'Grid count', 'Price range'], outputs: ['Grid levels', 'Profit estimate', 'Risk factors'] },
  { name: 'Smart Money Yield Agent', category: 'Yield Optimisation', skill: 'negotiate-erc8183-job', risk: 'Low–Medium', protocol: 'Aave V3 / Venus / Lista / PancakeSwap', description: 'Routes deposited liquidity to the highest available APR across Aave V3, Venus, Lista Liquid Staking, and PancakeSwap pools on BSC. Returns a ranked APR comparison with a recommended action.', inputs: ['Wallet address', 'Asset symbol', 'Deposit amount'], outputs: ['Ranked APRs', 'Recommended protocol', 'Projected returns'] },
  { name: 'Smart Money Health Factor Agent', category: 'Health Factor Monitoring', skill: 'negotiate-erc8183-job', risk: 'Risk monitoring', protocol: 'Aave V3 / Venus', description: 'Monitors lending positions and flags positions approaching the liquidation threshold. Returns the current health factor, collateral/debt summary, risk level, and a structured recommendation to hold, monitor, add collateral, or repay.', inputs: ['Wallet address'], outputs: ['Health factor', 'Liquidation buffer', 'Risk recommendation'] },
];

const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

function App() {
  const [account, setAccount] = useState('');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('All');
  const [selected, setSelected] = useState<Agent | null>(null);
  const [quote, setQuote] = useState<any>(null);
  const [status, setStatus] = useState('');

  const filtered = useMemo(() => agents.filter(a => {
    const text = `${a.name} ${a.category} ${a.description} ${a.protocol}`.toLowerCase();
    return text.includes(query.toLowerCase()) && (category === 'All' || a.category === category);
  }), [query, category]);

  useEffect(() => {
    const eth = window.ethereum;
    if (!eth) return;
    const onAccounts = (...args: unknown[]) => setAccount(String((args[0] as string[] | undefined)?.[0] || ''));
    eth.on?.('accountsChanged', onAccounts);
    return () => eth.removeListener?.('accountsChanged', onAccounts);
  }, []);

  async function connect() {
    if (!window.ethereum) { setStatus('Install a browser wallet such as MetaMask to connect.'); return; }
    try {
      const accounts = await window.ethereum.request({ method: 'eth_requestAccounts' }) as string[];
      setAccount(accounts[0] || '');
      await window.ethereum.request({ method: 'wallet_switchEthereumChain', params: [{ chainId: '0x61' }] });
      setStatus('Connected to BNB Smart Chain Testnet.');
    } catch (e: any) { setStatus(e?.message || 'Wallet connection failed.'); }
  }

  function disconnect() { setAccount(''); setSelected(null); setQuote(null); setStatus('Wallet disconnected from the marketplace.'); }

  async function hire(agent: Agent) {
    setSelected(agent); setQuote(null); setStatus('');
    if (!account) { setStatus('Connect your wallet before hiring an agent.'); return; }
    if (!API_URL) { setStatus('Marketplace backend URL is not configured yet. Set VITE_API_URL for the deployed Render API.'); return; }
    try {
      const response = await fetch(`${API_URL}/a2a`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ jsonrpc: '2.0', id: Date.now(), method: 'message/send', params: { message: { parts: [{ type: 'data', data: { skill: agent.skill, task_description: `[category:${agent.category.toLowerCase().replaceAll(' ', '-').replace('optimisation','yield')}] Hire ${agent.name} for wallet ${account}` } }] } } }) });
      const data = await response.json();
      setQuote(data?.result?.message?.parts?.[0]?.data || null);
      if (!response.ok) throw new Error(data?.error || 'Quote request failed');
    } catch (e: any) { setStatus(e?.message || 'Unable to reach the agent service.'); }
  }

  return <div className="app">
    <header className="nav"><div className="brand"><span className="mark">◆</span><span>AgentForge</span><small>SMART MONEY ERA</small></div><div className="navlinks"><a href="#agents">Agents</a><a href="#how">How it works</a><a href="#network">BNB Testnet</a></div><button className="wallet" onClick={account ? disconnect : connect}>{account ? `${account.slice(0,6)}…${account.slice(-4)}` : 'Connect wallet'}</button></header>
    <main>
      <section className="hero"><div className="eyebrow">BNB CHAIN · SMART MONEY ERA</div><h1>Find the agent that<br/><span>moves your money.</span></h1><p>Discover purpose-built DeFi agents for rebalancing, grid trading, yield optimisation and health-factor monitoring.</p><div className="heroStats"><div><b>04</b><span>AGENTS</span></div><div><b>ERC-8004</b><span>IDENTITY</span></div><div><b>ERC-8183</b><span>JOBS</span></div></div></section>
      <section id="agents" className="market"><div className="toolbar"><div><div className="sectionKicker">AGENT MARKETPLACE</div><h2>Available agents</h2></div><div className="controls"><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search agents, protocols, capabilities…"/><select value={category} onChange={e => setCategory(e.target.value)}><option>All</option>{agents.map(a => <option key={a.category}>{a.category}</option>)}</select></div></div>
      <div className="grid">{filtered.map(agent => <article className="card" key={agent.name}><div className="cardTop"><span className="badge">{agent.category}</span><span className="live">● LIVE</span></div><div className="agentIcon">{agent.category === 'Rebalancing' ? '↗' : agent.category === 'Grid Trading' ? '▦' : agent.category === 'Yield Optimisation' ? '◈' : '♥'}</div><h3>{agent.name}</h3><p>{agent.description}</p><div className="meta"><span>PROTOCOL<b>{agent.protocol}</b></span><span>RISK<b>{agent.risk}</b></span></div><div className="cardActions"><button className="details" onClick={() => {setSelected(agent);setQuote(null)}}>View capabilities</button><button className="hire" onClick={() => hire(agent)}>Hire agent →</button></div></article>)}</div></section>
      <section id="how" className="how"><div><div className="sectionKicker">NON-CUSTODIAL FLOW</div><h2>Know what you’re hiring.</h2></div><div className="steps"><div><b>01</b><strong>Connect</strong><p>Connect a wallet to identify the buyer for an ERC-8183 job.</p></div><div><b>02</b><strong>Inspect</strong><p>Read the agent’s identity, capability, protocol, inputs and expected deliverables before committing.</p></div><div><b>03</b><strong>Hire</strong><p>Request a signed quote from the agent service. Job execution remains on-chain.</p></div></div></section>
      <section id="network" className="network"><span className="bnbdot">◆</span><div><b>Built for BNB Smart Chain Testnet</b><p>ERC-8004 agent identity · ERC-8183 job negotiation · BSC Testnet execution</p></div></section>
    </main>
    {status && <div className="toast" onClick={() => setStatus('')}>{status}</div>}
    {selected && <div className="overlay" onClick={() => setSelected(null)}><div className="modal" onClick={e => e.stopPropagation()}><button className="close" onClick={() => setSelected(null)}>×</button><span className="badge">{selected.category}</span><h2>{selected.name}</h2><p>{selected.description}</p><div className="capgrid"><div><label>INPUTS</label>{selected.inputs.map(x=><span key={x}>{x}</span>)}</div><div><label>DELIVERABLES</label>{selected.outputs.map(x=><span key={x}>{x}</span>)}</div></div><div className="quote">{quote ? <><label>SIGNED QUOTE</label><code>{quote.negotiation_hash}</code><span>{quote.provider_address}</span><b>Price: {Number(quote.price || 0) / 1e18} token</b></> : <><label>READY TO HIRE</label><p>Request a signed ERC-8183 quote from this agent.</p><button className="hire wide" onClick={() => hire(selected)}>Request quote →</button></>}</div></div></div>}
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
