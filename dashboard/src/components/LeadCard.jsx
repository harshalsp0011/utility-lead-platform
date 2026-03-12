/**
 * LeadCard Component
 * 
 * Displays a single lead company with all key information and action buttons.
 * 
 * Props:
 *   company (object): Company data with id, name, industry, state, site_count, etc.
 *   features (object): Spend/savings data
 *   score (object): Score data with score, tier, score_reason
 *   contact (object): Contact data with name, title, email (optional)
 *   onApprove (function): Callback on approve
 *   onReject (function): Callback on reject
 *   onViewDetail (function): Callback on view detail
 * 
 * Usage:
 *   <LeadCard
 *     company={companyData}
 *     features={featuresData}
 *     score={scoreData}
 *     contact={contactData}
 *     onApprove={() => handleApprove()}
 *     onReject={() => handleReject()}
 *     onViewDetail={() => handleViewDetail()}
 *   />
 */

import React from 'react';
import ScoreBadge from './ScoreBadge';
import StatusBadge from './StatusBadge';

function formatCurrency(value) {
  if (!value) return '$0';
  if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(0)}k`;
  return `$${value}`;
}

export default function LeadCard({
  company,
  features,
  score,
  contact,
  onApprove,
  onReject,
  onViewDetail,
}) {
  if (!company) return null;

  const revenueEstimate = features?.savings_mid ? Math.round(features.savings_mid * 0.24) : 0;

  return (
    <div className="bg-white rounded-lg shadow hover:shadow-lg transition p-6 mb-4">
      {/* Top row: Name, industry, badges */}
      <div className="flex justify-between items-start gap-4 mb-4 pb-4 border-b">
        <div className="flex-1">
          <h3 className="text-2xl font-bold text-gray-900 mb-2">{company.name}</h3>
          <div className="flex gap-2 items-center flex-wrap">
            <span className="px-3 py-1 bg-blue-100 text-blue-800 rounded text-sm font-semibold">
              {company.industry}
            </span>
            {company.state && (
              <span className="text-gray-600">📍 {company.state}</span>
            )}
          </div>
        </div>

        <div className="flex flex-col items-end gap-2">
          <ScoreBadge score={score?.score || 0} tier={score?.tier || 'low'} size="lg" />
          <StatusBadge status={company.status || 'new'} />
        </div>
      </div>

      {/* Middle row: Company, Financial, Contact info */}
      <div className="grid md:grid-cols-3 gap-6 mb-6 pb-6 border-b">
        {/* Column 1: Company info */}
        <div>
          <h4 className="font-bold text-gray-900 mb-3">Company</h4>
          <div className="space-y-2 text-sm">
            <div>
              <p className="text-gray-600">Locations</p>
              <p className="font-semibold text-gray-900">
                {company.site_count || 0} sites
              </p>
            </div>
            <div>
              <p className="text-gray-600">Employees</p>
              <p className="font-semibold text-gray-900">
                {company.employee_count || 'N/A'} approx
              </p>
            </div>
            {company.website && (
              <div>
                <p className="text-gray-600">Website</p>
                <a
                  href={company.website}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:underline font-semibold"
                >
                  Visit →
                </a>
              </div>
            )}
          </div>
        </div>

        {/* Column 2: Financial estimates */}
        <div>
          <h4 className="font-bold text-gray-900 mb-3">Financial</h4>
          <div className="space-y-2 text-sm">
            <div>
              <p className="text-gray-600">Annual Spend</p>
              <p className="font-semibold text-gray-900">
                {formatCurrency(features?.total_spend)}
              </p>
            </div>
            <div>
              <p className="text-gray-600">Savings Range</p>
              <p className="font-semibold text-gray-900">
                {formatCurrency(features?.savings_low)} – {formatCurrency(features?.savings_high)}
              </p>
            </div>
            <div>
              <p className="text-gray-600">TB Revenue Est.</p>
              <p className="font-semibold text-green-700">
                {formatCurrency(revenueEstimate)}
              </p>
            </div>
          </div>
        </div>

        {/* Column 3: Contact info */}
        <div>
          <h4 className="font-bold text-gray-900 mb-3">Contact</h4>
          {contact ? (
            <div className="space-y-2 text-sm">
              <div>
                <p className="font-semibold text-gray-900">✓ {contact.name}</p>
                <p className="text-gray-600">{contact.title}</p>
              </div>
              <div>
                <p className="text-gray-600 mb-1">Email</p>
                <div className="flex items-center gap-2">
                  <a
                    href={`mailto:${contact.email}`}
                    className="text-blue-600 hover:underline text-xs truncate"
                  >
                    {contact.email}
                  </a>
                  <button
                    onClick={() => navigator.clipboard.writeText(contact.email)}
                    className="text-gray-500 hover:text-gray-700"
                    title="Copy email"
                  >
                    📋
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-500">✗ No contact found yet</p>
          )}
        </div>
      </div>

      {/* Bottom row: Action buttons */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => onViewDetail(company.id)}
          className="px-4 py-2 bg-gray-200 text-gray-800 rounded-lg hover:bg-gray-300 transition font-semibold text-sm"
        >
          View Detail
        </button>

        {score?.tier === 'high' && company.status !== 'approved' && (
          <button
            onClick={() => onApprove(company.id)}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition font-semibold text-sm"
          >
            ✓ Approve
          </button>
        )}

        {company.status !== 'rejected' && (
          <button
            onClick={() => onReject(company.id)}
            className="px-4 py-2 border border-red-600 text-red-600 rounded-lg hover:bg-red-50 transition font-semibold text-sm"
          >
            ✗ Reject
          </button>
        )}
      </div>
    </div>
  );
}
