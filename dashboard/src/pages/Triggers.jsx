/**
 * Triggers Page
 * 
 * Allows sales manager to manually control and trigger agent runs.
 * Supports full pipeline, scout-only, analyst-only, and writer-only modes.
 * Shows active trigger status with real-time polling.
 * 
 * Route: /triggers
 * 
 * Components:
 * - PageHeader: Title and subtitle
 * - RunFullPipelineCard: Full pipeline trigger with form
 * - RunScoutOnlyCard: Scout-only trigger with form
 * - RunAnalystOnlyCard: Analyst trigger (no form)
 * - RunWriterOnlyCard: Writer trigger (no form)
 * - ActiveRunStatus: Live status polling and progress
 * 
 * Usage:
 *   import Triggers from './pages/Triggers';
 *   <Route path="/triggers" element={<Triggers />} />
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  triggerFullPipeline,
  triggerScout,
  fetchTriggerStatus,
} from '../services/api';

// ============================================================================
// UTILITIES
// ============================================================================

const BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8001';

/**
 * Make API call to trigger analyst
 */
async function triggerAnalyst() {
  const response = await fetch(`${BASE_URL}/trigger/analyst`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

/**
 * Make API call to trigger writer
 */
async function triggerWriter() {
  const response = await fetch(`${BASE_URL}/trigger/writer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

/**
 * Format elapsed time in seconds
 */
function formatElapsedTime(seconds) {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}m ${secs}s`;
}

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

/**
 * PageHeader: Title and subtitle
 */
function PageHeader() {
  return (
    <div className="mb-6">
      <h1 className="text-3xl font-bold text-gray-900">Pipeline Controls</h1>
      <p className="text-gray-600 mt-1">Manually trigger agent runs</p>
    </div>
  );
}

/**
 * RunFullPipelineCard: Full pipeline trigger with form
 */
function RunFullPipelineCard({ onTrigger, isLoading, triggerStatus }) {
  const [industry, setIndustry] = useState('healthcare');
  const [location, setLocation] = useState('Buffalo, NY');
  const [count, setCount] = useState(20);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!industry.trim() || !location.trim()) {
      alert('Please fill in all required fields');
      return;
    }
    onTrigger('full', { industry, location, count });
  };

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <h2 className="text-xl font-bold text-gray-900 mb-2">Run Full Pipeline</h2>
      <p className="text-gray-600 mb-4">
        Finds new companies, scores them, enriches contacts, and generates email drafts — all in one run.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid md:grid-cols-2 gap-4">
          {/* Industry */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Industry *</label>
            <select
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="healthcare">Healthcare</option>
              <option value="hospitality">Hospitality</option>
              <option value="manufacturing">Manufacturing</option>
              <option value="retail">Retail</option>
              <option value="public_sector">Public Sector</option>
              <option value="office">Office</option>
            </select>
          </div>

          {/* Location */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Location *</label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Buffalo, NY"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        {/* Count Slider */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Find up to {count} companies
          </label>
          <input
            type="range"
            min="5"
            max="100"
            value={count}
            onChange={(e) => setCount(parseInt(e.target.value, 10))}
            className="w-full"
          />
          <div className="flex justify-between text-xs text-gray-500 mt-1">
            <span>5</span>
            <span>100</span>
          </div>
        </div>

        {/* Submit Button */}
        <button
          type="submit"
          disabled={isLoading}
          className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 transition font-semibold"
        >
          {isLoading ? '⏳ Running...' : '▶️ Run Full Pipeline'}
        </button>
      </form>

      {/* Trigger Status */}
      {triggerStatus && triggerStatus.mode === 'full' && (
        <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg text-sm">
          <p>
            <span className="font-semibold">{triggerStatus.status}</span>
            {triggerStatus.progress && ` — ${triggerStatus.progress}`}
          </p>
        </div>
      )}
    </div>
  );
}

/**
 * RunScoutOnlyCard: Scout-only trigger with form
 */
function RunScoutOnlyCard({ onTrigger, isLoading, triggerStatus }) {
  const [industry, setIndustry] = useState('healthcare');
  const [location, setLocation] = useState('Buffalo, NY');
  const [count, setCount] = useState(20);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!industry.trim() || !location.trim()) {
      alert('Please fill in all required fields');
      return;
    }
    onTrigger('scout', { industry, location, count });
  };

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <h2 className="text-xl font-bold text-gray-900 mb-2">Scout Only — Find Companies</h2>
      <p className="text-gray-600 mb-4">Find new companies without scoring or emailing</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid md:grid-cols-2 gap-4">
          {/* Industry */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Industry *</label>
            <select
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="healthcare">Healthcare</option>
              <option value="hospitality">Hospitality</option>
              <option value="manufacturing">Manufacturing</option>
              <option value="retail">Retail</option>
              <option value="public_sector">Public Sector</option>
              <option value="office">Office</option>
            </select>
          </div>

          {/* Location */}
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">Location *</label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Buffalo, NY"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        {/* Count Slider */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Find up to {count} companies
          </label>
          <input
            type="range"
            min="5"
            max="100"
            value={count}
            onChange={(e) => setCount(parseInt(e.target.value, 10))}
            className="w-full"
          />
          <div className="flex justify-between text-xs text-gray-500 mt-1">
            <span>5</span>
            <span>100</span>
          </div>
        </div>

        {/* Submit Button */}
        <button
          type="submit"
          disabled={isLoading}
          className="w-full px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 transition font-semibold"
        >
          {isLoading ? '⏳ Finding...' : '🔍 Find Companies'}
        </button>
      </form>

      {/* Trigger Status */}
      {triggerStatus && triggerStatus.mode === 'scout' && (
        <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg text-sm">
          <p>
            <span className="font-semibold">{triggerStatus.status}</span>
            {triggerStatus.progress && ` — ${triggerStatus.progress}`}
          </p>
        </div>
      )}
    </div>
  );
}

/**
 * RunAnalystOnlyCard: Analyst-only trigger
 */
function RunAnalystOnlyCard({ onTrigger, isLoading, triggerStatus, pendingAnalystCount }) {
  const handleSubmit = (e) => {
    e.preventDefault();
    onTrigger('analyst', {});
  };

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <h2 className="text-xl font-bold text-gray-900 mb-2">Analyst Only — Score Pending Companies</h2>
      <p className="text-gray-600 mb-4">
        Score all companies that have been found but not yet analyzed
      </p>

      <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
        <p className="text-sm text-blue-900 font-semibold">
          {pendingAnalystCount} companies pending analysis
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <button
          type="submit"
          disabled={isLoading || pendingAnalystCount === 0}
          className="w-full px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-400 transition font-semibold"
        >
          {isLoading ? '⏳ Scoring...' : '⭐ Score Now'}
        </button>
      </form>

      {/* Trigger Status */}
      {triggerStatus && triggerStatus.mode === 'analyst' && (
        <div className="mt-4 p-3 bg-purple-50 border border-purple-200 rounded-lg text-sm">
          <p>
            <span className="font-semibold">{triggerStatus.status}</span>
            {triggerStatus.progress && ` — ${triggerStatus.progress}`}
          </p>
        </div>
      )}
    </div>
  );
}

