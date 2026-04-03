/**
 * Email Review Page
 * 
 * Human approval checkpoint for pending email drafts before sending.
 * Allows reviewers to approve, edit, reject, or regenerate drafts.
 * Supports bulk approval of high-score leads.
 * 
 * Route: /emails/review
 * 
 * Components:
 * - PageHeader: Title, subtitle, pending count badge
 * - PendingCountBanner: Info/success banner based on queue status
 * - BulkApproveSection: Select all, bulk approve with progress
 * - EmailReviewCards: Individual draft review and approval workflow
 * 
 * Usage:
 *   import EmailReview from './pages/EmailReview';
 *   <Route path="/emails/review" element={<EmailReview />} />
 */

import React, { useState, useEffect } from 'react';
import LoadingOverlay from '../components/LoadingOverlay';
import {
  fetchPendingEmails,
  approveEmail,
  rejectEmail,
  regenerateEmail,
  editEmail,
  fetchCrmCompanies,
  saveCompanyContext,
  generateCrmEmail,
} from '../services/api';

// ============================================================================
// UTILITIES
// ============================================================================

/**
 * Format currency
 */
function formatSavings(value) {
  if (!value) return '$0';
  if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(0)}k`;
  return `$${value}`;
}

/**
 * Get tier badge color
 */
function getTierColor(tier) {
  if (tier === 'high') return 'bg-green-100 text-green-800';
  if (tier === 'medium') return 'bg-yellow-100 text-yellow-800';
  return 'bg-gray-100 text-gray-800';
}

/**
 * CriticBadge: shows the AI critic score (e.g. "8/10 ✓" or "5/10 ⚠")
 */
function CriticBadge({ score, rewrites }) {
  if (score == null) return null;
  const passed = score >= 7;
  const color = passed
    ? 'bg-green-100 text-green-800 border-green-200'
    : 'bg-yellow-100 text-yellow-800 border-yellow-200';
  const icon = passed ? '✓' : '⚠';
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-semibold ${color}`}>
      AI {score.toFixed(1)}/10 {icon}
      {rewrites > 0 && <span className="text-xs font-normal opacity-70">({rewrites}x rewrite)</span>}
    </span>
  );
}

// ============================================================================
// SUB-COMPONENTS
// ============================================================================

/**
 * PageHeader: Title and pending count
 */
function PageHeader({ pendingCount }) {
  return (
    <div className="flex justify-between items-start mb-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Email Review Queue</h1>
        <p className="text-gray-600 mt-1">Review and approve emails before sending</p>
      </div>
      <div className="bg-blue-100 text-blue-800 px-4 py-2 rounded-full font-bold">
        {pendingCount} pending
      </div>
    </div>
  );
}

/**
 * PendingCountBanner: Info or success banner
 */
function PendingCountBanner({ pendingCount }) {
  if (pendingCount > 0) {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6 text-blue-900">
        <p className="font-semibold">
          You have <span className="text-lg font-bold">{pendingCount}</span> emails waiting for your review.
        </p>
        <p className="text-sm mt-1">All emails require approval before sending.</p>
      </div>
    );
  }

  return (
    <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-6 text-green-900">
      <p className="font-semibold">✓ All caught up — no emails pending review</p>
    </div>
  );
}

/**
 * BulkApproveSection: Select and approve all high-score leads
 */
function BulkApproveSection({
  emails,
  selectedCount,
  onToggleSelectAll,
  onBulkApprove,
  isApproving,
  approvalProgress,
  approvedCount,
}) {
  const highScoreEmails = emails.filter((e) => e.lead_score >= 80).length;
  const allHighSelected =
    highScoreEmails > 0 &&
    emails.filter((e) => e.lead_score >= 80).every((e) => e.selected);

  return (
    <div className="bg-white rounded-lg shadow p-4 mb-6">
      <div className="flex items-center justify-between gaps-4">
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={allHighSelected}
              onChange={(e) => onToggleSelectAll(e.target.checked)}
              className="w-5 h-5"
            />
            <span className="font-semibold text-gray-700">
              Select all High score leads ({highScoreEmails})
            </span>
          </label>
        </div>

        <div className="flex items-center gap-4">
          {approvalProgress > 0 && approvalProgress < 100 && (
            <div className="flex items-center gap-2">
              <div className="w-32 bg-gray-200 rounded-full h-2">
                <div
                  className="bg-green-600 h-2 rounded-full transition-all"
                  style={{ width: `${approvalProgress}%` }}
                />
              </div>
              <span className="text-xs font-semibold text-gray-600">
                {approvedCount}/{selectedCount}
              </span>
            </div>
          )}

          <button
            onClick={onBulkApprove}
            disabled={selectedCount === 0 || isApproving}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 transition font-semibold"
          >
            {isApproving ? '⏳ Approving...' : '✓ Approve All Selected'}
          </button>
        </div>
      </div>

      {approvedCount > 0 && approvalProgress === 100 && (
        <p className="mt-3 text-sm text-green-700 font-semibold">
          ✓ {approvedCount} of {selectedCount} approved this session
        </p>
      )}
    </div>
  );
}

