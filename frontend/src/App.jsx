import { useState, useEffect } from 'react'
import axios from 'axios'
import './App.css'

function App() {
  const [state, setState] = useState(null)
  const [trades, setTrades] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const stateRes = await axios.get('/api/state')
        setState(stateRes.data)
        
        const tradesRes = await axios.get('/api/trades')
        setTrades(tradesRes.data.reverse().slice(0, 10)) // Get last 10 trades
        setError(null)
      } catch (err) {
        setError("Connecting to bot engine...")
      }
    }
    
    fetchData()
    const interval = setInterval(fetchData, 3000)
    return () => clearInterval(interval)
  }, [])

  if (error) {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <h2>{error}</h2>
      </div>
    )
  }

  if (!state || state.status === "Waiting for bot to generate state...") {
    return (
      <div className="loading-screen">
        <div className="spinner"></div>
        <h2>Waiting for bot to generate state...</h2>
      </div>
    )
  }

  return (
    <div className="dashboard-container">
      <header className="header">
        <h1>XAUUSD Signal Bot</h1>
        <div className="status-badge pulse">⚡ LIVE</div>
      </header>

      <div className="grid">
        <div className="card stat-card">
          <h3>Daily P&L</h3>
          <p className={state.daily_pnl >= 0 ? "profit" : "loss"}>
            ${state.daily_pnl > 0 ? "+" : ""}{state.daily_pnl}
          </p>
        </div>
        <div className="card stat-card">
          <h3>Trades Today</h3>
          <p>{state.trades_today}</p>
        </div>
      </div>

      <div className="card section">
        <h2>Active Trade</h2>
        {state.active_trade ? (
          <div className="active-trade-box">
            <div className="trade-header">
              <span className={`direction ${state.active_trade.signal.toLowerCase()}`}>
                {state.active_trade.signal === 'LONG' ? '🟢 BUY' : '🔴 SELL'}
              </span>
              <span className="confidence">{state.active_trade.confidence}% Confidence</span>
            </div>
            <div className="trade-details">
              <div><span>Entry:</span> <strong>{state.active_trade.entry_price}</strong></div>
              <div><span>TP:</span> <strong>{state.active_trade.tp_price}</strong></div>
              <div><span>SL:</span> <strong>{state.active_trade.sl_price}</strong></div>
            </div>
          </div>
        ) : (
          <div className="empty-state">
            <p>Scanning market for opportunities...</p>
            <div className="radar"></div>
          </div>
        )}
      </div>

      <div className="card section">
        <h2>Recent Trades</h2>
        <div className="trades-list">
          {trades.length > 0 ? trades.map((trade, i) => (
            <div key={i} className="trade-item">
              <div className="trade-main">
                <span className={trade.signal === 'LONG' ? "long" : "short"}>{trade.signal}</span>
                <span className="price">{trade.entry} → {trade.exit}</span>
              </div>
              <div className="trade-result">
                <span className={trade.pnl >= 0 ? "profit" : "loss"}>
                  {trade.pnl >= 0 ? "+" : ""}${trade.pnl}
                </span>
                <span className="reason">{trade.reason}</span>
              </div>
            </div>
          )) : (
            <p className="empty-text">No trades completed today.</p>
          )}
        </div>
      </div>
    </div>
  )
}

export default App