/**
 * RunWriterOnlyCard: Writer-only trigger
 */
function RunWriterOnlyCard({ onTrigger, isLoading, triggerStatus, pendingWriterCount }) {
  const handleSubmit = (e) => {
    e.preventDefault();
    onTrigger('writer', {});
  };

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <h2 className="text-xl font-bold text-gray-900 mb-2">Writer Only — Generate Email Drafts</h2>
      <p className="text-gray-600 mb-4">
        Generate email drafts for all approved high-score leads that do not have drafts yet
      </p>

      <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
        <p className="text-sm text-blue-900 font-semibold">
          {pendingWriterCount} approved leads without email drafts
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <button
          type="submit"
          disabled={isLoading || pendingWriterCount === 0}
          className="w-full px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 disabled:bg-gray-400 transition font-semibold"
        >
          {isLoading ? '⏳ Generating...' : '✉️ Generate Drafts'}
        </button>
      </form>

      {/* Trigger Status */}
      {triggerStatus && triggerStatus.mode === 'writer' && (
        <div className="mt-4 p-3 bg-orange-50 border border-orange-200 rounded-lg text-sm">
          <p>
            <span className="font-semibold">{triggerStatus.status}</span>
            {triggerStatus.progress && ` — ${triggerStatus.progress}`}
          </p>
        </div>
      )}
    </div>
  );
}

/**
 * ActiveRunStatus: Live status with polling
 */
