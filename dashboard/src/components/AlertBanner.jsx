/**
 * AlertBanner Component
 * 
 * Sticky alert banner for hot leads that need attention.
 * Supports dismissal with localStorage persistence.
 * 
 * Props:
 *   alerts (array): List of hot lead objects with id, name, savings_mid
 *   onDismiss (function): Callback when dismissed
 *   onViewLead (function): Callback when viewing a lead
 * 
 * Usage:
 *   <AlertBanner
 *     alerts={hotLeads}
 *     onDismiss={handleDismiss}
 *     onViewLead={handleViewLead}
 *   />
 */

import React, { useState, useEffect } from 'react';

function formatCurrency(value) {
  if (!value) return '$0';
  if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(0)}k`;
  return `$${value}`;
}

export default function AlertBanner({ alerts, onDismiss, onViewLead }) {
  const [isDismissed, setIsDismissed] = useState(false);
  const [displayedAlerts, setDisplayedAlerts] = useState([]);

  useEffect(() => {
    // Restore dismissed state from localStorage
    const dismissed = localStorage.getItem('alertBanner_dismissed');
    if (dismissed === 'true') {
      setIsDismissed(true);
    }

    // Update displayed alerts when alerts change
    if (alerts && alerts.length > 0) {
      setIsDismissed(false);
      localStorage.removeItem('alertBanner_dismissed');
      setDisplayedAlerts(alerts.slice(0, 3));
    }
  }, [alerts]);

  if (isDismissed || !displayedAlerts || displayedAlerts.length === 0) {
    return null;
  }

  const remainingCount = Math.max(0, alerts.length - 3);

  const handleDismiss = () => {
    setIsDismissed(true);
    localStorage.setItem('alertBanner_dismissed', 'true');
    onDismiss?.();
  };

  return (
    <div className="sticky top-0 z-40 bg-gradient-to-r from-red-600 to-orange-600 text-white shadow-lg animate-pulse">
      <div className="max-w-7xl mx-auto px-6 py-4">
        {/* Header with dismiss button */}
        <div className="flex justify-between items-start mb-3">
          <div className="flex items-center gap-2">
            <span className="text-2xl">🔔</span>
            <p className="font-bold text-lg">
              {displayedAlerts.length} HOT LEAD{displayedAlerts.length !== 1 ? 'S' : ''} — replied and need action
            </p>
          </div>
          <button
            onClick={handleDismiss}
            className="text-white hover:text-gray-100 font-bold text-xl"
            title="Dismiss alert"
          >
            ✕
          </button>
        </div>

        {/* Alert items */}
        <div className="space-y-2">
          {displayedAlerts.map((alert) => (
            <div
              key={alert.id}
              className="bg-white bg-opacity-10 rounded-lg p-3 flex justify-between items-center"
            >
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-white truncate">{alert.company_name}</p>
                <p className="text-sm text-gray-100">
                  Est. Savings: {formatCurrency(alert.savings_mid)} •{' '}
                  {alert.reply_summary || 'Replied to your outreach'}
                </p>
              </div>
              <button
                onClick={() => onViewLead(alert.id)}
                className="ml-2 px-3 py-1 bg-white text-red-600 rounded font-bold hover:bg-gray-100 transition flex-shrink-0"
              >
                View Lead
              </button>
            </div>
          ))}
        </div>

        {/* More alerts link */}
        {remainingCount > 0 && (
          <p className="mt-3 text-sm text-gray-100">
            <a href="/leads?status=replied" className="font-bold hover:underline">
              and {remainingCount} more →
            </a>
          </p>
        )}
      </div>
    </div>
  );
}
