import { useEffect, useMemo, useState } from "react";

import {
  api,
  AccountDefaults,
  AccountDeletionPreview,
  AccessStatus,
  RetentionReport,
  clearStoredAccessToken,
} from "../api/client";
import { AUDIENCE_LEVELS, CONTENT_FORMATS, EMOJI_PREFERENCES, STYLE_PRESETS, TARGET_PLATFORMS } from "../constants";

const ACCOUNT_DELETION_NOTICE_KEY = "story-engine-account-deletion-notice";

export function SettingsPage() {
  const [defaults, setDefaults] = useState<AccountDefaults | null>(null);
  const [accessStatus, setAccessStatus] = useState<AccessStatus | null>(null);
  const [deletionPreview, setDeletionPreview] = useState<AccountDeletionPreview | null>(null);
  const [retentionReport, setRetentionReport] = useState<RetentionReport | null>(null);
  const [stylePreset, setStylePreset] = useState("clean_3d_cartoon");
  const [targetPlatforms, setTargetPlatforms] = useState<string[]>(["instagram", "tiktok", "youtube"]);
  const [captionTone, setCaptionTone] = useState("playful explainer");
  const [hashtagSet, setHashtagSet] = useState("#coding #webdev #learncode #javascript #codetoonsai");
  const [durationSeconds, setDurationSeconds] = useState(18);
  const [audienceLevel, setAudienceLevel] = useState("beginner");
  const [contentFormat, setContentFormat] = useState("coding metaphor");
  const [brandDescription, setBrandDescription] = useState("");
  const [preferredCta, setPreferredCta] = useState("");
  const [avoidPhrases, setAvoidPhrases] = useState("");
  const [emojiPreference, setEmojiPreference] = useState("minimal");
  const [error, setError] = useState("");
  const [deletionError, setDeletionError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [confirmationPhrase, setConfirmationPhrase] = useState("");
  const [deletionPassword, setDeletionPassword] = useState("");
  const [acknowledgeProviderVideosRemainOnline, setAcknowledgeProviderVideosRemainOnline] = useState(false);

  function applyConfig(config: AccountDefaults["account_config_json"]) {
    setStylePreset(String(config.default_style_preset ?? "clean_3d_cartoon"));
    setTargetPlatforms(Array.isArray(config.target_platforms) ? config.target_platforms : ["instagram"]);
    setCaptionTone(String(config.default_caption_tone ?? "playful explainer"));
    setHashtagSet(Array.isArray(config.default_hashtag_set) ? config.default_hashtag_set.join(" ") : "");
    setDurationSeconds(Number(config.default_duration_seconds ?? 18));
    setAudienceLevel(String(config.default_audience_level ?? "beginner"));
    setContentFormat(String(config.default_content_format ?? "coding metaphor"));
    setBrandDescription(String(config.brand_description ?? ""));
    setPreferredCta(String(config.preferred_cta ?? ""));
    setAvoidPhrases(Array.isArray(config.avoid_phrases) ? config.avoid_phrases.join(", ") : "");
    setEmojiPreference(String(config.emoji_preference ?? "minimal"));
  }

  function togglePlatform(platform: string) {
    setTargetPlatforms((current) => {
      if (current.includes(platform)) {
        const next = current.filter((item) => item !== platform);
        return next.length > 0 ? next : current;
      }
      return [...current, platform];
    });
  }

  async function loadDeletionContext() {
    const [status, preview, retention] = await Promise.all([
      api.getAccessStatus(),
      api.getAccountDeletionPreview(),
      api.getRetentionReport(),
    ]);
    setAccessStatus(status);
    setDeletionPreview(preview);
    setRetentionReport(retention);
  }

  useEffect(() => {
    Promise.all([api.getAccountDefaults(), loadDeletionContext()])
      .then(([data]) => {
        setDefaults(data);
        applyConfig(data.account_config_json);
      })
      .catch((requestError: Error) => setError(requestError.message));
  }, []);

  async function handleSave() {
    try {
      setError("");
      setIsSaving(true);
      const updated = await api.updateAccountDefaults({
        default_style_preset: stylePreset,
        target_platforms: targetPlatforms,
        default_caption_tone: captionTone,
        default_hashtag_set: hashtagSet.split(/\s+/).filter(Boolean),
        default_duration_seconds: durationSeconds,
        default_audience_level: audienceLevel,
        default_content_format: contentFormat,
        brand_description: brandDescription,
        preferred_cta: preferredCta,
        avoid_phrases: avoidPhrases.split(",").map((item) => item.trim()).filter(Boolean),
        emoji_preference: emojiPreference,
      });
      setDefaults(updated);
      applyConfig(updated.account_config_json);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Failed to save brand defaults.");
    } finally {
      setIsSaving(false);
    }
  }

  const requiresPassword = Boolean(accessStatus?.auth_enabled && deletionPreview?.requires_password_confirmation);
  const canSubmitDeletion = useMemo(() => {
    if (!deletionPreview?.can_delete) {
      return false;
    }
    if (confirmationPhrase.trim() !== deletionPreview.confirmation_phrase) {
      return false;
    }
    if (!acknowledgeProviderVideosRemainOnline) {
      return false;
    }
    if (requiresPassword && !deletionPassword.trim()) {
      return false;
    }
    return true;
  }, [acknowledgeProviderVideosRemainOnline, confirmationPhrase, deletionPassword, deletionPreview, requiresPassword]);

  async function handleDeleteAccount() {
    if (!deletionPreview) {
      return;
    }
    try {
      setDeletionError("");
      setIsDeleting(true);
      await api.validateAccountDeletion({
        confirmation_phrase: confirmationPhrase,
        acknowledge_provider_videos_remain_online: acknowledgeProviderVideosRemainOnline,
        password: requiresPassword ? deletionPassword : null,
      });
      const result = await api.deleteAccount({
        confirmation_phrase: confirmationPhrase,
        acknowledge_provider_videos_remain_online: acknowledgeProviderVideosRemainOnline,
        password: requiresPassword ? deletionPassword : null,
      });
      window.sessionStorage.setItem(ACCOUNT_DELETION_NOTICE_KEY, result.message);
      clearStoredAccessToken();
      window.dispatchEvent(new CustomEvent("story-engine-account-deleted", { detail: { message: result.message } }));
    } catch (requestError) {
      setDeletionError(requestError instanceof Error ? requestError.message : "Failed to delete the account.");
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <div className="page stack">
      <section className="page-header-card panel">
        <div>
          <p className="eyebrow">Settings</p>
          <h2>Brand Defaults</h2>
          <p className="subtle">Set the defaults used for new ideas, new runs, and posting copy.</p>
        </div>
        <div className="hero-actions">
          <button className="secondary" type="button" onClick={() => defaults ? applyConfig(defaults.account_config_json) : undefined}>
            Reset Form
          </button>
          <button onClick={handleSave} disabled={isSaving}>{isSaving ? "Saving..." : "Save Defaults"}</button>
        </div>
      </section>
      {error ? <p className="error">{error}</p> : null}
      <section className="panel">
        <div className="form-grid">
          <label className="field">
            <span>Default Style Preset</span>
            <select value={stylePreset} onChange={(event) => setStylePreset(event.target.value)}>
              {STYLE_PRESETS.map((preset) => <option key={preset} value={preset}>{preset}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Default Caption Tone</span>
            <input value={captionTone} onChange={(event) => setCaptionTone(event.target.value)} />
          </label>
          <label className="field">
            <span>Default Video Duration</span>
            <input type="number" min={5} max={30} value={durationSeconds} onChange={(event) => setDurationSeconds(Number(event.target.value))} />
          </label>
          <label className="field">
            <span>Default Audience Level</span>
            <select value={audienceLevel} onChange={(event) => setAudienceLevel(event.target.value)}>
              {AUDIENCE_LEVELS.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Default Content Format</span>
            <select value={contentFormat} onChange={(event) => setContentFormat(event.target.value)}>
              {CONTENT_FORMATS.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Emoji Preference</span>
            <select value={emojiPreference} onChange={(event) => setEmojiPreference(event.target.value)}>
              {EMOJI_PREFERENCES.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <div className="field field-wide">
            <span>Default Target Platforms</span>
            <div className="toggle-row">
              {TARGET_PLATFORMS.map((platform) => (
                <label key={platform} className="toggle-chip">
                  <input type="checkbox" checked={targetPlatforms.includes(platform)} onChange={() => togglePlatform(platform)} />
                  <span>{platform}</span>
                </label>
              ))}
            </div>
          </div>
          <label className="field field-wide">
            <span>Default Hashtag Set</span>
            <textarea value={hashtagSet} onChange={(event) => setHashtagSet(event.target.value)} rows={3} />
          </label>
          <label className="field field-wide">
            <span>Short Brand Description</span>
            <textarea value={brandDescription} onChange={(event) => setBrandDescription(event.target.value)} rows={3} />
          </label>
          <label className="field field-wide">
            <span>Preferred CTA</span>
            <textarea value={preferredCta} onChange={(event) => setPreferredCta(event.target.value)} rows={3} />
          </label>
          <label className="field field-wide">
            <span>Words/Phrases To Avoid</span>
            <textarea value={avoidPhrases} onChange={(event) => setAvoidPhrases(event.target.value)} rows={3} />
          </label>
        </div>
      </section>
      <section className="panel stack">
        <div>
          <p className="eyebrow">Danger Zone</p>
          <h3>Delete account</h3>
          <p className="subtle">
            Deleting the account permanently removes local Story Engine data, disconnects social accounts, logs you out,
            and cannot be undone.
          </p>
        </div>
        <div className="notice-card danger">
          <strong>Uploaded provider videos stay online</strong>
          <p>{deletionPreview?.provider_video_warning ?? "Uploaded provider videos remain online and must be removed on those platforms separately."}</p>
        </div>
        {retentionReport ? (
          <div className="notice-card">
            <strong>Retention policy</strong>
            <p>
              Story Engine currently uses a {retentionReport.default_retention_months}-month maximum retention window for data
              that is no longer needed and exposes a dry-run retention report for review.
            </p>
          </div>
        ) : null}
        {deletionPreview ? (
          <>
            <div className="stack">
              <strong>Connected accounts to disconnect</strong>
              {deletionPreview.connected_accounts.length === 0 ? (
                <p className="subtle">No connected social accounts were found.</p>
              ) : (
                <ul>
                  {deletionPreview.connected_accounts.map((item) => (
                    <li key={`${item.platform}-${item.display_name ?? item.username ?? "connection"}`}>
                      {item.platform}
                      {item.display_name ? ` - ${item.display_name}` : ""}
                      {item.username ? ` (${item.username})` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="stack">
              <strong>Data that will be deleted</strong>
              <ul>
                {deletionPreview.deletion_categories.map((item) => (
                  <li key={item.key}>
                    {item.title} ({item.count}) - {item.description}
                  </li>
                ))}
              </ul>
            </div>
            <div className="stack">
              <strong>Data that will be anonymised</strong>
              <ul>
                {deletionPreview.anonymised_categories.map((item) => (
                  <li key={item.key}>
                    {item.title} ({item.count}) - {item.description}
                  </li>
                ))}
              </ul>
            </div>
            <div className="stack">
              <strong>Data that may be temporarily retained</strong>
              <ul>
                {deletionPreview.temporarily_retained_categories.map((item) => (
                  <li key={item.key}>
                    {item.title} ({item.count}) - {item.description}
                  </li>
                ))}
              </ul>
            </div>
            <label className="field">
              <span>Type the confirmation phrase</span>
              <input
                aria-label="Delete account confirmation phrase"
                value={confirmationPhrase}
                onChange={(event) => setConfirmationPhrase(event.target.value)}
                placeholder={deletionPreview.confirmation_phrase}
              />
            </label>
            {requiresPassword ? (
              <label className="field">
                <span>Re-enter the app access password</span>
                <input
                  aria-label="Delete account password confirmation"
                  type="password"
                  value={deletionPassword}
                  onChange={(event) => setDeletionPassword(event.target.value)}
                  placeholder="Enter the current app access password"
                />
              </label>
            ) : (
              <p className="subtle">This environment does not support password re-entry, so deletion uses the current protected session plus the confirmation steps below.</p>
            )}
            <label className="toggle-chip">
              <input
                type="checkbox"
                checked={acknowledgeProviderVideosRemainOnline}
                onChange={(event) => setAcknowledgeProviderVideosRemainOnline(event.target.checked)}
              />
              <span>I understand that uploaded YouTube videos remain online and are not deleted automatically.</span>
            </label>
            <div className="notice-card danger">
              <strong>Irreversible action</strong>
              <p>This permanently deletes the Story Engine account and logs you out immediately.</p>
            </div>
          </>
        ) : (
          <p className="subtle">Loading deletion preview...</p>
        )}
        {deletionError ? <p className="error">{deletionError}</p> : null}
        <div className="hero-actions">
          <button
            className="secondary"
            type="button"
            onClick={() => {
              setConfirmationPhrase("");
              setDeletionPassword("");
              setAcknowledgeProviderVideosRemainOnline(false);
              setDeletionError("");
            }}
          >
            Clear Confirmation
          </button>
          <button type="button" disabled={!canSubmitDeletion || isDeleting} onClick={handleDeleteAccount}>
            {isDeleting ? "Deleting account..." : "Delete account"}
          </button>
        </div>
      </section>
    </div>
  );
}