function ActiveRunStatus({ triggerId, pollInterval = 5000 }) {
  const [status, setStatus] = useState(null);
  const [elapsedTime, setElapsedTime] = useState(0);
  const pollingRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!triggerId) return;

    const startTime = Date.now();

    /**
     * Poll trigger status
     */
    const pollStatus = async () => {
      try {
        const data = await fetchTriggerStatus(triggerId);
        setStatus(data);

        // Stop polling if completed or failed
        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(pollingRef.current);
          clearInterval(timerRef.current);
        }
      } catch (err) {
        console.error('Failed to fetch trigger status:', err);
      }
    };

    // Initial poll
    pollStatus();

    // Poll every N seconds
    pollingRef.current = setInterval(pollStatus, pollInterval);

    // Update elapsed time every second
    timerRef.current = setInterval(() => {
      setElapsedTime(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    return () => {
      clearInterval(pollingRef.current);
      clearInterval(timerRef.current);
    };
  }, [triggerId, pollInterval]);

  if (!status) return null;

  const statusColorMap = {
    starting: 'bg-yellow-50 border-yellow-200 text-yellow-900',
    running: 'bg-blue-50 border-blue-200 text-blue-900',
    completed: 'bg-green-50 border-green-200 text-green-900',
    failed: 'bg-red-50 border-red-200 text-red-900',
  };

  const colorClass = statusColorMap[status.status] || 'bg-gray-50 border-gray-200 text-gray-900';

  return (
    <div className={`p-4 border rounded-lg ${colorClass} mb-6`}>
      <div className="flex justify-between items-start mb-2">
        <p className="font-bold text-lg">Active Run: {status.stage || 'Pipeline'}</p>
        <p className="text-sm font-semibold">{formatElapsedTime(elapsedTime)}</p>
      </div>
      <p className="text-sm mb-2">
        Status: <span className="font-semibold uppercase">{status.status}</span>
      </p>
      {status.progress && (
        <p className="text-sm">{status.progress}</p>
      )}
    </div>
  );
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * Triggers: Pipeline control page
 */
export default function Triggers() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTrigger, setActiveTrigger] = useState(null);
  const [triggerStatus, setTriggerStatus] = useState(null);
  const [pendingCounts, setPendingCounts] = useState({
    analyst: 0,
    writer: 0,
  });

  /**
   * Load initial pending counts
   */
  useEffect(() => {
    const loadPendingCounts = async () => {
      // For now, use placeholder values
      // In production, these would be fetched from API endpoints
      setPendingCounts({
        analyst: 12,
        writer: 8,
      });
    };

    loadPendingCounts();
  }, []);

  /**
   * Handle trigger
   */
  const handleTrigger = async (mode, params) => {
    setIsLoading(true);
    setError(null);
    setTriggerStatus({ mode, status: 'starting', progress: '' });

    try {
      let response;

      switch (mode) {
        case 'full':
          response = await triggerFullPipeline(
            params.industry,
            params.location,
            params.count
          );
          break;
        case 'scout':
          response = await triggerScout(
            params.industry,
            params.location,
            params.count
          );
          break;
        case 'analyst':
          response = await triggerAnalyst();
          break;
        case 'writer':
          response = await triggerWriter();
          break;
        default:
          throw new Error(`Unknown trigger mode: ${mode}`);
      }

      setActiveTrigger(response.trigger_id);
      setTriggerStatus({
        mode,
        status: 'running',
        progress: response.message || 'Running...',
      });
    } catch (err) {
      console.error('Trigger failed:', err);
      setError(`Failed to trigger ${mode} run: ${err.message}`);
      setTriggerStatus({
        mode,
        status: 'failed',
        progress: err.message,
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-4xl mx-auto">
        <PageHeader />

        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded-lg mb-6">
            {error}
          </div>
        )}

        {activeTrigger && (
          <ActiveRunStatus triggerId={activeTrigger} />
        )}

        <RunFullPipelineCard
          onTrigger={handleTrigger}
          isLoading={isLoading && (!triggerStatus || triggerStatus.mode === 'full')}
          triggerStatus={triggerStatus}
        />

        <RunScoutOnlyCard
          onTrigger={handleTrigger}
          isLoading={isLoading && (!triggerStatus || triggerStatus.mode === 'scout')}
          triggerStatus={triggerStatus}
        />

        <RunAnalystOnlyCard
          onTrigger={handleTrigger}
          isLoading={isLoading && (!triggerStatus || triggerStatus.mode === 'analyst')}
          triggerStatus={triggerStatus}
          pendingAnalystCount={pendingCounts.analyst}
        />

        <RunWriterOnlyCard
          onTrigger={handleTrigger}
          isLoading={isLoading && (!triggerStatus || triggerStatus.mode === 'writer')}
          triggerStatus={triggerStatus}
          pendingWriterCount={pendingCounts.writer}
        />
      </div>
    </div>
  );
}