/**
 * CompanyDraftCard: One card per company. If company has multiple drafts,
 * shows navigation arrows to switch between them. Click header to expand
 * full email view.
 */
function CompanyDraftCard({
  drafts,
  onApprove,
  onReject,
  onRegenerate,
  isLoading,
  onToggleSelect,
  selectedEmails,
}) {
  const [draftIdx, setDraftIdx] = useState(0);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  const email = drafts[draftIdx];
  const [subject, setSubject] = useState(email.subject_line || '');
  const [body, setBody] = useState(email.body || '');
  const hasMultiple = drafts.length > 1;

  // Sync editable fields when navigating between drafts
  const goTo = (idx) => {
    setDraftIdx(idx);
    setSubject(drafts[idx].subject_line || '');
    setBody(drafts[idx].body || '');
    setIsEditing(false);
    setShowRejectForm(false);
    setRejectReason('');
  };

  const handleApprove = async () => {
    if (isEditing) {
      await onApprove(email.id, subject, body);
      setIsEditing(false);
    } else {
      await onApprove(email.id);
    }
  };

  const handleReject = async () => {
    if (!rejectReason.trim()) { alert('Please enter a rejection reason'); return; }
    await onReject(email.id, rejectReason);
  };

  const isSelected = selectedEmails.has(email.id);

  return (
    <div className="bg-white rounded-lg shadow mb-4 overflow-hidden border border-gray-200">

      {/* ── COLLAPSED HEADER (always visible, click to expand) ── */}
      <div
        className="px-5 py-4 cursor-pointer hover:bg-gray-50 transition select-none"
        onClick={() => setIsExpanded(v => !v)}
      >
        <div className="flex items-center gap-3">
          {/* Checkbox — stop propagation so click doesn't toggle expand */}
          <input
            type="checkbox"
            checked={isSelected}
            onChange={(e) => { e.stopPropagation(); onToggleSelect(email.id, e.target.checked); }}
            onClick={(e) => e.stopPropagation()}
            className="w-4 h-4 flex-shrink-0"
          />

          {/* Company + meta */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold text-gray-900 text-base">{email.company_name}</span>
              {hasMultiple && (
                <span className="bg-blue-100 text-blue-700 text-xs font-semibold px-2 py-0.5 rounded-full">
                  {drafts.length} drafts
                </span>
              )}
              {email.low_confidence && (
                <span className="bg-yellow-100 text-yellow-800 text-xs font-semibold px-2 py-0.5 rounded-full">
                  ⚠ Low confidence
                </span>
              )}
              <CriticBadge score={email.critic_score} rewrites={email.rewrite_count || 0} />
            </div>

            {/* Subject preview */}
            <p className="text-sm text-gray-600 mt-0.5 truncate">
              <span className="font-semibold text-gray-500 mr-1">To:</span>
              {email.contact_name || email.contact_email || 'No contact'}{email.contact_title ? ` · ${email.contact_title}` : ''}
              <span className="mx-2 text-gray-300">|</span>
              <span className="font-semibold text-gray-500 mr-1">Subject:</span>
              {email.subject_line}
            </p>
          </div>

          {/* Multi-draft navigation — stop propagation */}
          {hasMultiple && (
            <div className="flex items-center gap-1 flex-shrink-0" onClick={e => e.stopPropagation()}>
              <button
                onClick={() => goTo(Math.max(0, draftIdx - 1))}
                disabled={draftIdx === 0}
                className="w-7 h-7 rounded border border-gray-300 flex items-center justify-center text-gray-500 hover:bg-gray-100 disabled:opacity-30 text-sm"
              >‹</button>
              <span className="text-xs font-semibold text-gray-600 w-10 text-center">
                {draftIdx + 1}/{drafts.length}
              </span>
              <button
                onClick={() => goTo(Math.min(drafts.length - 1, draftIdx + 1))}
                disabled={draftIdx === drafts.length - 1}
                className="w-7 h-7 rounded border border-gray-300 flex items-center justify-center text-gray-500 hover:bg-gray-100 disabled:opacity-30 text-sm"
              >›</button>
            </div>
          )}

          {/* Expand toggle */}
          <span className="text-gray-400 text-lg flex-shrink-0">{isExpanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {/* ── EXPANDED: full email view ── */}
      {isExpanded && (
        <div className="border-t border-gray-200">
          {/* Email client header */}
          <div className="bg-gray-50 px-6 py-4 space-y-2 text-sm border-b border-gray-200">
            <div className="flex gap-3">
              <span className="w-16 text-xs font-semibold text-gray-500 uppercase pt-0.5 flex-shrink-0">From</span>
              <span className="text-gray-700">Your Consulting Firm</span>
            </div>
            <div className="flex gap-3">
              <span className="w-16 text-xs font-semibold text-gray-500 uppercase pt-0.5 flex-shrink-0">To</span>
              <div>
                {email.contact_name
                  ? <span className="font-semibold text-gray-900">{email.contact_name}</span>
                  : <span className="text-gray-500 italic">No contact found</span>
                }
                {email.contact_title && <span className="text-gray-500 ml-1">· {email.contact_title}</span>}
                {email.contact_email && (
                  <span className="ml-2 text-blue-600">&lt;{email.contact_email}&gt;</span>
                )}
              </div>
            </div>
            <div className="flex gap-3">
              <span className="w-16 text-xs font-semibold text-gray-500 uppercase pt-0.5 flex-shrink-0">Subject</span>
              {isEditing ? (
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  className="flex-1 px-2 py-0.5 border border-blue-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              ) : (
                <span className="font-semibold text-gray-900">{subject}</span>
              )}
            </div>
            {email.savings_estimate && (
              <div className="flex gap-3">
                <span className="w-16 text-xs font-semibold text-gray-500 uppercase pt-0.5 flex-shrink-0">Savings</span>
                <span className="text-green-700 font-semibold">{email.savings_estimate}</span>
              </div>
            )}
            {email.template_used && (
              <div className="flex gap-3">
                <span className="w-16 text-xs font-semibold text-gray-500 uppercase pt-0.5 flex-shrink-0">Angle</span>
                <span className="text-gray-500 text-xs bg-gray-200 rounded px-1.5 py-0.5">{email.template_used}</span>
              </div>
            )}
          </div>

          {/* Email body */}
          <div className="px-6 py-5">
            {isEditing ? (
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={12}
                className="w-full px-3 py-2 border border-blue-300 rounded text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 leading-relaxed"
              />
            ) : (
              <div className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed font-sans">
                {body}
              </div>
            )}
          </div>

          {/* Rejection form */}
          {showRejectForm && (
            <div className="mx-6 mb-4 bg-red-50 border border-red-200 rounded-lg p-4">
              <label className="block text-sm font-semibold text-gray-700 mb-2">Rejection Reason</label>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-red-500 text-sm"
                placeholder="Why are you rejecting this draft?"
              />
            </div>
          )}

          {/* Action buttons */}
          <div className="px-6 pb-5 flex gap-2 flex-wrap border-t border-gray-100 pt-4">
            {!showRejectForm ? (
              <>
                <button
                  onClick={handleApprove}
                  disabled={isLoading}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 transition font-semibold text-sm"
                >
                  {isEditing ? '✓ Save & Send' : '✓ Approve & Send'}
                </button>
                <button
                  onClick={() => setIsEditing(v => !v)}
                  disabled={isLoading}
                  className={`px-4 py-2 rounded-lg transition font-semibold text-sm ${isEditing ? 'bg-gray-200 text-gray-700 hover:bg-gray-300' : 'bg-blue-600 text-white hover:bg-blue-700'}`}
                >
                  {isEditing ? 'Cancel Edit' : '✎ Edit'}
                </button>
                <button
                  onClick={() => setShowRejectForm(true)}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition font-semibold text-sm"
                >
                  ✗ Reject
                </button>
                <button
                  onClick={() => onRegenerate(email.id)}
                  disabled={isLoading}
                  className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:bg-gray-400 transition font-semibold text-sm"
                >
                  ↻ Regenerate
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={handleReject}
                  disabled={isLoading}
                  className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:bg-gray-400 transition font-semibold text-sm"
                >
                  {isLoading ? '...' : 'Confirm Reject'}
                </button>
                <button
                  onClick={() => { setShowRejectForm(false); setRejectReason(''); }}
                  className="px-4 py-2 bg-gray-300 text-gray-800 rounded-lg hover:bg-gray-400 transition font-semibold text-sm"
                >
                  Cancel
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// CRM TAB COMPONENTS
// ============================================================================

/**
/**
 * SendConfirmDialog: shows exactly where the email is going before sending.
 */
function SendConfirmDialog({ toEmail, toName, fromEmail, subject, onConfirm, onCancel }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-bold text-gray-900 mb-3">Confirm Send</h2>
        <div className="space-y-2 text-sm mb-5">
          <div className="flex gap-2">
            <span className="w-14 text-xs font-semibold text-gray-500 uppercase pt-0.5 flex-shrink-0">To</span>
            <div>
              <p className="font-semibold text-gray-900">{toName || toEmail}</p>
              {toName && <p className="text-blue-600 text-xs">{toEmail}</p>}
            </div>
          </div>
          <div className="flex gap-2">
            <span className="w-14 text-xs font-semibold text-gray-500 uppercase flex-shrink-0">From</span>
            <span className="text-gray-700">{fromEmail || 'UBinterns@troybanks.com'}</span>
          </div>
          <div className="flex gap-2">
            <span className="w-14 text-xs font-semibold text-gray-500 uppercase flex-shrink-0">Subject</span>
            <span className="text-gray-800 font-medium">{subject}</span>
          </div>
        </div>
        <div className="flex gap-3 justify-end">
          <button onClick={onCancel} className="px-4 py-2 rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200 transition font-semibold text-sm">
            Cancel
          </button>
          <button onClick={onConfirm} className="px-4 py-2 rounded-lg bg-green-600 text-white hover:bg-green-700 transition font-semibold text-sm">
            ✓ Send Now
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * RegenerateDialog: modal asking the user what to change before regenerating.
 * Feedback is optional — leaving it blank triggers a fresh write.
 */
function RegenerateDialog({ onConfirm, onCancel }) {
  const [feedback, setFeedback] = useState('');
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-bold text-gray-900 mb-1">Regenerate Email</h2>
        <p className="text-sm text-gray-500 mb-4">
          What should change? Leave blank to generate a completely fresh draft.
        </p>
        <textarea
          autoFocus
          value={feedback}
          onChange={e => setFeedback(e.target.value)}
          rows={4}
          placeholder="e.g. Make the tone more casual, shorten the email, lead with the audit offer instead of savings..."
          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
        />
        <div className="flex gap-3 mt-4 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-lg bg-gray-100 text-gray-700 hover:bg-gray-200 transition font-semibold text-sm"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(feedback.trim())}
            className="px-4 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 transition font-semibold text-sm"
          >
            ↻ Regenerate
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * CrmDraftView: shows a generated draft inline with Edit + Send actions.
 */
function CrmDraftView({ draft, onSend, onRegenerate, isLoading, contact }) {
  const [isEditing, setIsEditing] = useState(false);
  const [subject, setSubject] = useState(draft.subject_line || '');
  const [body, setBody] = useState(draft.body || '');
  const [showRegenerateDialog, setShowRegenerateDialog] = useState(false);
  const [showSendConfirm, setShowSendConfirm] = useState(false);

  const handleSendConfirmed = async () => {
    setShowSendConfirm(false);
    if (isEditing) {
      await onSend(draft.id, subject, body);
    } else {
      await onSend(draft.id);
    }
    setIsEditing(false);
  };

  const handleRegenerateConfirm = (feedback) => {
    setShowRegenerateDialog(false);
    onRegenerate(draft.id, feedback);
  };

  return (
    <>
      {showSendConfirm && (
        <SendConfirmDialog
          toEmail={contact?.email || ''}
          toName={contact?.full_name || ''}
          fromEmail="UBinterns@troybanks.com"
          subject={isEditing ? subject : draft.subject_line}
          onConfirm={handleSendConfirmed}
          onCancel={() => setShowSendConfirm(false)}
        />
      )}
      {showRegenerateDialog && (
        <RegenerateDialog
          onConfirm={handleRegenerateConfirm}
          onCancel={() => setShowRegenerateDialog(false)}
        />
      )}

      <div className="mt-4 border border-gray-200 rounded-lg overflow-hidden">
        {/* Draft header */}
        <div className="bg-gray-50 px-4 py-3 border-b border-gray-200 space-y-1.5 text-sm">
          <div className="flex gap-3 items-center">
            <span className="w-16 text-xs font-semibold text-gray-500 uppercase flex-shrink-0">Subject</span>
            {isEditing ? (
              <input
                type="text"
                value={subject}
                onChange={e => setSubject(e.target.value)}
                className="flex-1 px-2 py-0.5 border border-blue-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            ) : (
              <span className="font-semibold text-gray-900">{subject}</span>
            )}
          </div>
          {draft.savings_estimate && (
            <div className="flex gap-3">
              <span className="w-16 text-xs font-semibold text-gray-500 uppercase flex-shrink-0">Savings</span>
              <span className="text-green-700 font-semibold">{draft.savings_estimate}</span>
            </div>
          )}
          {draft.template_used && (
            <div className="flex gap-3">
              <span className="w-16 text-xs font-semibold text-gray-500 uppercase flex-shrink-0">Angle</span>
              <span className="text-xs bg-gray-200 text-gray-600 rounded px-1.5 py-0.5">{draft.template_used}</span>
            </div>
          )}
        </div>

        {/* Body */}
        <div className="px-4 py-4">
          {isEditing ? (
            <textarea
              value={body}
              onChange={e => setBody(e.target.value)}
              rows={10}
              className="w-full px-3 py-2 border border-blue-300 rounded text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 leading-relaxed"
            />
          ) : (
            <div className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">{body}</div>
          )}
        </div>

        {/* Actions */}
        <div className="px-4 pb-4 flex gap-2 flex-wrap border-t border-gray-100 pt-3">
          <button
            onClick={() => setShowSendConfirm(true)}
            disabled={isLoading}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 transition font-semibold text-sm"
          >
            {isEditing ? '✓ Save & Send' : '✓ Send'}
          </button>
          <button
            onClick={() => setIsEditing(v => !v)}
            disabled={isLoading}
            className={`px-4 py-2 rounded-lg transition font-semibold text-sm ${isEditing ? 'bg-gray-200 text-gray-700 hover:bg-gray-300' : 'bg-blue-600 text-white hover:bg-blue-700'}`}
          >
            {isEditing ? 'Cancel' : '✎ Edit'}
          </button>
          <button
            onClick={() => setShowRegenerateDialog(true)}
            disabled={isLoading}
            className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 disabled:bg-gray-400 transition font-semibold text-sm"
          >
            ↻ Regenerate
          </button>
        </div>
      </div>
    </>
  );
}

/**
 * CrmCompanyCard: one card per CRM company.
 * Shows company info, contact, context notes input, and draft section.
 */
function CrmCompanyCard({ company, onSend, onRegenerate }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [notesRaw, setNotesRaw] = useState(company.context_notes_raw || '');
  const [notesFormatted, setNotesFormatted] = useState(company.context_notes_formatted || '');
  const [draft, setDraft] = useState(company.latest_draft || null);
  const [isSavingContext, setIsSavingContext] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [contextSaved, setContextSaved] = useState(!!company.context_notes_raw);
  const [error, setError] = useState(null);

  const handleSaveContext = async () => {
    if (!notesRaw.trim()) return;
    setIsSavingContext(true);
    setError(null);
    try {
      const result = await saveCompanyContext(company.company_id, notesRaw, 'user');
      setNotesFormatted(result.notes_formatted || notesRaw);
      setContextSaved(true);
    } catch (err) {
      setError('Failed to save context. Try again.');
    } finally {
      setIsSavingContext(false);
    }
  };

  const handleGenerate = async () => {
    setIsGenerating(true);
    setError(null);
    try {
      const newDraft = await generateCrmEmail(company.company_id, 'user');
      setDraft(newDraft);
    } catch (err) {
      setError('Failed to generate email. Try again.');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSend = async (draftId, newSubject, newBody) => {
    setIsSending(true);
    setError(null);
    try {
      if (newSubject || newBody) {
        await editEmail(draftId, 'user', newSubject, newBody);
      }
      const result = await approveEmail(draftId, 'user');
      if (result?.sent) {
        // Email actually delivered by SendGrid
        setDraft(prev => ({ ...prev, approved_human: true, approved_at: new Date().toISOString() }));
      } else {
        // Approved in DB but SendGrid rejected (bad key, unsubscribed, daily limit, etc.)
        const reason = result?.message || 'Send failed — check SendGrid config.';
        setError(reason);
      }
    } catch (err) {
      setError('Failed to send. Try again.');
    } finally {
      setIsSending(false);
    }
  };

  const handleRegenerate = async (draftId, feedback) => {
    setIsGenerating(true);
    setError(null);
    try {
      const newDraft = await generateCrmEmail(company.company_id, 'user', feedback || null);
      setDraft(newDraft);
    } catch (err) {
      setError('Failed to regenerate. Try again.');
    } finally {
      setIsGenerating(false);
    }
  };

  const isSent = draft?.approved_human === true && draft?.approved_at;

  return (
    <div className="bg-white rounded-lg shadow mb-4 border border-gray-200 overflow-hidden">
      {/* Collapsed header */}
      <div
        className="px-5 py-4 cursor-pointer hover:bg-gray-50 transition select-none"
        onClick={() => setIsExpanded(v => !v)}
      >
        <div className="flex items-center gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold text-gray-900 text-base">{company.name}</span>
              <span className="bg-purple-100 text-purple-700 text-xs font-semibold px-2 py-0.5 rounded-full">CRM Lead</span>
              {isSent && <span className="bg-green-100 text-green-700 text-xs font-semibold px-2 py-0.5 rounded-full">✓ Sent</span>}
              {draft && !isSent && <span className="bg-blue-100 text-blue-700 text-xs font-semibold px-2 py-0.5 rounded-full">Draft Ready</span>}
              {draft?.low_confidence && <span className="bg-yellow-100 text-yellow-800 text-xs font-semibold px-2 py-0.5 rounded-full">⚠ Low confidence</span>}
            </div>
            <p className="text-sm text-gray-500 mt-0.5">
              {company.industry} · {company.city}, {company.state}
              {company.contact && <span className="ml-2">· {company.contact.full_name}{company.contact.title ? `, ${company.contact.title}` : ''}</span>}
            </p>
          </div>
          <span className="text-gray-400 text-lg flex-shrink-0">{isExpanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="border-t border-gray-200 px-5 py-5 space-y-5">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2 rounded-lg">{error}</div>
          )}

          {/* Company + Contact info */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Company</p>
              <p className="font-semibold text-gray-900">{company.name}</p>
              <p className="text-gray-600">{company.industry}</p>
              <p className="text-gray-600">{company.city}, {company.state}</p>
              {company.employee_count && <p className="text-gray-500">{company.employee_count} employees</p>}
              {company.site_count && <p className="text-gray-500">{company.site_count} site(s)</p>}
            </div>
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase mb-1">Contact</p>
              {company.contact ? (
                <>
                  <p className="font-semibold text-gray-900">{company.contact.full_name}</p>
                  <p className="text-gray-600">{company.contact.title}</p>
                  <p className="text-blue-600 text-xs">{company.contact.email}</p>
                </>
              ) : (
                <p className="text-gray-400 italic text-sm">No contact — add manually before sending</p>
              )}
            </div>
          </div>

          {/* Context notes */}
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Meeting Context</p>
            <textarea
              value={notesRaw}
              onChange={e => { setNotesRaw(e.target.value); setContextSaved(false); }}
              rows={4}
              placeholder="What did you discuss? Pain points, number of sites, interest in audit, anything they mentioned about their utility costs..."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            />
            <div className="flex items-center gap-3 mt-2">
              <button
                onClick={handleSaveContext}
                disabled={isSavingContext || !notesRaw.trim()}
                className="px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 transition text-sm font-semibold"
              >
                {isSavingContext ? '⏳ Formatting...' : contextSaved ? '✓ Saved & Formatted' : '💾 Save & Format'}
              </button>
              {contextSaved && <span className="text-xs text-gray-500">LLM formatted ✓</span>}
            </div>

            {/* Formatted bullet points */}
            {notesFormatted && contextSaved && (
              <div className="mt-3 bg-blue-50 border border-blue-100 rounded-lg px-4 py-3">
                <p className="text-xs font-semibold text-blue-700 mb-1.5">Formatted signals (used by writer)</p>
                <div className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{notesFormatted}</div>
              </div>
            )}
          </div>

          {/* Draft section */}
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase mb-2">Email Draft</p>

            {/* Prominent loading state */}
            {isGenerating && (
              <div className="bg-indigo-50 border border-indigo-200 rounded-lg px-4 py-5 flex items-center gap-4">
                <div className="w-6 h-6 border-3 border-indigo-600 border-t-transparent rounded-full animate-spin flex-shrink-0" style={{borderWidth: '3px'}} />
                <div>
                  <p className="text-indigo-800 font-semibold text-sm">Writing email with AI…</p>
                  <p className="text-indigo-600 text-xs mt-0.5">Running Writer → Critic loop · may take up to 60 s</p>
                </div>
              </div>
            )}

            {!isGenerating && draft ? (
              isSent ? (
                <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-3">
                  <div className="flex items-center justify-between flex-wrap gap-3">
                    <div>
                      <p className="text-green-800 font-semibold text-sm">✓ Email sent</p>
                      <p className="text-green-600 text-xs mt-0.5">
                        To: {company.contact?.email || 'unknown'} · {new Date(draft.approved_at).toLocaleString()}
                      </p>
                    </div>
                    <button
                      onClick={() => setDraft(prev => ({ ...prev, approved_at: null }))}
                      className="px-3 py-1.5 text-xs font-semibold bg-white border border-green-300 text-green-700 rounded-lg hover:bg-green-50 transition"
                    >
                      ↻ Resend
                    </button>
                  </div>
                </div>
              ) : (
                <CrmDraftView
                  draft={draft}
                  onSend={handleSend}
                  onRegenerate={handleRegenerate}
                  isLoading={isSending}
                  contact={company.contact}
                />
              )
            ) : null}

            {!isGenerating && !draft && (
              <div className="space-y-2">
                <button
                  onClick={handleGenerate}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 active:bg-indigo-800 transition font-semibold text-sm"
                >
                  ✨ Generate Email
                </button>
                {!contextSaved && (
                  <p className="text-xs text-yellow-600">⚠ No context saved — email will be generic</p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * CrmLeadsTab: lists all CRM companies with context + draft workflow.
 */
function CrmLeadsTab() {
  const [companies, setCompanies] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const load = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await fetchCrmCompanies();
        setCompanies(data.companies || []);
      } catch (err) {
        setError('Failed to load CRM companies. Check API connection.');
      } finally {
        setIsLoading(false);
      }
    };
    load();
  }, []);

  if (isLoading) {
    return <div className="text-center py-12 text-gray-500">Loading CRM leads...</div>;
  }

  if (error) {
    return <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded-lg">{error}</div>;
  }

  if (companies.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-12 text-center">
        <p className="text-gray-500 text-lg">No CRM leads found</p>
        <p className="text-gray-400 text-sm mt-1">Companies with <code className="bg-gray-100 px-1 rounded">data_origin = hubspot_crm</code> will appear here</p>
      </div>
    );
  }

  return (
    <div>
      <div className="bg-purple-50 border border-purple-200 rounded-lg p-4 mb-6 text-purple-900">
        <p className="font-semibold">
          <span className="text-lg font-bold">{companies.length}</span> CRM lead{companies.length !== 1 ? 's' : ''} — add meeting context and generate a personalised email for each.
        </p>
        <p className="text-sm mt-1">Drafts are pre-approved. Click Send when ready — no separate approval step needed.</p>
      </div>
      {companies.map(company => (
        <CrmCompanyCard
          key={company.company_id}
          company={company}
        />
      ))}
    </div>
  );
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

/**
 * EmailReview: Email approval queue page
 */
export default function EmailReview() {
  // 'pipeline' | 'crm'
  const [activeTab, setActiveTab] = useState('pipeline');

  const [emails, setEmails] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isApproving, setIsApproving] = useState(false);
  const [error, setError] = useState(null);
  const [selectedEmails, setSelectedEmails] = useState(new Set());
  const [approvalProgress, setApprovalProgress] = useState(0);
  const [approvedCount, setApprovedCount] = useState(0);
  // 'all' | 'named' | 'generic'
  const [contactFilter, setContactFilter] = useState('all');

  /**
   * Load pending emails
   */
  const loadPendingEmails = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetchPendingEmails();
      const emailsWithSelected = (response.drafts || []).map((email) => ({
        ...email,
        selected: false,
      }));
      setEmails(emailsWithSelected);
      setSelectedEmails(new Set());
      setApprovedCount(0);
      setApprovalProgress(0);
    } catch (err) {
      console.error('Failed to load pending emails:', err);
      setError('Failed to load emails. Check API connection.');
    } finally {
      setIsLoading(false);
    }
  };

  /**
   * Load on mount
   */
  useEffect(() => {
    loadPendingEmails();
  }, []);

  /**
   * Toggle all high-score leads
   */
  const handleToggleSelectAll = (checked) => {
    const highScoreEmails = emails.filter((e) => e.lead_score >= 80);
    if (checked) {
      const newSelected = new Set([...selectedEmails]);
      highScoreEmails.forEach((email) => newSelected.add(email.id));
      setSelectedEmails(newSelected);
    } else {
      const newSelected = new Set([...selectedEmails]);
      highScoreEmails.forEach((email) => newSelected.delete(email.id));
      setSelectedEmails(newSelected);
    }
  };

  /**
   * Toggle individual email selection
   */
  const handleToggleSelect = (emailId, checked) => {
    const newSelected = new Set([...selectedEmails]);
    if (checked) {
      newSelected.add(emailId);
    } else {
      newSelected.delete(emailId);
    }
    setSelectedEmails(newSelected);
  };

  /**
   * Bulk approve selected emails
   */
  const handleBulkApprove = async () => {
    if (selectedEmails.size === 0) return;

    setIsApproving(true);
    setApprovalProgress(0);
    let approved = 0;

    const selectedArray = Array.from(selectedEmails);
    try {
      for (let i = 0; i < selectedArray.length; i++) {
        const draftId = selectedArray[i];
        try {
          await approveEmail(draftId, 'bulk_approval');
          approved++;
        } catch (err) {
          console.error(`Failed to approve email ${draftId}:`, err);
        }
        setApprovalProgress(Math.round(((i + 1) / selectedArray.length) * 100));
      }

      setApprovedCount(approved);
      // Reload after all approvals
      setTimeout(() => loadPendingEmails(), 500);
    } catch (err) {
      console.error('Bulk approve failed:', err);
      setError('Some emails failed to approve. Try again.');
    } finally {
      setIsApproving(false);
    }
  };

  /**
   * Approve single email
   */
  const handleApproveEmail = async (draftId, newSubject, newBody) => {
    try {
      // If edited, save edits first
      if (newSubject || newBody) {
        await editEmail(draftId, 'user', newSubject, newBody);
      }
      await approveEmail(draftId, 'user');
      setEmails(emails.filter((e) => e.id !== draftId));
      setSelectedEmails(
        new Set([...selectedEmails].filter((id) => id !== draftId))
      );
    } catch (err) {
      console.error('Approve failed:', err);
      setError('Failed to approve email. Try again.');
    }
  };

  /**
   * Reject email
   */
  const handleRejectEmail = async (draftId, reason) => {
    try {
      await rejectEmail(draftId, 'user', reason);
      setEmails(emails.filter((e) => e.id !== draftId));
      setSelectedEmails(
        new Set([...selectedEmails].filter((id) => id !== draftId))
      );
    } catch (err) {
      console.error('Reject failed:', err);
      setError('Failed to reject email. Try again.');
    }
  };

  /**
   * Regenerate email
   */
  const handleRegenerate = async (draftId) => {
    try {
      const newDraft = await regenerateEmail(draftId);
      setEmails(
        emails.map((e) =>
          e.id === draftId
            ? { ...newDraft, selected: e.selected }
            : e
        )
      );
    } catch (err) {
      console.error('Regenerate failed:', err);
      setError('Failed to regenerate email. Try again.');
    }
  };

  if (isLoading) {
    return (
      <div className="h-full overflow-y-auto bg-gray-50 p-6">
        <div className="max-w-6xl mx-auto text-center py-12">
          <p className="text-gray-500">Loading emails...</p>
        </div>
      </div>
    );
  }

  const emailsWithSelected = emails.map((e) => ({
    ...e,
    selected: selectedEmails.has(e.id),
  }));

  const namedCount = emails.filter(e => e.contact_name && e.contact_name.trim()).length;
  const genericCount = emails.filter(e => !e.contact_name || !e.contact_name.trim()).length;

  const filteredEmails = emailsWithSelected.filter(e => {
    if (contactFilter === 'named') return e.contact_name && e.contact_name.trim();
    if (contactFilter === 'generic') return !e.contact_name || !e.contact_name.trim();
    return true;
  });

  return (
    <div className="h-full overflow-y-auto bg-gray-50 p-6">
      {isLoading && activeTab === 'pipeline' && <LoadingOverlay message="Loading emails..." />}
      <div className="max-w-6xl mx-auto">
        <PageHeader pendingCount={emails.length} />

        {/* Tab switcher */}
        <div className="flex gap-1 mb-6 bg-white rounded-lg shadow p-1 w-fit">
          {[
            { key: 'pipeline', label: '📋 Pipeline Queue', count: emails.length },
            { key: 'crm',      label: '🏢 CRM Leads' },
          ].map(({ key, label, count }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`px-5 py-2 rounded-md text-sm font-semibold transition ${
                activeTab === key
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {label}
              {count !== undefined && (
                <span className={`ml-2 px-1.5 py-0.5 rounded-full text-xs font-bold ${
                  activeTab === key ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-600'
                }`}>
                  {count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* CRM tab */}
        {activeTab === 'crm' && <CrmLeadsTab />}

        {/* Pipeline tab — all existing content unchanged */}
        {activeTab === 'pipeline' && (<>

        {error && (
          <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded-lg mb-6">
            {error}
          </div>
        )}

        <PendingCountBanner pendingCount={emails.length} />

        {/* Contact filter bar */}
        {emails.length > 0 && (
          <div className="flex items-center gap-2 mb-4">
            <span className="text-sm font-semibold text-gray-500 mr-1">Contact:</span>
            {[
              { key: 'all', label: `All (${emails.length})` },
              { key: 'named', label: `Named Contact (${namedCount})` },
              { key: 'generic', label: `Generic / Assumed (${genericCount})` },
            ].map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setContactFilter(key)}
                className={`px-3 py-1.5 rounded-full text-sm font-semibold border transition ${
                  contactFilter === key
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white text-gray-600 border-gray-300 hover:border-blue-400 hover:text-blue-600'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        {emails.length > 0 && (
          <BulkApproveSection
            emails={emailsWithSelected}
            selectedCount={selectedEmails.size}
            onToggleSelectAll={handleToggleSelectAll}
            onBulkApprove={handleBulkApprove}
            isApproving={isApproving}
            approvalProgress={approvalProgress}
            approvedCount={approvedCount}
          />
        )}

        {filteredEmails.length > 0 ? (
          <div>
            {/* Group drafts by company_id — multi-contact companies get one card with navigation */}
            {Object.values(
              filteredEmails.reduce((groups, email) => {
                const key = email.company_id;
                if (!groups[key]) groups[key] = [];
                groups[key].push(email);
                return groups;
              }, {})
            ).map((drafts) => (
              <CompanyDraftCard
                key={drafts[0].company_id}
                drafts={drafts}
                onApprove={handleApproveEmail}
                onReject={handleRejectEmail}
                onRegenerate={handleRegenerate}
                isLoading={isApproving}
                onToggleSelect={handleToggleSelect}
                selectedEmails={selectedEmails}
              />
            ))}
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow p-12 text-center">
            <p className="text-gray-500 text-lg">
              {contactFilter !== 'all'
                ? `No ${contactFilter === 'named' ? 'named contact' : 'generic'} drafts in queue`
                : '✓ All caught up — no emails pending review'}
            </p>
          </div>
        )}
        </>)}
      </div>
    </div>
  );
}
