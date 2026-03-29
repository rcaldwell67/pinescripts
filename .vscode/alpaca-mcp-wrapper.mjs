// alpaca-mcp-wrapper.mjs
// Wrapper for Alpaca MCP server integration
// Usage: import and call runAlpacaBacktest({ script, symbol, timeframe, ... })

import fetch from 'node-fetch';

/**
 * Runs a Pine Script backtest on the Alpaca MCP server.
 * @param {Object} params
 * @param {string} params.script - Pine Script source code
 * @param {string} params.symbol - Symbol to backtest (e.g., 'CLM')
 * @param {string} params.timeframe - Timeframe (e.g., '5m')
 * @param {string} [params.serverUrl] - MCP server URL (default: 'http://localhost:8000')
 * @param {Object} [params.options] - Additional options for the MCP server
 * @returns {Promise<Object>} - Backtest results
 */
export async function runAlpacaBacktest({ script, symbol, timeframe, serverUrl = 'http://localhost:8000', options = {} }) {
  const payload = {
    script,
    symbol,
    timeframe,
    ...options
  };
  const response = await fetch(`${serverUrl}/backtest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`Backtest failed: ${response.status} ${response.statusText}`);
  }
  return await response.json();
}

/**
 * Example usage:
 *
 * import { runAlpacaBacktest } from './alpaca-mcp-wrapper.mjs';
 *
 * const result = await runAlpacaBacktest({
 *   script: '...pine script...',
 *   symbol: 'CLM',
 *   timeframe: '5m'
 * });
 * console.log(result);
 */
