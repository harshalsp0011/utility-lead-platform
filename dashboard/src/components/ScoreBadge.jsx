/**
 * ScoreBadge Component
 * 
 * Displays lead score with tier color coding.
 * 
 * Props:
 *   score (number): Lead score 0-100
 *   tier (string): 'high' | 'medium' | 'low'
 *   size (string): 'sm' | 'md' | 'lg' (default: 'md')
 * 
 * Usage:
 *   <ScoreBadge score={87} tier="high" size="lg" />
 */

import React from 'react';

const getTierColor = (tier, size) => {
  const baseClasses = {
    sm: 'px-2 py-1 text-xs',
    md: 'px-3 py-2 text-sm',
    lg: 'px-4 py-3 text-lg',
  }[size] || 'px-3 py-2 text-sm';

  const tierColors = {
    high: 'bg-green-600 text-white',
    medium: 'bg-yellow-500 text-gray-900',
    low: 'bg-gray-400 text-gray-900',
  };

  return `${baseClasses} ${tierColors[tier] || tierColors.low} rounded-full font-bold`;
};

export default function ScoreBadge({ score, tier, size = 'md' }) {
  const tierLabel = {
    high: 'HIGH',
    medium: 'MED',
    low: 'LOW',
  }[tier] || 'N/A';

  const sizeClasses = {
    sm: 'text-sm gap-1',
    md: 'text-base gap-2',
    lg: 'text-lg gap-2',
  }[size] || 'text-base gap-2';

  return (
    <div className={`flex items-center ${sizeClasses}`}>
      <span className={`font-bold ${size === 'lg' ? 'text-2xl' : size === 'md' ? 'text-lg' : 'text-sm'}`}>
        {score}
      </span>
      <span className={getTierColor(tier, size)}>
        {tierLabel}
      </span>
    </div>
  );
}
