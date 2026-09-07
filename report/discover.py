import os
import httpx
from dotenv import load_dotenv

load_dotenv()

HACKATHON_CATEGORIES = ["rebalancing", "grid-trading", "yield", "health-factor"]

SCAN_API   = os.getenv("SCAN_API_BASE", "https://api.8004scan.io/api/v1")
AGENT_HOST = os.getenv("AGENT_HOST", "http://localhost:8010")


def _liveness_probe(url: str, timeout: int = 5) -> bool:
    """Check if an agent's /status endpoint is reachable."""
    try:
        base = url.rstrip("/").replace("/.well-known/agent-card.json", "")
        r = httpx.get(f"{base}/status", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def discover_from_env(verbose: bool = False) -> list[dict]:
    """
    Fast path: resolve agents directly from env-set agent IDs.
    These IDs are produced by 02_register_provider.py and saved to .env.
    """
    id_map = {
        "rebalancing":  os.getenv("AGENT_ID_REBALANCING"),
        "grid-trading": os.getenv("AGENT_ID_GRID_TRADING"),
        "yield":        os.getenv("AGENT_ID_YIELD"),
        "health-factor":os.getenv("AGENT_ID_HEALTH_FACTOR"),
    }

    # If none are set, return empty — fall through to scan API
    if not any(id_map.values()):
        return []

    # Provider wallet is the same for all 4 agents in this project
    provider_wallet = os.getenv("PROVIDER_WALLET_ADDRESS", "")

    agents = []
    for category, agent_id in id_map.items():
        if not agent_id:
            if verbose:
                print(f"[discover] no env ID for {category} — skipping")
            continue

        a2a_url = AGENT_HOST.rstrip("/")
        live    = _liveness_probe(a2a_url)

        if verbose:
            status = "✓ live" if live else "✗ unreachable"
            print(f"[discover] {category}: agentId={agent_id}  {status}  {a2a_url}")

        agents.append({
            "agent_id":       int(agent_id),
            "category":       category,
            "provider_wallet": provider_wallet,
            "a2a_url":        a2a_url,
            "erc8183_url":    a2a_url,
            "live":           live,
            "source":         "env",
        })

    return agents


def discover_from_scan(verbose: bool = False) -> list[dict]:
    """
    Slow path: query 8004scan indexer for agents with hackathon category tags.
    Falls back gracefully if the API is unreachable.
    """
    agents = []
    headers = {}
    api_key = os.getenv("SCAN_API_KEY", "")
    if api_key:
        headers["X-API-Key"] = api_key

    for category in HACKATHON_CATEGORIES:
        try:
            r = httpx.get(
                f"{SCAN_API}/agents",
                params={"tag": f"category:{category}", "limit": 5},
                headers=headers,
                timeout=10,
            )
            if r.status_code != 200:
                continue
            for item in r.json().get("data", []):
                a2a_url = (
                    item.get("a2aUrl")
                    or item.get("erc8183Url")
                    or item.get("endpoint", "")
                )
                live = _liveness_probe(a2a_url) if a2a_url else False
                if verbose:
                    status = "✓ live" if live else "✗ unreachable"
                    print(f"[discover:scan] {category}: {item.get('agentId')}  {status}")
                agents.append({
                    "agent_id":        item.get("agentId"),
                    "category":        category,
                    "provider_wallet": item.get("owner", ""),
                    "a2a_url":         a2a_url,
                    "erc8183_url":     a2a_url,
                    "live":            live,
                    "source":          "scan",
                })
        except Exception as e:
            if verbose:
                print(f"[discover:scan] {category}: scan failed — {e}")

    return agents


def discover_agents(
    categories:   list[str] = None,
    require_live: bool = True,
    verbose:      bool = False,
) -> list[dict]:
    """
    Main entry point. Tries env IDs first (fast), falls back to scan API.
    Returns list of agent records filtered by categories and liveness.
    """
    categories = categories or HACKATHON_CATEGORIES

    # Try env IDs first
    agents = discover_from_env(verbose=verbose)

    # Fall back to scan API if env has nothing
    if not agents:
        if verbose:
            print("[discover] no env IDs found — querying 8004scan...")
        agents = discover_from_scan(verbose=verbose)

    # Filter by requested categories
    agents = [a for a in agents if a["category"] in categories]

    # Optionally filter to only live agents
    if require_live:
        agents = [a for a in agents if a["live"]]

    return agents


def pick_for_category(agents: list[dict], category: str) -> dict | None:
    """Return the first live agent matching the given category."""
    matches = [a for a in agents if a["category"] == category]
    return matches[0] if matches else None


def assert_all_four_covered(agents: list[dict]) -> None:
    """
    Verify all 4 hackathon categories have at least one live agent.
    Prints a warning for any missing category — does not hard-fail,
    so the client can still proceed with whichever categories are live.
    """
    found = {a["category"] for a in agents}
    for cat in HACKATHON_CATEGORIES:
        if cat not in found:
            print(f"[discover] ⚠  WARNING: no live agent for category '{cat}'")
        else:
            print(f"[discover] ✓ {cat} covered")
