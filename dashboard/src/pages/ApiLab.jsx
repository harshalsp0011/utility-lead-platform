import { useState } from 'react';
import {
  apiLabApolloEnrich,
  apiLabApolloSearch,
  apiLabCreditsHunter,
  apiLabCreditsScraperApi,
  apiLabCreditsSnov,
  apiLabCreditsZeroBounce,
  apiLabEnrichmentWaterfall,
  apiLabGoogleMaps,
  apiLabHunter,
  apiLabInstantly,
  apiLabProspeo,
  apiLabScraperDirectory,
  apiLabSendGrid,
  apiLabSerperEmail,
  apiLabSnov,
  apiLabTavilyNews,
  apiLabTavilySearch,
  apiLabYelp,
  apiLabZeroBounceGuessFormat,
  apiLabZeroBounceValidate,
} from '../services/api';

// ---------------------------------------------------------------------------
// API function map — keyed by card id
// ---------------------------------------------------------------------------

const API_FN = {
  tavily_search:            apiLabTavilySearch,
  tavily_news:              apiLabTavilyNews,
  google_maps:              apiLabGoogleMaps,
  yelp:                     apiLabYelp,
  hunter:                   apiLabHunter,
  apollo_enrich:            apiLabApolloEnrich,
  apollo_search:            apiLabApolloSearch,
  snov:                     apiLabSnov,
  prospeo:                  apiLabProspeo,
  zerobounce_validate:      apiLabZeroBounceValidate,
  zerobounce_guessformat:   apiLabZeroBounceGuessFormat,
  serper_email:             apiLabSerperEmail,
  sendgrid:                 apiLabSendGrid,
  instantly:                apiLabInstantly,
  scraper_directory:        apiLabScraperDirectory,
};

// Credit-check functions — only for providers that expose a balance/usage endpoint
const CREDIT_FN = {
  hunter:           apiLabCreditsHunter,
  zerobounce_validate:  apiLabCreditsZeroBounce,
  zerobounce_guessformat: apiLabCreditsZeroBounce,
  snov:             apiLabCreditsSnov,
  scraper_directory: apiLabCreditsScraperApi,
};

// ---------------------------------------------------------------------------
// Section + card configuration (data-driven)
// ---------------------------------------------------------------------------

