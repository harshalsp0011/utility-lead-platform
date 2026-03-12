/**
 * PipelineStageBar Component
 * 
 * Horizontal stage progression bar showing counts at each stage.
 * Click stages to filter leads by status.
 * 
 * Props:
 *   stages (object): Counts per stage {new, enriched, scored, approved, contacted, replied, meeting_booked, won}
 *   pipelineValueFormatted (string): Formatted total pipeline value (e.g., "$2.5M")
 *   troyBanksRevenueFormatted (string): Formatted Troy & Banks revenue estimate
 * 
 * Usage:
 *   <PipelineStageBar
 *     stages={{ new: 45, enriched: 38, ...scored: 28, approved: 15, ... }}
 *     pipelineValueFormatted="$2.5M"
 *     troyBanksRevenueFormatted="$600k"
 *   />
 */

import React from 'react';
import { useNavigate } from 'react-router-dom';

const STAGE_CONFIG = [
  { key: 'new', label: 'New', color: 'bg-gray-300' },
  { key: 'enriched', label: 'Enriched', color: 'bg-blue-300' },
  { key: 'scored', label: 'Scored', color: 'bg-purple-300' },
  { key: 'approved', label: 'Approved', color: 'bg-indigo-400' },
  { key: 'contacted', label: 'Contacted', color: 'bg-yellow-300' },
  { key: 'replied', label: 'Replied', color: 'bg-orange-400' },
  { key: 'meeting_booked', label: 'Meeting', color: 'bg-teal-400' },
  { key: 'won', label: 'Won', color: 'bg-green-500' },
];

export default function PipelineStageBar({
  stages = {},
  pipelineValueFormatted = '$0',
  troyBanksRevenueFormatted = '$0',
}) {
  const navigate = useNavigate();

  const handleStageClick = (stageKey) => {
    navigate(`/leads?status=${stageKey}`);
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      {/* Stage progression boxes */}
      <div className="flex gap-2 mb-6 overflow-x-auto pb-2">
        {STAGE_CONFIG.map((stage, index) => {
          const count = stages[stage.key] || 0;
          return (
            <div key={stage.key} className="flex items-center flex-shrink-0">
              {/* Stage box */}
              <button
                onClick={() => handleStageClick(stage.key)}
                className={`${stage.color} hover:shadow-lg transition rounded-lg p-4 min-w-max cursor-pointer`}
              >
                <p className="text-xs uppercase tracking-widest text-gray-700 font-semibold">
                  {stage.label}
                </p>
                <p className="text-3xl font-bold text-gray-900">{count}</p>
              </button>

              {/* Arrow separator (not on last stage) */}
              {index < STAGE_CONFIG.length - 1 && (
                <div className="flex-shrink-0 px-3 text-gray-400 text-lg">→</div>
              )}
            </div>
          );
        })}
      </div>

      {/* Pipeline value footer */}
      <div className="border-t pt-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm text-gray-600 font-medium">Total Pipeline Value</p>
            <p className="text-2xl font-bold text-green-600">{pipelineValueFormatted}</p>
          </div>
          <div>
            <p className="text-sm text-gray-600 font-medium">Troy & Banks Revenue Est.</p>
            <p className="text-2xl font-bold text-blue-600">{troyBanksRevenueFormatted}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
