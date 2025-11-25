// src/App.jsx - New version with a single source of truth

import React, { useState, useEffect, useRef } from 'react';
import './App.css';

function App() {
  const [status, setStatus] = useState('Initializing...');
  const [result, setResult] = useState('');
  const [screenshotCount, setScreenshotCount] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false); // A flag to disable buttons during actions

  // --- Master Polling Effect ---
  // This runs continuously to keep the frontend in sync with the backend
  useEffect(() => {
    const intervalId = setInterval(async () => {
      try {
        const response = await fetch('/api/status');
        const data = await response.json();

        // Update screenshot count from the source of truth
        setScreenshotCount(data.screenshotCount);

        // Check if a new result has arrived
        if (data.llmResult) {
          setResult(data.llmResult);
          setStatus('Complete');
          setIsProcessing(false);
        }
      } catch (error) {
        console.error('Polling Error:', error);
        setStatus('Error: Connection failed.');
      }
    }, 2000); // Poll every 2 seconds

    return () => clearInterval(intervalId); // Cleanup on component unmount
  }, []); // The empty array ensures this effect runs only once on startup

  // --- User Action Handlers ---
  // These functions now only send a command and update the local status text.
  // They DO NOT change the screenshot count or result directly.

  const handleAddScreenshot = async () => {
    setIsProcessing(true);
    setStatus('Triggering screenshot...');
    await fetch('/api/trigger', { method: 'POST' });
    setStatus('Waiting for agent to upload...');
    // The polling loop will eventually see the new screenshot and update the count
    setTimeout(() => setIsProcessing(false), 1000); // Re-enable buttons after a short delay
  };

  const handleSolve = async () => {
    if (screenshotCount === 0) return;
    setIsProcessing(true);
    setStatus('Sending to LLM for analysis...');
    setResult('');
    await fetch('/api/solve', { method: 'POST' });
    // The polling loop will see the count go to 0 and eventually get the result
  };
  
  const handleClear = async () => {
    setIsProcessing(true);
    setStatus('Clearing queue...');
    await fetch('/api/clear', { method: 'POST' });
    setResult(''); // Immediately clear the local result
    setStatus('Idle');
    // The polling loop will confirm the count is 0
    setIsProcessing(false);
  };

  return (
    <div className="container">
      <header className="header">
        <div className="title-status">
          <h1>Remote Assistant</h1>
          <p>Status: {status}</p>
        </div>
        <div className="button-group">
          <button onClick={handleAddScreenshot} disabled={isProcessing}>
            Add Screenshot
          </button>
          <button 
            onClick={handleSolve} 
            disabled={screenshotCount === 0 || isProcessing}
            className="solve-button"
          >
            Solve Problem ({screenshotCount})
          </button>
          <button onClick={handleClear} disabled={isProcessing} className="clear-button">
            Clear
          </button>
        </div>
      </header>
      <main className="result-box">
        <pre>{result || 'Awaiting result...'}</pre>
      </main>
    </div>
  );
}

export default App;