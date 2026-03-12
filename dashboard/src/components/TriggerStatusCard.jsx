/**
 * TriggerStatusCard Component
 * 
 * Real-time status card for manual agent trigger runs.
 * Polls trigger status every 5 seconds while running.
 * 
 * Props:
 *   triggerId (string): UUID of the trigger run
 *   runMode (string): Mode name (full/scout/analyst/writer)
 *   industry (string): Industry name
 *   location (string): Location string
 *   status (string): Current status (starting/running/completed/failed)
 *   onCompleted (function): Callback when trigger completes or fails
 * 
 * Usage:
 *   <TriggerStatusCard
 *     triggerId="550e8400-e29b-41d4-a716-446655440000"
 *     runMode="full"
 *     industry="Healthcare"
 *     location="Buffalo, NY"
 *     status="running"
 *     onCompleted={handleCompleted}
 *   />
 */

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '../services/api.js';

export default function TriggerStatusCard({
  triggerId,
  runMode,
  industry,
  location,
  status,
  onCompleted,
}) {
  const navigate = useNavigate();
  const [triggerStatus, setTriggerStatus] = useState({
    mode: runMode,
    status,
    progress: 0,
    message: 'Initializing...',
    results: null,
    elapsed_seconds: 0,
  });
  const [isPolling, setIsPolling] = useState(status === 'starting' || status === 'running');

  useEffect(() => {
    if (!isPolling) return;

    const pollInterval = setInterval(async () => {
      try {
        const response = await api.fetchTriggerStatus(triggerId);
        setTriggerStatus(response);

        if (response.status === 'completed' || response.status === 'failed') {
          setIsPolling(false);
          onCompleted?.(response);
        }
      } catch (error) {
        console.error('Error polling trigger status:', error);
      }
    }, 5000);

    return () => clearInterval(pollInterval);
  }, [isPolling, triggerId, onCompleted]);

  // Format mode name for display
  const getModeLabel = () => {
    const modeMap = {
      full: 'Full Pipeline',
      scout: 'Find Companies',
      analyst: 'Score Companies',
      writer: 'Generate Drafts',
    };
    return modeMap[runMode] || runMode;
  };

  // Get status icon and color
  const getStatusIcon = () => {
    switch (triggerStatus.status) {
      case 'starting':
      case 'running':
        return <span className="text-3xl animate-spin">⚙️</span>;
      case 'completed':
        return <span className="text-3xl">✅</span>;
      case 'failed':
        return <span className="text-3xl">❌</span>;
      default:
        return <span className="text-3xl">⏳</span>;
    }
  };

  // Get progress bar color based on status
  const getProgressColor = () => {
    switch (triggerStatus.status) {
      case 'completed':
        return 'bg-green-500';
      case 'failed':
        return 'bg-red-500';
      default:
        return 'bg-blue-500';
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-6 border-l-4 border-blue-500">
      {/* Header with status icon */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-4">
          {getStatusIcon()}
          <div>
            <p className="text-lg font-bold text-gray-900">
              {getModeLabel()} — {industry} / {location}
            </p>
            <p className="text-sm text-gray-600 mt-1">
              Run ID: <code className="bg-gray-100 px-2 py-1 rounded">{triggerId.substring(0, 8)}</code>
            </p>
          </div>
        </div>
      </div>

      {/* Status text */}
      <div className="mb-4">
        {triggerStatus.status === 'running' && (
          <p className="text-base font-semibold text-blue-600">
            Running... elapsed{' '}
            <span className="text-lg font-bold">{triggerStatus.elapsed_seconds}s</span>
          </p>
        )}
        {triggerStatus.status === 'starting' && (
          <p className="text-base font-semibold text-yellow-600">Starting pipeline...</p>
        )}
        {triggerStatus.status === 'completed' && (
          <p className="text-base font-semibold text-green-600">
            Completed in <span className="font-bold">{triggerStatus.elapsed_seconds}s</span>
          </p>
        )}
        {triggerStatus.status === 'failed' && (
          <p className="text-base font-semibold text-red-600">Failed — check Airflow logs</p>
        )}
      </div>

      {/* Progress bar */}
      <div className="mb-4">
        <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
          <div
            className={`h-full ${getProgressColor()} transition-all duration-500`}
            style={{
              width:
                triggerStatus.status === 'completed'
                  ? '100%'
                  : triggerStatus.status === 'failed'
                    ? '100%'
                    : `${Math.min(triggerStatus.progress || 0, 95)}%`,
            }}
          />
        </div>
      </div>

      {/* Status message */}
      {triggerStatus.message && (
        <p className="text-sm text-gray-700 mb-4 bg-gray-50 p-3 rounded">
          {triggerStatus.message}
        </p>
      )}

      {/* Results summary (when completed or failed) */}
      {triggerStatus.status === 'completed' && triggerStatus.results && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
          <p className="font-bold text-green-900 mb-3">Results Summary</p>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-gray-600">Companies Found</p>
              <p className="text-2xl font-bold text-green-600">
                {triggerStatus.results.companies_found || 0}
              </p>
            </div>
            <div>
              <p className="text-gray-600">High Score Leads</p>
              <p className="text-2xl font-bold text-blue-600">
                {triggerStatus.results.high_score_leads || 0}
              </p>
            </div>
            <div>
              <p className="text-gray-600">Emails Drafted</p>
              <p className="text-2xl font-bold text-purple-600">
                {triggerStatus.results.emails_drafted || 0}
              </p>
            </div>
            <div>
              <p className="text-gray-600">Success Rate</p>
              <p className="text-2xl font-bold text-yellow-600">
                {triggerStatus.results.success_rate || '0'}%
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-2">
        {triggerStatus.status === 'completed' && (
          <button
            onClick={() => navigate('/leads?date_from=today')}
            className="px-4 py-2 bg-blue-600 text-white rounded font-semibold hover:bg-blue-700 transition"
          >
            View Results →
          </button>
        )}
        {triggerStatus.status === 'running' && (
          <p className="text-sm text-gray-600">
            Updates every 5 seconds... (do not close this window)
          </p>
        )}
        {triggerStatus.status === 'failed' && (
          <a
            href="http://localhost:8080/dags"
            target="_blank"
            rel="noopener noreferrer"
            className="px-4 py-2 bg-red-600 text-white rounded font-semibold hover:bg-red-700 transition"
          >
            Check Airflow Logs
          </a>
        )}
      </div>
    </div>
  );
}
