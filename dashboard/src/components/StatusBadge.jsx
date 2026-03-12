/**
 * StatusBadge Component
 * 
 * Displays lead status with color coding.
 * 
 * Props:
 *   status (string): 'new' | 'enriched' | 'scored' | 'approved' | 'contacted' |
 *                    'replied' | 'meeting_booked' | 'won' | 'lost' | 
 *                    'no_response' | 'archived'
 * 
 * Usage:
 *   <StatusBadge status="replied" />
 */

import React from 'react';

const getStatusColor = (status) => {
  const statusColors = {
    new: 'bg-gray-100 text-gray-800',
    enriched: 'bg-gray-100 text-gray-800',
    scored: 'bg-purple-100 text-purple-800',
    approved: 'bg-blue-100 text-blue-800',
    contacted: 'bg-yellow-100 text-yellow-800',
    replied: 'bg-orange-100 text-orange-800',
    meeting_booked: 'bg-teal-100 text-teal-800',
    won: 'bg-green-100 text-green-800',
    lost: 'bg-red-100 text-red-800',
    no_response: 'bg-gray-100 text-gray-800',
    archived: 'bg-gray-700 text-gray-100',
  };

  return statusColors[status] || 'bg-gray-100 text-gray-800';
};

const getStatusLabel = (status) => {
  const labels = {
    new: 'New',
    enriched: 'Enriched',
    scored: 'Scored',
    approved: 'Approved',
    contacted: 'Contacted',
    replied: 'Replied',
    meeting_booked: 'Meeting Booked',
    won: 'Won',
    lost: 'Lost',
    no_response: 'No Response',
    archived: 'Archived',
  };

  return labels[status] || status;
};

export default function StatusBadge({ status }) {
  return (
    <span
      className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${getStatusColor(
        status
      )}`}
    >
      {getStatusLabel(status)}
    </span>
  );
}
