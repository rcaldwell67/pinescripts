
import React, { useEffect, useState } from "react";

function SymbolsTable() {
  const [symbols, setSymbols] = useState([]);
  const [alpacaSymbols, setAlpacaSymbols] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [newSymbol, setNewSymbol] = useState("");
  const [assetType, setAssetType] = useState("crypto");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [editSymbol, setEditSymbol] = useState(null);
  const [editDescription, setEditDescription] = useState("");
  const [editAssetType, setEditAssetType] = useState("");
  const [editLiveEnabled, setEditLiveEnabled] = useState(0);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState(null);
  const [editIsActive, setEditIsActive] = useState(1);

  useEffect(() => {
    async function fetchSymbols() {
      try {
        setLoading(true);
        setError(null);
        const res = await fetch("http://localhost:4000/api/symbols");
        if (!res.ok) throw new Error("Failed to load symbols from backend API");
        const data = await res.json();
        setSymbols(data || []);
      } catch (err) {
        setError(err.message || "Unknown error");
      } finally {
        setLoading(false);
      }
    }
    fetchSymbols();
  }, []);

  useEffect(() => {
    async function fetchAlpacaSymbols() {
      try {
        const res = await fetch("http://localhost:4000/api/alpaca-symbols");
        if (!res.ok) throw new Error("Failed to load Alpaca symbols");
        const data = await res.json();
        setAlpacaSymbols(data || []);
      } catch (err) {
        // Don't block UI if this fails
      }
    }
    fetchAlpacaSymbols();
  }, []);

  // Filter for add-symbol dropdown
  const availableSymbols = alpacaSymbols.filter(sym => {
    if (assetType === "all") return true;
    const type = (sym.asset_class || sym.type || "").toLowerCase();
    if (assetType === "crypto") return type === "crypto";
    if (assetType === "etf") return type !== "crypto";
    return true;
  });

  // No auto-description logic needed

  async function handleAddSymbol(e) {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    try {
      // Find the selected Alpaca symbol to get its asset_class
      const selectedAlpaca = alpacaSymbols.find(sym => sym.symbol === newSymbol);
      let asset_type = "";
      let description = "";
      if (selectedAlpaca) {
        asset_type = (selectedAlpaca.asset_class || "").toLowerCase();
        if (asset_type === "us_equity") asset_type = "etf";
        description = selectedAlpaca.name || "";
      }
      const res = await fetch("http://localhost:4000/api/symbols", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: newSymbol, asset_type, description })
      });
      if (!res.ok) throw new Error("Failed to add symbol");
      setShowForm(false);
      setNewSymbol("");
      setAssetType("crypto");
      // Refresh symbols
      const symbolsRes = await fetch("http://localhost:4000/api/symbols");
      setSymbols(await symbolsRes.json());
    } catch (err) {
      setSubmitError("Failed to add symbol");
    } finally {
      setSubmitting(false);
    }
  }

  function startEditSymbol(sym) {
    setEditSymbol(sym.symbol);
    setEditDescription(sym.description || "");
    setEditAssetType(sym.asset_type || sym.asset_class || "crypto");
    setEditLiveEnabled(sym.live_enabled ?? 0);
    setEditIsActive(sym.isactive ?? 1);
    setEditError(null);
  }

  function cancelEdit() {
    setEditSymbol(null);
    setEditDescription("");
    setEditAssetType("");
    setEditLiveEnabled(0);
    setEditIsActive(1);
    setEditError(null);
  }

  async function handleEditSubmit(e) {
    e.preventDefault();
    setEditSubmitting(true);
    setEditError(null);
    try {
      const res = await fetch(`http://localhost:4000/api/symbols/${encodeURIComponent(editSymbol)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: editDescription, asset_type: editAssetType, live_enabled: editLiveEnabled, isactive: editIsActive })
      });
      if (!res.ok) throw new Error("Failed to update symbol");
      cancelEdit();
      const symbolsRes = await fetch("http://localhost:4000/api/symbols");
      setSymbols(await symbolsRes.json());
    } catch (err) {
      setEditError("Failed to update symbol");
    } finally {
      setEditSubmitting(false);
    }
  }

  async function handleDeactivate(sym) {
    if (!window.confirm(`Deactivate symbol '${sym.symbol}'?`)) return;
    try {
      await fetch(`http://localhost:4000/api/symbols/${encodeURIComponent(sym.symbol)}/deactivate`, {
        method: "PATCH"
      });
      const symbolsRes = await fetch("http://localhost:4000/api/symbols");
      setSymbols(await symbolsRes.json());
    } catch (err) {
      alert("Failed to deactivate symbol");
    }
  }

  if (loading) {
    return <section style={{ padding: 24 }}>Loading symbols...</section>;
  }

  function renderError() {
    return error ? <div style={{ color: 'red', marginBottom: 16 }}>Error: {error}</div> : null;
  }

  // Filter symbols for table based on assetType
  const filteredSymbols = symbols.filter(sym => {
    if (assetType === "all") return true;
    const type = sym.asset_type || sym.asset_class || "";
    return type.toLowerCase() === assetType;
  });

  return (
    <section style={{ padding: 24 }}>
      <h2>Symbols Table</h2>
      {renderError()}
      <div style={{ marginBottom: 16 }}>
        <button onClick={() => setShowForm(v => !v)} style={{ marginRight: 12 }}>
          {showForm ? "Cancel" : "Add Symbol"}
        </button>
        <span>Filter: </span>
        <select value={assetType} onChange={e => setAssetType(e.target.value)} style={{ marginLeft: 8 }}>
          <option value="all">All</option>
          <option value="crypto">Crypto</option>
          <option value="etf">Non-Crypto</option>
        </select>
      </div>
      {showForm && (
        <form onSubmit={handleAddSymbol} style={{ marginBottom: 20, background: 'var(--bg-mid)', padding: 16, borderRadius: 8, maxWidth: 420 }}>
          <div style={{ marginBottom: 8 }}>
            <label>Symbol: 
              <select value={newSymbol} onChange={e => setNewSymbol(e.target.value)} required style={{ marginLeft: 8, minWidth: 120 }}>
                <option value="">Select symbol...</option>
                {availableSymbols.map(sym => (
                  <option key={sym.symbol} value={sym.symbol}>
                    {sym.symbol} - {sym.name || sym.exchange || sym.asset_class || sym.type}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button type="submit" disabled={submitting}>{submitting ? "Adding..." : "Add Symbol"}</button>
          {submitError && <div style={{ color: 'red', marginTop: 8 }}>{submitError}</div>}
        </form>
      )}
      <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 16 }}>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Description</th>
            <th>Asset Type</th>
            <th>Live Enabled</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {filteredSymbols.map(sym => (
            editSymbol === sym.symbol ? (
              <tr key={sym.symbol} style={{ background: '#f5f5f5' }}>
                <td>{sym.symbol}</td>
                <td><input value={editDescription} onChange={e => setEditDescription(e.target.value)} /></td>
                <td>
                  <select value={editAssetType} onChange={e => setEditAssetType(e.target.value)}>
                    <option value="crypto">Crypto</option>
                    <option value="etf">Non-Crypto</option>
                  </select>
                </td>
                <td>
                  <input type="checkbox" checked={!!editLiveEnabled} onChange={e => setEditLiveEnabled(e.target.checked ? 1 : 0)} />
                </td>
                <td>
                  <label style={{ marginRight: 8 }}>
                    <input type="checkbox" checked={!!editIsActive} onChange={e => setEditIsActive(e.target.checked ? 1 : 0)} /> Active
                  </label>
                  <button onClick={handleEditSubmit} disabled={editSubmitting}>Save</button>
                  <button onClick={cancelEdit} style={{ marginLeft: 8 }}>Cancel</button>
                  {editError && <div style={{ color: 'red' }}>{editError}</div>}
                </td>
              </tr>
            ) : (
              <tr key={sym.symbol}>
                <td>{sym.symbol}</td>
                <td>{sym.description}</td>
                <td>{sym.asset_type || sym.asset_class}</td>
                <td>{sym.live_enabled ? "Yes" : "No"}</td>
                <td>
                  <button onClick={() => startEditSymbol(sym)}>Edit</button>
                  <button onClick={() => handleDeactivate(sym)} style={{ marginLeft: 8 }}>Deactivate</button>
                </td>
              </tr>
            )
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default SymbolsTable;
