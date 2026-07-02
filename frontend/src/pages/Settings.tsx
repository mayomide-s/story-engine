import { useEffect, useState } from "react";

import { api, AccountDefaults } from "../api/client";
import { AUDIENCE_LEVELS, CONTENT_FORMATS, EMOJI_PREFERENCES, STYLE_PRESETS, TARGET_PLATFORMS } from "../constants";

export function SettingsPage() {
  const [defaults, setDefaults] = useState<AccountDefaults | null>(null);
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
  const [isSaving, setIsSaving] = useState(false);

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

  useEffect(() => {
    api.getAccountDefaults()
      .then((data) => {
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
    </div>
  );
}
