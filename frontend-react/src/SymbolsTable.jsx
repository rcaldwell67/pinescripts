

import React, { useEffect, useState } from "react";

  const [symbols, setSymbols] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [newSymbol, setNewSymbol] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [assetType, setAssetType] = useState("crypto");
  const [filter, setFilter] = useState("all");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [editSymbol, setEditSymbol] = useState(null); // symbol string
  const [editDescription, setEditDescription] = useState("");
  const [editAssetType, setEditAssetType] = useState("");
  const [editLiveEnabled, setEditLiveEnabled] = useState(0);
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editError, setEditError] = useState(null);

  // Compute available symbols for dropdown based on filter
  const availableSymbols = symbols.filter(sym => {
    if (filter === "all") return true;
    const type = sym.asset_type || sym.asset_class || "";
    return type.toLowerCase() === filter;
  });

  useEffect(() => {
    async function fetchSymbols() {
      try {
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

  const filteredSymbols = symbols.filter(sym => {
    if (filter === "all") return true;
    const type = sym.asset_type || sym.asset_class || "";
    return type.toLowerCase() === filter;
  });

  // When symbol changes, auto-fill description if available
  useEffect(() => {
    const found = availableSymbols.find(s => s.symbol === newSymbol);
    if (found && found.description) {
      setNewDescription(found.description);
    } else {
      setNewDescription("");
    }
  }, [newSymbol, availableSymbols]);

  async function handleAddSymbol(e) {
    e.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await fetch("http://localhost:4000/api/symbols", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: newSymbol, description: newDescription, asset_type: assetType })
      });
      if (!res.ok) throw new Error("Failed to add symbol");
      setShowForm(false);
      setNewSymbol("");
      setNewDescription("");
      setAssetType("crypto");
      // Refresh symbols
      await fetchSymbols();
    } catch (err) {
      setSubmitError("Failed to add symbol");
    } finally {
      setSubmitting(false);
    }
  }

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

  function startEditSymbol(sym) {
    setEditSymbol(sym.symbol);
    setEditDescription(sym.description || "");
    setEditAssetType(sym.asset_type || sym.asset_class || "crypto");
    setEditLiveEnabled(sym.live_enabled ?? 0);
    setEditError(null);
  }

  function cancelEdit() {
    setEditSymbol(null);
    setEditDescription("");
    setEditAssetType("");
    setEditLiveEnabled(0);
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
        body: JSON.stringify({ description: editDescription, asset_type: editAssetType, live_enabled: editLiveEnabled })
      });
      if (!res.ok) throw new Error("Failed to update symbol");
      cancelEdit();
      await fetchSymbols();
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
      await fetchSymbols();
    } catch (err) {
      alert("Failed to deactivate symbol");
    }
  }


  if (loading) return <section style={{ padding: 24 }}>Loading symbols...</section>;

  function renderError() {
    return error ? <div style={{ color: 'red', marginBottom: 16 }}>Error: {error}</div> : null;
  }

  return (
    <section style={{ padding: 24 }}>
      <h2>Symbols Table</h2>
      {renderError()}
      <div style={{ marginBottom: 16 }}>
        <button onClick={() => setShowForm(v => !v)} style={{ marginRight: 12 }}>
          {showForm ? "Cancel" : "Add Symbol"}
        </button>
        <span>Filter: </span>
        <select value={filter} onChange={e => setFilter(e.target.value)} style={{ marginLeft: 8 }}>
          <option value="all">All</option>
          <option value="crypto">Crypto</option>
          <option value="etf">Non-Crypto</option>
        </select>
      </div>
      {showForm && (
        <form onSubmit={handleAddSymbol} style={{ marginBottom: 20, background: 'var(--bg-mid)', padding: 16, borderRadius: 8, maxWidth: 420 }}>
          <div style={{ marginBottom: 8 }}>
            <label>Symbol: 
              <input value={newSymbol} onChange={e => setNewSymbol(e.target.value)} required style={{ marginLeft: 8, minWidth: 120 }} placeholder="Enter symbol" />
            </label>
          </div>
          <div style={{ marginBottom: 8 }}>
            <label>Description: <input value={newDescription} onChange={e => setNewDescription(e.target.value)} style={{ marginLeft: 8, minWidth: 180 }}/></label>
          </div>
          <div style={{ marginBottom: 8 }}>
            <label>Asset Type: </label>
            <select value={assetType} onChange={e => setAssetType(e.target.value)} style={{ marginLeft: 8 }}>
              <option value="crypto">Crypto</option>
              <option value="etf">Non-Crypto</option>
            </select>
          </div>
          <button type="submit" disabled={submitting || !newSymbol}>{submitting ? "Adding..." : "Add Symbol"}</button>
          {submitError && <span style={{ color: 'red', marginLeft: 12 }}>{submitError}</span>}
        </form>
      )}

      {editSymbol && (
        <form onSubmit={handleEditSubmit} style={{ marginBottom: 20, background: '#f7f7f7', padding: 16, borderRadius: 8, maxWidth: 420 }}>
          <h4>Edit Symbol: {editSymbol}</h4>
          <div style={{ marginBottom: 8 }}>
            <label>Description: <input value={editDescription} onChange={e => setEditDescription(e.target.value)} style={{ marginLeft: 8, minWidth: 180 }}/></label>
          </div>
          <div style={{ marginBottom: 8 }}>
            <label>Asset Type: </label>
            <select value={editAssetType} onChange={e => setEditAssetType(e.target.value)} style={{ marginLeft: 8 }}>
              <option value="crypto">Crypto</option>
              <option value="etf">Non-Crypto</option>
            </select>
          </div>
          <div style={{ marginBottom: 8 }}>
            <label>Live Enabled: </label>
            <select value={editLiveEnabled} onChange={e => setEditLiveEnabled(Number(e.target.value))} style={{ marginLeft: 8 }}>
              <option value={0}>No</option>
              <option value={1}>Yes</option>
            </select>
          </div>
          <button type="submit" disabled={editSubmitting}>{editSubmitting ? "Saving..." : "Save"}</button>
          <button type="button" onClick={cancelEdit} style={{ marginLeft: 12 }}>Cancel</button>
          {editError && <span style={{ color: 'red', marginLeft: 12 }}>{editError}</span>}
        </form>
      )}

      <div style={{overflowX: 'auto'}}>
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 16 }}>
          <thead>
            <tr style={{background: 'var(--bg-mid)'}}>
              <th style={{padding: '8px 12px', textAlign: 'left'}}>Symbol</th>
              <th style={{padding: '8px 12px', textAlign: 'left'}}>Description</th>
              <th style={{padding: '8px 12px', textAlign: 'left'}}>Asset Type</th>
              <th style={{padding: '8px 12px', textAlign: 'left'}}>Live Enabled</th>
              <th style={{padding: '8px 12px', textAlign: 'left'}}>Is Active</th>
              <th style={{padding: '8px 12px', textAlign: 'left'}}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredSymbols.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '16px', color: '#888' }}>
                  No symbols found.
                </td>
              </tr>
            ) : (
              filteredSymbols.map(sym => (
                <tr key={sym.symbol_key || sym.symbol}>
                  <td style={{padding: '8px 12px'}}>{sym.symbol}</td>
                  <td style={{padding: '8px 12px'}}>{sym.description || '-'}</td>
                  <td style={{padding: '8px 12px'}}>{sym.asset_type || sym.asset_class || '-'}</td>
                  <td style={{padding: '8px 12px'}}>{sym.live_enabled !== undefined ? String(sym.live_enabled) : '-'}</td>
                  <td style={{padding: '8px 12px'}}>{sym.isactive !== undefined ? String(sym.isactive) : '-'}</td>
                  <td style={{padding: '8px 12px'}}>
                    <button onClick={() => startEditSymbol(sym)} style={{ marginRight: 8 }}>Edit</button>
                    <button onClick={() => handleDeactivate(sym)} disabled={sym.isactive === 0} style={{ color: sym.isactive === 0 ? '#aaa' : '#a00' }}>Deactivate</button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