const SECTIONS = [
  {
    id: 'search_discovery',
    title: 'Search & Discovery',
    icon: '🔍',
    runAllLabel: 'Run All Discovery APIs',
    runAllFields: [
      { name: 'industry', label: 'Industry', type: 'text', placeholder: 'healthcare' },
      { name: 'location', label: 'Location', type: 'text', placeholder: 'Buffalo, NY' },
    ],
    runAllMode: 'sequential', // runs each card individually in sequence
    cards: [
      {
        id: 'tavily_search',
        title: 'Tavily Web Search',
        description: 'Discovers directory URLs for a given industry and location using Tavily web search.',
        badge: 'stores in: directory_sources table',
        badgeColor: 'blue',
        fields: [
          { name: 'industry', label: 'Industry', type: 'text', placeholder: 'healthcare' },
          { name: 'location', label: 'Location', type: 'text', placeholder: 'Buffalo, NY' },
        ],
        limits: {
          free: '1,000 searches/month',
          rate: 'No hard rate limit published',
          reset: 'Monthly',
          canCheckLive: false,
          notes: 'Paid plans start at $40/mo for 4,000 searches.',
        },
      },
      {
        id: 'tavily_news',
        title: 'Tavily News Scout',
        description: 'Finds companies in local business news with buying signals (expansion, cost pressure, new facility).',
        badge: 'not stored',
        badgeColor: 'gray',
        fields: [
          { name: 'industry', label: 'Industry', type: 'text', placeholder: 'healthcare' },
          { name: 'location', label: 'Location', type: 'text', placeholder: 'Buffalo, NY' },
          { name: 'max_results', label: 'Max Results', type: 'number', placeholder: '10', defaultValue: 10 },
        ],
        limits: {
          free: '1,000 searches/month (shared with Tavily Web)',
          rate: 'No hard rate limit published',
          reset: 'Monthly',
          canCheckLive: false,
          notes: 'Each news call may fire up to 3 internal Tavily requests (one per LLM-generated query).',
        },
      },
      {
        id: 'google_maps',
        title: 'Google Maps Places',
        description: 'Searches Google Places API for businesses matching industry and location. Skips permanently closed.',
        badge: 'not stored',
        badgeColor: 'gray',
        fields: [
          { name: 'industry', label: 'Industry', type: 'text', placeholder: 'healthcare' },
          { name: 'location', label: 'Location', type: 'text', placeholder: 'Buffalo, NY' },
          { name: 'limit', label: 'Limit', type: 'number', placeholder: '20', defaultValue: 20 },
        ],
        limits: {
          free: '$200 free credit/month (~4,000 Text Search calls)',
          rate: '600 req/min (QPM) per project',
          reset: 'Monthly',
          canCheckLive: false,
          notes: 'Text Search = $0.032/call after free credit. Max 20 results per call (enforced in code).',
        },
      },
      {
        id: 'yelp',
        title: 'Yelp Business Search',
        description: 'Finds local businesses sorted by rating. Maps Yelp categories to internal industry buckets.',
        badge: 'not stored',
        badgeColor: 'gray',
        fields: [
          { name: 'industry', label: 'Industry', type: 'text', placeholder: 'healthcare' },
          { name: 'location', label: 'Location', type: 'text', placeholder: 'Buffalo, NY' },
          { name: 'limit', label: 'Limit', type: 'number', placeholder: '50', defaultValue: 50 },
        ],
        limits: {
          free: '500 calls/day (free tier hard limit)',
          rate: '5 req/sec',
          reset: 'Daily',
          canCheckLive: false,
          notes: 'Max 50 results per call (enforced in code). Requires Yelp Fusion API key.',
        },
      },
    ],
  },
  {
    id: 'enrichment',
    title: 'Contact Enrichment & Email Finding',
    icon: '📋',
    runAllLabel: 'Run Full Waterfall (stores to DB)',
    runAllFields: [
      { name: 'company_name', label: 'Company Name', type: 'text', placeholder: 'Acme Health Systems' },
      { name: 'domain', label: 'Domain', type: 'text', placeholder: 'acmehealth.com' },
    ],
    runAllMode: 'waterfall', // single waterfall call, not per-card
    runAllEndpointFn: apiLabEnrichmentWaterfall,
    runAllBadge: 'stores in: contacts table',
    cards: [
      {
        id: 'hunter',
        title: 'Hunter.io',
        description: 'Domain-based email finder targeting decision-makers (CFO, Finance Director, Facilities Manager, etc.).',
        badge: 'not stored (individual)',
        badgeColor: 'gray',
        fields: [
          { name: 'domain', label: 'Domain', type: 'text', placeholder: 'acmehealth.com' },
        ],
        limits: {
          free: '25 domain searches/month (free plan)',
          rate: '10 req/sec',
          reset: 'Monthly',
          canCheckLive: true,
          liveFields: ['searches_used', 'searches_available', 'plan', 'reset_date'],
          notes: 'Starter: 500/mo. Each domain search = 1 credit. Email verification is separate.',
        },
      },
      {
        id: 'apollo_enrich',
        title: 'Apollo — Org Enrich',
        description: 'Enriches a company by domain: returns employee_count, city, and state.',
        badge: 'not stored (individual)',
        badgeColor: 'gray',
        fields: [
          { name: 'domain', label: 'Domain', type: 'text', placeholder: 'acmehealth.com' },
        ],
        limits: {
          free: '10 org enrichments/month (free plan)',
          rate: '10 req/min',
          reset: 'Monthly',
          canCheckLive: false,
          notes: 'Returns 403 when monthly export limit is reached. Free tier: 50 people exports + 10 org enrichments.',
        },
      },
      {
        id: 'apollo_search',
        title: 'Apollo — People Search',
        description: 'Finds decision-maker contacts at a company (senior/executive seniority, target titles).',
        badge: 'not stored (individual)',
        badgeColor: 'gray',
        fields: [
          { name: 'company_name', label: 'Company Name', type: 'text', placeholder: 'Acme Health Systems' },
          { name: 'domain', label: 'Domain', type: 'text', placeholder: 'acmehealth.com' },
        ],
        limits: {
          free: '50 people exports/month (free plan)',
          rate: '10 req/min',
          reset: 'Monthly',
          canCheckLive: false,
          notes: 'Returns 403 on rate-limit; code sets _apollo_blocked=True to skip for the rest of the run.',
        },
      },
      {
        id: 'snov',
        title: 'Snov.io',
        description: 'OAuth-based domain email finder. Finds verified and unverified contacts. 150 credits/month free tier.',
        badge: 'not stored (individual)',
        badgeColor: 'gray',
        fields: [
          { name: 'company_name', label: 'Company Name', type: 'text', placeholder: 'Acme Health Systems' },
          { name: 'domain', label: 'Domain', type: 'text', placeholder: 'acmehealth.com' },
        ],
        limits: {
          free: '150 credits/month (free plan)',
          rate: 'Not published',
          reset: 'Monthly',
          canCheckLive: true,
          liveFields: ['balance'],
          notes: '1 credit = 1 email found. OAuth token required per call (auto-fetched).',
        },
      },
      {
        id: 'prospeo',
        title: 'Prospeo',
        description: 'LinkedIn-sourced email lookup. Searches by company domain with seniority filters, then enriches top 2 contacts.',
        badge: 'not stored (individual)',
        badgeColor: 'gray',
        fields: [
          { name: 'company_name', label: 'Company Name', type: 'text', placeholder: 'Acme Health Systems' },
          { name: 'domain', label: 'Domain', type: 'text', placeholder: 'acmehealth.com' },
        ],
        limits: {
          free: 'Free trial credits (limited)',
          rate: 'Not published',
          reset: 'One-time trial',
          canCheckLive: false,
          notes: '1 credit per person enriched. Only top 2 contacts are enriched per call to conserve credits.',
        },
      },
      {
        id: 'zerobounce_validate',
        title: 'ZeroBounce — Validate',
        description: 'Validates a single email address. Returns true (valid/catch-all), false (invalid/spam), or null (unknown).',
        badge: 'not stored',
        badgeColor: 'gray',
        fields: [
          { name: 'email', label: 'Email', type: 'email', placeholder: 'john.doe@acmehealth.com' },
        ],
        limits: {
          free: '100 validations/month (free plan)',
          rate: 'Not published',
          reset: 'Monthly',
          canCheckLive: true,
          liveFields: ['credits'],
          notes: '1 credit = 1 email validated. Shared with guessformat calls.',
        },
      },
      {
        id: 'zerobounce_guessformat',
        title: 'ZeroBounce — Guess Format',
        description: 'Infers the email naming format (e.g., first.last, flast) for a given domain.',
        badge: 'not stored',
        badgeColor: 'gray',
        fields: [
          { name: 'domain', label: 'Domain', type: 'text', placeholder: 'acmehealth.com' },
        ],
        limits: {
          free: '10 domain format guesses/month (free plan)',
          rate: 'Not published',
          reset: 'Monthly',
          canCheckLive: true,
          liveFields: ['credits'],
          notes: 'Tighter limit than validation. Each guess = 1 credit from the same ZeroBounce pool.',
        },
      },
      {
        id: 'serper_email',
        title: 'Serper / SerpAPI',
        description: 'Google search-based email extraction. Queries "@domain.com" and company name to surface contact emails.',
        badge: 'not stored (individual)',
        badgeColor: 'gray',
        fields: [
          { name: 'company_name', label: 'Company Name', type: 'text', placeholder: 'Acme Health Systems' },
          { name: 'domain', label: 'Domain', type: 'text', placeholder: 'acmehealth.com' },
        ],
        limits: {
          free: 'Serper: 2,500 queries/month free — SerpAPI: 100 queries/month free',
          rate: 'Serper: not published — SerpAPI: 2 req/sec',
          reset: 'Monthly',
          canCheckLive: false,
          notes: 'Code tries Serper first, falls back to SerpAPI. Each call fires 2 Google search queries.',
        },
      },
    ],
  },
  {
    id: 'email_delivery',
    title: 'Email Delivery',
    icon: '✉️',
    runAllMode: 'none', // no Run All for email — too risky
    cards: [
      {
        id: 'sendgrid',
        title: 'SendGrid',
        description: 'Sends a real email via SendGrid with open + click tracking. Uses SENDGRID_FROM_EMAIL as sender.',
        badge: 'not stored (test send)',
        badgeColor: 'orange',
        requiresConfirmation: true,
        confirmationText: 'I understand this will send a real email',
        fields: [
          { name: 'to_email', label: 'To Email', type: 'email', placeholder: 'recipient@example.com' },
          { name: 'to_name', label: 'To Name', type: 'text', placeholder: 'John Doe' },
          { name: 'subject', label: 'Subject', type: 'text', placeholder: 'Test from API Lab' },
          { name: 'body', label: 'Body', type: 'textarea', placeholder: 'Hello, this is a test message.' },
        ],
        limits: {
          free: '100 emails/day (free tier)',
          rate: '600 req/min (marketing sends), higher for transactional',
          reset: 'Daily',
          canCheckLive: false,
          notes: 'Free tier is permanent (not trial). Paid plans start at $19.95/mo for 50K emails.',
        },
      },
      {
        id: 'instantly',
        title: 'Instantly.ai',
        description: 'Adds a lead to your Instantly campaign. WARNING: this triggers a real email sequence in the campaign.',
        badge: 'not stored (test send)',
        badgeColor: 'orange',
        requiresConfirmation: true,
        confirmationText: 'I understand this adds a real lead to my Instantly campaign',
        fields: [
          { name: 'to_email', label: 'To Email', type: 'email', placeholder: 'recipient@example.com' },
          { name: 'to_name', label: 'To Name', type: 'text', placeholder: 'John Doe' },
          { name: 'subject', label: 'Subject', type: 'text', placeholder: 'Test from API Lab' },
          { name: 'body', label: 'Body', type: 'textarea', placeholder: 'Hello, this is a test message.' },
        ],
        limits: {
          free: 'Plan-dependent (Growth: 1,000 active leads/mo, Hypergrowth: unlimited)',
          rate: 'Not published — campaign-level daily send limits apply',
          reset: 'Monthly',
          canCheckLive: false,
          notes: 'Each call adds lead to INSTANTLY_CAMPAIGN_ID. Sending schedule is controlled by campaign settings.',
        },
      },
    ],
  },
  {
    id: 'scraping',
    title: 'Web Scraping & Proxies',
    icon: '🌐',
    runAllMode: 'sequential',
    runAllFields: [
      { name: 'directory_url', label: 'Directory URL', type: 'text', placeholder: 'https://example.com/directory' },
    ],
    cards: [
      {
        id: 'scraper_directory',
        title: 'ScraperAPI — Directory Scrape',
        description: 'Scrapes a business directory URL for company listings. Uses rotating proxies to bypass IP blocks. May take up to 2 minutes for large directories.',
        badge: 'not stored',
        badgeColor: 'gray',
        fields: [
          { name: 'directory_url', label: 'Directory URL', type: 'text', placeholder: 'https://example.com/directory' },
        ],
        limits: {
          free: '1,000 API credits/month (free plan)',
          rate: '1 concurrent request (free) — 5 concurrent (Hobby)',
          reset: 'Monthly',
          canCheckLive: true,
          liveFields: ['requests_used', 'request_limit', 'concurrency_limit'],
          notes: '1 basic request = 1 credit. JavaScript rendering = 5 credits. Each paginated page = 1 credit.',
        },
      },
    ],
  },
];

