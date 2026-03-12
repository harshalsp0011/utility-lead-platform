/**
 * ApprovalModal Component
 * 
 * Modal for reviewing and approving email drafts with inline editing.
 * 
 * Props:
 *   draft (object): Email draft with subject_line, body, tone_warnings
 *   company (object): Company data
 *   contact (object): Contact data
 *   isOpen (boolean): Show/hide modal
 *   onClose (function): Close modal callback
 *   onApprove (function): Approve callback
 *   onReject (function): Reject callback
 *   onRegenerate (function): Regenerate callback
 * 
 * Usage:
 *   <ApprovalModal
 *     draft={draftData}
 *     company={companyData}
 *     contact={contactData}
 *     isOpen={isOpen}
 *     onClose={handleClose}
 *     onApprove={handleApprove}
 *     onReject={handleReject}
 *     onRegenerate={handleRegenerate}
 *   />
 */

import React, { useState } from 'react';

function formatCurrency(value) {
  if (!value) return '$0';
  if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(0)}k`;
  return `$${value}`;
}

function countWords(text) {
  return (text || '').trim().split(/\s+/).filter(w => w.length > 0).length;
}

export default function ApprovalModal({
  draft,
  company,
  contact,
  isOpen,
  onClose,
  onApprove,
  onReject,
  onRegenerate,
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [subject, setSubject] = useState(draft?.subject_line || '');
  const [body, setBody] = useState(draft?.body || '');
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen || !draft) return null;

  const hasEdits = subject !== (draft?.subject_line || '') || body !== (draft?.body || '');
  const wordCount = countWords(body);
  const wordCountExceeded = wordCount > 250;

  const handleApprove = async () => {
    setIsSubmitting(true);
    try {
      await onApprove();
      setIsEditing(false);
      setShowRejectForm(false);
      onClose();
    } catch (err) {
      console.error('Approve failed:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!rejectReason.trim()) {
      alert('Please enter a rejection reason');
      return;
    }
    setIsSubmitting(true);
    try {
      await onReject(rejectReason);
      setShowRejectForm(false);
      onClose();
    } catch (err) {
      console.error('Reject failed:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRegenerate = async () => {
    setIsSubmitting(true);
    try {
      await onRegenerate();
      setIsEditing(false);
      setSubject(draft?.subject_line || '');
      setBody(draft?.body || '');
    } catch (err) {
      console.error('Regenerate failed:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-auto">
        {/* Header */}
        <div className="flex justify-between items-center mb-4 pb-4 border-b">
          <h2 className="text-xl font-bold text-gray-900">
            Review Email — {company?.name}
          </h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-800 text-2xl"
          >
            ✕
          </button>
        </div>

        {/* Recipient section */}
        <div className="mb-4 p-3 bg-gray-50 rounded-lg">
          <p className="text-sm font-semibold text-gray-900">
            TO: {contact?.name || 'Contact'} — {contact?.title || 'Title'}
          </p>
          <p className="text-sm text-gray-600">Email: {contact?.email}</p>
          <p className="text-sm text-gray-600">
            Company: {company?.name} ({company?.industry})
          </p>
        </div>

        {/* Savings reminder */}
        <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
          <p className="text-sm font-semibold text-blue-900">
            Estimated savings: {formatCurrency(draft?.savings_mid)} •
            Score: {draft?.score || 0}/100 — {draft?.tier || 'unknown'}
          </p>
        </div>

        {/* Tone warnings */}
        {draft?.tone_warnings && draft.tone_warnings.length > 0 && (
          <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg">
            <p className="text-sm font-semibold text-yellow-900 mb-2">
              ⚠️ Tone Warnings
            </p>
            {draft.tone_warnings.map((warning, idx) => (
              <p key={idx} className="text-sm text-yellow-800">
                • {warning}
              </p>
            ))}
            <p className="text-xs text-yellow-700 mt-2">
              This email may have issues — review before approving
            </p>
          </div>
        )}

        {/* Subject line field */}
        <div className="mb-4">
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Subject Line
          </label>
          {isEditing ? (
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              maxLength="60"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          ) : (
            <p className="px-3 py-2 bg-gray-100 rounded-lg text-gray-900">{subject}</p>
          )}
          {isEditing && (
            <p className="text-xs text-gray-600 mt-1">
              {subject.length}/60 characters
            </p>
          )}
        </div>

        {/* Email body field */}
        <div className="mb-4">
          <label className="block text-sm font-semibold text-gray-700 mb-2">
            Email Body
          </label>
          {isEditing ? (
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows="8"
              className={`w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 ${
                wordCountExceeded
                  ? 'border-red-500 focus:ring-red-500'
                  : 'border-gray-300 focus:ring-blue-500'
              }`}
            />
          ) : (
            <div className="px-3 py-2 bg-gray-100 rounded-lg text-gray-900 whitespace-pre-wrap max-h-64 overflow-y-auto">
              {body}
            </div>
          )}
          <div className="flex justify-between mt-1">
            <p className={`text-xs ${wordCountExceeded ? 'text-red-600' : 'text-gray-600'}`}>
              {wordCount}/250 words
            </p>
            {wordCountExceeded && (
              <p className="text-xs text-red-600 font-semibold">Over word limit</p>
            )}
          </div>
        </div>

        {/* Rejection form */}
        {showRejectForm && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
            <label className="block text-sm font-semibold text-gray-700 mb-2">
              Rejection Reason
            </label>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows="3"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
              placeholder="Explain why you're rejecting this email..."
            />
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-2 flex-wrap">
          {!showRejectForm && (
            <>
              <button
                onClick={handleApprove}
                disabled={isSubmitting || wordCountExceeded}
                className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 transition font-semibold"
              >
                {isSubmitting ? '⏳' : '✓'}
                {hasEdits ? ' Save Edits and Approve' : ' Approve and Queue for Send'}
              </button>

              <button
                onClick={() => {
                  if (isEditing) {
                    setIsEditing(false);
                  } else {
                    setIsEditing(true);
                  }
                }}
                className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition font-semibold"
              >
                {isEditing ? 'Done Editing' : '✎ Edit'}
              </button>

              <button
                onClick={() => setShowRejectForm(true)}
                className="px-4 py-2 border border-red-600 text-red-600 rounded-lg hover:bg-red-50 transition font-semibold"
              >
                ✗ Reject
              </button>

              <button
                onClick={handleRegenerate}
                disabled={isSubmitting}
                className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition font-semibold"
              >
                {isSubmitting ? '⏳' : '↻'} Regenerate
              </button>
            </>
          )}

          {showRejectForm && (
            <>
              <button
                onClick={handleReject}
                disabled={isSubmitting}
                className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:bg-gray-400 transition font-semibold"
              >
                {isSubmitting ? '⏳' : '✓'} Confirm Reject
              </button>
              <button
                onClick={() => {
                  setShowRejectForm(false);
                  setRejectReason('');
                }}
                className="flex-1 px-4 py-2 bg-gray-300 text-gray-800 rounded-lg hover:bg-gray-400 transition font-semibold"
              >
                Cancel
              </button>
            </>
          )}

          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 rounded-lg hover:bg-gray-100 transition font-semibold"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