// ---------------------------------------------------------------------------
// Helper: get default input values for a card
// ---------------------------------------------------------------------------

function getCardDefaults(card) {
  const defaults = {};
  for (const f of card.fields) {
    if (f.defaultValue !== undefined) defaults[f.name] = f.defaultValue;
  }
  return defaults;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StorageBadge({ text, color }) {
  const colorMap = {
    blue:   'bg-blue-100 text-blue-700',
    gray:   'bg-gray-100 text-gray-600',
    orange: 'bg-orange-100 text-orange-700',
    green:  'bg-green-100 text-green-700',
  };
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-mono ${colorMap[color] || colorMap.gray}`}>
      {text}
    </span>
  );
}

function ResponseViewer({ result, error, loading }) {
  const [copied, setCopied] = useState(false);

  if (loading) {
    return (
      <div className="mt-3 p-3 bg-blue-50 rounded border border-blue-200 text-blue-700 text-sm flex items-center gap-2">
        <div className="animate-spin w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full" />
        Calling API...
      </div>
    );
  }

  if (!result && !error) return null;

  const hasError   = !!error || (result && result.error);
  const displayErr = error || (result && result.error);
  const jsonText   = result
    ? JSON.stringify(result.data ?? null, null, 2)
    : null;

  function copy() {
    navigator.clipboard.writeText(jsonText || displayErr || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="mt-3 border border-gray-200 rounded-lg overflow-hidden shadow-sm">
      {/* Metadata row */}
      {result && (
        <div className="flex items-center gap-3 px-3 py-2 bg-gray-50 border-b border-gray-200 text-xs text-gray-500">
          <span className={result.success ? 'text-green-600 font-semibold' : 'text-red-600 font-semibold'}>
            {result.success ? '✓ success' : '✗ failed'}
          </span>
          <span>{result.duration_ms} ms</span>
          {result.stored_in && (
            <span className="text-gray-400">stored in: <span className="text-gray-600">{result.stored_in}</span></span>
          )}
          <button
            onClick={copy}
            className="ml-auto text-gray-400 hover:text-gray-700 transition-colors"
          >
            {copied ? '✓ copied' : 'copy'}
          </button>
        </div>
      )}

      {/* Error banner */}
      {hasError && (
        <div className="px-3 py-2 bg-red-50 text-red-700 text-xs border-b border-red-200">
          {displayErr}
        </div>
      )}

      {/* JSON output — keep dark terminal style for readability */}
      {jsonText && (
        <pre className="p-3 bg-gray-900 text-green-400 text-xs font-mono overflow-auto max-h-72 whitespace-pre-wrap break-words">
          {jsonText}
        </pre>
      )}
    </div>
  );
}

function FieldInput({ field, value, onChange }) {
  const base = 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent';

  if (field.type === 'textarea') {
    return (
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">{field.label}</label>
        <textarea
          rows={3}
          className={base}
          placeholder={field.placeholder}
          value={value ?? ''}
          onChange={(e) => onChange(field.name, e.target.value)}
        />
      </div>
    );
  }

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{field.label}</label>
      <input
        type={field.type || 'text'}
        className={base}
        placeholder={field.placeholder}
        value={value ?? (field.defaultValue ?? '')}
        onChange={(e) => onChange(field.name, field.type === 'number' ? Number(e.target.value) : e.target.value)}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// LimitsPanel — shows static limit info + optional live credit check
// ---------------------------------------------------------------------------

function LimitsPanel({ card, creditState, onCheckCredits }) {
  const { limits } = card;
  if (!limits) return null;

  const isLoading = creditState?.loading;
  const result    = creditState?.result;
  const err       = creditState?.error;

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-gray-50 border-b border-gray-200">
        <span className="text-xs font-semibold text-gray-600 flex items-center gap-1.5">
          <span>⚡</span> Rate &amp; Credit Limits
        </span>
        {limits.canCheckLive && (
          <button
            disabled={isLoading}
            onClick={onCheckCredits}
            className="text-xs px-2 py-1 bg-white border border-gray-300 hover:bg-gray-50 disabled:opacity-50 text-gray-600 rounded transition-colors"
          >
            {isLoading ? 'Checking...' : '↻ Check Live'}
          </button>
        )}
      </div>

      {/* Static info grid */}
      <div className="px-3 py-2 bg-white grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <div>
          <span className="text-gray-400 uppercase tracking-wide text-xs">Free allowance</span>
          <p className="text-gray-800 mt-0.5 font-medium">{limits.free}</p>
        </div>
        <div>
          <span className="text-gray-400 uppercase tracking-wide text-xs">Rate limit</span>
          <p className="text-gray-800 mt-0.5 font-medium">{limits.rate}</p>
        </div>
        <div>
          <span className="text-gray-400 uppercase tracking-wide text-xs">Resets</span>
          <p className="text-gray-800 mt-0.5 font-medium">{limits.reset}</p>
        </div>
        {limits.canCheckLive && (
          <div>
            <span className="text-gray-400 uppercase tracking-wide text-xs">Live check</span>
            <p className="text-green-600 mt-0.5 font-medium">✓ available</p>
          </div>
        )}
        {limits.notes && (
          <div className="col-span-2 pt-2 border-t border-gray-100 mt-0.5">
            <span className="text-gray-400">Note: </span>
            <span className="text-gray-500">{limits.notes}</span>
          </div>
        )}
      </div>

      {/* Live credit result */}
      {(isLoading || result || err) && (
        <div className="px-3 py-2 bg-gray-50 border-t border-gray-200">
          {isLoading && (
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <div className="animate-spin w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full" />
              Fetching live usage...
            </div>
          )}
          {err && !isLoading && (
            <p className="text-red-600 text-xs">{err}</p>
          )}
          {result && !isLoading && (
            <div className="space-y-1">
              <p className="text-xs text-gray-400 mb-1">Live usage ({result.duration_ms} ms):</p>
              {result.data && typeof result.data === 'object'
                ? Object.entries(result.data).map(([k, v]) => (
                    <div key={k} className="flex justify-between text-xs">
                      <span className="text-gray-500">{k.replace(/_/g, ' ')}</span>
                      <span className={
                        k.includes('available') || k.includes('credit') || k.includes('limit')
                          ? 'text-green-600 font-mono font-semibold'
                          : 'text-gray-800 font-mono'
                      }>
                        {v === null ? '—' : String(v)}
                      </span>
                    </div>
                  ))
                : <span className="text-gray-800 text-xs font-mono">{String(result.data)}</span>
              }
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ApiCard({ card, state, creditState, onInputChange, onRun, onCheckCredits }) {
  const inputs    = state?.inputs   || {};
  const loading   = state?.loading  || false;
  const result    = state?.result   || null;
  const error     = state?.error    || null;
  const confirmed = state?.confirmed || false;

  const runDisabled = loading || (card.requiresConfirmation && !confirmed);
  const btnStyle = card.requiresConfirmation
    ? 'bg-red-600 hover:bg-red-700 disabled:bg-red-300 text-white'
    : 'bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:text-gray-500 text-white';

  return (
    <div className="bg-white rounded-lg shadow p-5 border border-gray-100">
      {/* Card header */}
      <div className="flex items-center gap-3 mb-3">
        <h3 className="text-base font-bold text-gray-900 flex-1">{card.title}</h3>
        <StorageBadge text={card.badge} color={card.badgeColor} />
      </div>

      <div className="space-y-4">
        {/* Description */}
        <p className="text-sm text-gray-600 leading-relaxed">{card.description}</p>

        {/* Limits panel */}
        <LimitsPanel
          card={card}
          creditState={creditState}
          onCheckCredits={() => onCheckCredits(card.id)}
        />

        {/* Warning banner for destructive cards */}
        {card.requiresConfirmation && (
          <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg p-3">
            <span className="text-red-500 text-sm mt-0.5">⚠</span>
            <div className="flex-1">
              <p className="text-red-700 text-xs font-semibold mb-2">
                This action sends a real {card.id === 'instantly' ? 'lead to your campaign' : 'email'}.
                {card.id === 'instantly' && ' It may trigger an email sequence immediately.'}
              </p>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => onInputChange(card.id, '_confirmed', e.target.checked)}
                  className="accent-red-600"
                />
                <span className="text-red-700 text-xs">{card.confirmationText}</span>
              </label>
            </div>
          </div>
        )}

        {/* Input fields */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {card.fields.map((f) => (
            <div key={f.name} className={f.type === 'textarea' ? 'sm:col-span-2' : ''}>
              <FieldInput
                field={f}
                value={inputs[f.name]}
                onChange={(name, val) => onInputChange(card.id, name, val)}
              />
            </div>
          ))}
        </div>

        {/* Run button */}
        <button
          disabled={runDisabled}
          onClick={() => onRun(card.id)}
          className={`w-full py-2 rounded-lg text-sm font-semibold transition-colors ${btnStyle}`}
        >
          {loading ? 'Running...' : `Run ${card.title}`}
        </button>

        {/* Response */}
        <ResponseViewer result={result} error={error} loading={loading} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ApiLab() {
  // cardStates: { [cardId]: { inputs, loading, result, error, confirmed } }
  const [cardStates, setCardStates] = useState({});

  // creditStates: { [cardId]: { loading, result, error } }
  const [creditStates, setCreditStates] = useState({});

  // sectionRunning: { [sectionId]: boolean }
  const [sectionRunning, setSectionRunning] = useState({});

  // sectionInputs: shared Run All input values per section
  const [sectionInputs, setSectionInputs] = useState({});

  // waterfallResult: result from the enrichment waterfall Run All
  const [waterfallResult, setWaterfallResult] = useState(null);
  const [waterfallLoading, setWaterfallLoading] = useState(false);

  // -------------------------------------------------------------------------
  // State helpers
  // -------------------------------------------------------------------------

  function patchCard(cardId, patch) {
    setCardStates((prev) => ({
      ...prev,
      [cardId]: { ...prev[cardId], ...patch },
    }));
  }

  function handleInputChange(cardId, name, value) {
    if (name === '_confirmed') {
      patchCard(cardId, { confirmed: value });
    } else {
      setCardStates((prev) => ({
        ...prev,
        [cardId]: {
          ...prev[cardId],
          inputs: { ...(prev[cardId]?.inputs || {}), [name]: value },
        },
      }));
    }
  }

  function handleSectionInputChange(sectionId, name, value) {
    setSectionInputs((prev) => ({
      ...prev,
      [sectionId]: { ...(prev[sectionId] || {}), [name]: value },
    }));
  }

  // -------------------------------------------------------------------------
  // Check live credits for a card
  // -------------------------------------------------------------------------

  async function checkCredits(cardId) {
    const fn = CREDIT_FN[cardId];
    if (!fn) return;
    setCreditStates((prev) => ({ ...prev, [cardId]: { loading: true, result: null, error: null } }));
    try {
      const res = await fn();
      setCreditStates((prev) => ({ ...prev, [cardId]: { loading: false, result: res, error: null } }));
    } catch (err) {
      setCreditStates((prev) => ({ ...prev, [cardId]: { loading: false, result: null, error: err.message || String(err) } }));
    }
  }

  // -------------------------------------------------------------------------
  // Run a single card
  // -------------------------------------------------------------------------

  async function runCard(cardId, overrideBody = null) {
    const fn = API_FN[cardId];
    if (!fn) return;

    const section = SECTIONS.find((s) => s.cards.some((c) => c.id === cardId));
    const card    = section?.cards.find((c) => c.id === cardId);
    if (!card) return;

    const defaults = getCardDefaults(card);
    const body = overrideBody ?? { ...defaults, ...(cardStates[cardId]?.inputs || {}) };

    patchCard(cardId, { loading: true, result: null, error: null });
    try {
      const res = await fn(body);
      patchCard(cardId, { loading: false, result: res });
    } catch (err) {
      patchCard(cardId, { loading: false, error: err.message || String(err) });
    }
  }

  // -------------------------------------------------------------------------
  // Run All for a section
  // -------------------------------------------------------------------------

  async function runAll(section) {
    if (section.runAllMode === 'none') return;
    setSectionRunning((prev) => ({ ...prev, [section.id]: true }));

    if (section.runAllMode === 'waterfall') {
      // single waterfall call
      setWaterfallLoading(true);
      setWaterfallResult(null);
      try {
        const body = sectionInputs[section.id] || {};
        const res  = await section.runAllEndpointFn(body);
        setWaterfallResult(res);
      } catch (err) {
        setWaterfallResult({ success: false, error: err.message, data: null, duration_ms: 0 });
      } finally {
        setWaterfallLoading(false);
      }
    } else {
      // sequential: run each card one by one
      for (const card of section.cards) {
        const defaults     = getCardDefaults(card);
        const shared       = sectionInputs[section.id] || {};
        const cardInputs   = cardStates[card.id]?.inputs || {};
        const mergedBody   = { ...defaults, ...cardInputs, ...shared };
        await runCard(card.id, mergedBody);
      }
    }

    setSectionRunning((prev) => ({ ...prev, [section.id]: false }));
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="h-full overflow-y-auto bg-gray-50">
      <div className="p-6">
        {/* Page header — matches Triggers/Pipeline style */}
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900">API Lab</h1>
          <p className="text-gray-600 mt-1">
            Live test every external API integration. Individual calls are read-only; the enrichment waterfall writes to the database.
          </p>
        </div>

        <div className="space-y-10">
        {SECTIONS.map((section) => (
          <div key={section.id}>
            {/* Section header */}
            <div className="mb-4">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
                  <span>{section.icon}</span>
                  {section.title}
                </h2>

                {/* Run All button (hidden for email_delivery) */}
                {section.runAllMode !== 'none' && section.runAllMode !== undefined && (
                  <button
                    disabled={sectionRunning[section.id]}
                    onClick={() => runAll(section)}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:text-gray-500 text-white text-sm font-semibold rounded-lg transition-colors"
                  >
                    {sectionRunning[section.id] ? 'Running...' : section.runAllLabel || 'Run All'}
                  </button>
                )}
              </div>

              {/* Shared Run All input fields */}
              {section.runAllFields && section.runAllMode !== 'none' && (
                <div className="bg-white border border-gray-200 rounded-lg shadow px-4 py-4 mb-4">
                  <p className="text-sm font-semibold text-gray-700 mb-3">
                    {section.runAllMode === 'waterfall'
                      ? 'Waterfall inputs — shared across all providers:'
                      : 'Shared inputs for Run All:'}
                  </p>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {section.runAllFields.map((f) => (
                      <FieldInput
                        key={f.name}
                        field={f}
                        value={(sectionInputs[section.id] || {})[f.name]}
                        onChange={(name, val) => handleSectionInputChange(section.id, name, val)}
                      />
                    ))}
                  </div>

                  {/* Waterfall result display */}
                  {section.runAllMode === 'waterfall' && (
                    <div className="mt-3">
                      {section.runAllBadge && (
                        <div className="mb-2">
                          <StorageBadge text={section.runAllBadge} color="green" />
                        </div>
                      )}
                      <ResponseViewer
                        result={waterfallResult}
                        error={null}
                        loading={waterfallLoading}
                      />
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Cards grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {section.cards.map((card) => (
                <ApiCard
                  key={card.id}
                  card={card}
                  state={cardStates[card.id]}
                  creditState={creditStates[card.id]}
                  onInputChange={handleInputChange}
                  onRun={runCard}
                  onCheckCredits={checkCredits}
                />
              ))}
            </div>
          </div>
        ))}
        </div>
      </div>
    </div>
  );
}
