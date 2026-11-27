import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../../api/client";
import type {
  OidcSettingsStatus,
  OidcTestResult,
  SamlSettingsStatus,
  SamlTestResult,
  SsoSource,
} from "../../types";

// Single sign-on settings (super admins). Like the Azure DevOps connection,
// settings saved here override that provider's environment variables as a
// whole, including whether it's enabled; removing them reverts to the env vars.
// Secrets (client secret, SP private key) are write-only.
export default function AdminSso() {
  const navigate = useNavigate();
  return (
    <div className="container">
      <div className="breadcrumb">
        <a onClick={() => navigate("/admin")} style={{ cursor: "pointer" }}>← Portals</a>
      </div>
      <h1>Single sign-on</h1>
      <p className="subtitle">
        Let people sign in with your identity provider over OpenID Connect or SAML 2.0. Email
        and password sign-in always stays available, so a broken setup can't lock you out.
      </p>
      <OidcSection />
      <SamlSection />
    </div>
  );
}

function SourceBadge({ source, enabled }: { source: SsoSource; enabled: boolean }) {
  const where =
    source === "database" ? "Saved settings" : source === "environment" ? "Environment" : null;
  return (
    <div className="row">
      <strong>Status:</strong>
      <span className={`badge ${enabled ? "synced" : "pending"}`}>
        {enabled ? "Enabled" : "Disabled"}
      </span>
      {where && <span className="muted">from {where.toLowerCase()}</span>}
    </div>
  );
}

function Copyable({ label, value }: { label: string; value: string }) {
  return (
    <tr>
      <td>{label}</td>
      <td className="mono" style={{ wordBreak: "break-all" }}>{value}</td>
    </tr>
  );
}

function EnvTable({ rows, ignored }: { rows: [string, ReactNode][]; ignored: boolean }) {
  return (
    <details style={{ marginTop: 16 }}>
      <summary className="muted" style={{ cursor: "pointer" }}>Environment variables</summary>
      <table style={{ marginTop: 8 }}>
        <tbody>
          {rows.map(([name, value]) => (
            <tr key={name}>
              <td className="mono">{name}</td>
              <td>{value || <span className="muted">not set</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {ignored && (
        <div className="muted" style={{ marginTop: 8, fontSize: 13 }}>
          Ignored while saved settings exist.
        </div>
      )}
    </details>
  );
}

function useRunner() {
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  };
  return { error, setError, notice, setNotice, busy, run };
}

function EnableToggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <label style={{ fontWeight: 600, display: "flex", gap: 8, alignItems: "center" }}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        style={{ width: "auto" }}
      />
      {label}
    </label>
  );
}

// ── OIDC ──────────────────────────────────────────────────────────────────
function OidcSection() {
  const [status, setStatus] = useState<OidcSettingsStatus | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [discoveryUrl, setDiscoveryUrl] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [redirectUri, setRedirectUri] = useState("");
  const [scopes, setScopes] = useState("openid email profile");
  const [label, setLabel] = useState("");
  const [test, setTest] = useState<OidcTestResult | null>(null);
  const { error, setError, notice, setNotice, busy, run } = useRunner();

  const apply = (s: OidcSettingsStatus) => {
    setStatus(s);
    // Start from the saved values, else from the env vars to ease moving them here.
    const v = s.stored ?? s.environment;
    setEnabled(v.enabled);
    setDiscoveryUrl(v.discovery_url);
    setClientId(v.client_id);
    setRedirectUri(v.redirect_uri);
    setScopes(v.scopes || "openid email profile");
    setLabel(v.button_label);
    setClientSecret("");
  };

  useEffect(() => {
    api
      .get<OidcSettingsStatus>("/api/sso/oidc")
      .then(apply)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load"));
  }, [setError]);

  const payload = () => ({
    enabled,
    discovery_url: discoveryUrl,
    client_id: clientId,
    client_secret: clientSecret || null,
    redirect_uri: redirectUri,
    scopes,
    button_label: label,
  });

  const save = (e: FormEvent) => {
    e.preventDefault();
    setTest(null);
    void run(async () => {
      apply(await api.put<OidcSettingsStatus>("/api/sso/oidc", payload()));
      setNotice(
        enabled
          ? "OIDC settings saved. The sign-in button is now on the login page."
          : "OIDC settings saved. OIDC sign-in is off.",
      );
    });
  };

  const runTest = () =>
    run(async () => {
      setTest(await api.post<OidcTestResult>("/api/sso/oidc/test", payload()));
    });

  const remove = () => {
    if (!confirm("Remove the saved OIDC settings? Azuregos will use the OIDC_* environment variables.")) return;
    setTest(null);
    void run(async () => {
      await api.del("/api/sso/oidc");
      apply(await api.get<OidcSettingsStatus>("/api/sso/oidc"));
      setNotice("Saved OIDC settings removed.");
    });
  };

  const stored = status?.stored;
  const env = status?.environment;
  const secretSaved = !!stored?.client_secret_set;

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <h2 style={{ marginTop: 0 }}>OpenID Connect</h2>
      {error && <div className="alert error">{error}</div>}
      {notice && <div className="alert success">{notice}</div>}
      {status?.error && <div className="alert error">{status.error}</div>}
      {status && <SourceBadge source={status.source} enabled={status.enabled} />}

      {status && (
        <>
          <p className="muted" style={{ marginBottom: 6 }}>Register this with your identity provider:</p>
          <table style={{ marginBottom: 16 }}>
            <tbody>
              <Copyable label="Redirect URI" value={redirectUri || status.default_redirect_uri} />
            </tbody>
          </table>
        </>
      )}

      <form onSubmit={save}>
        <div className="field">
          <EnableToggle checked={enabled} onChange={setEnabled} label="Enable OIDC sign-in" />
        </div>
        <div className="field">
          <label>Discovery URL {enabled && "*"}</label>
          <input
            type="url"
            value={discoveryUrl}
            onChange={(e) => setDiscoveryUrl(e.target.value)}
            placeholder="https://login.microsoftonline.com/<tenant>/v2.0/.well-known/openid-configuration"
            required={enabled}
          />
          <div className="help">The issuer's <code>.well-known/openid-configuration</code> URL.</div>
        </div>
        <div className="field">
          <label>Client ID {enabled && "*"}</label>
          <input value={clientId} onChange={(e) => setClientId(e.target.value)} required={enabled} />
        </div>
        <div className="field">
          <label>Client secret {enabled && !secretSaved && "*"}</label>
          <input
            type="password"
            value={clientSecret}
            onChange={(e) => setClientSecret(e.target.value)}
            placeholder={secretSaved ? "Saved. Leave blank to keep it." : ""}
            autoComplete="new-password"
            required={enabled && !secretSaved}
          />
          <div className="help">Stored encrypted and never shown again.</div>
        </div>
        <div className="field">
          <label>Redirect URI</label>
          <input
            type="url"
            value={redirectUri}
            onChange={(e) => setRedirectUri(e.target.value)}
            placeholder={status?.default_redirect_uri}
          />
          <div className="help">Leave blank to use the default shown above.</div>
        </div>
        <div className="field">
          <label>Scopes</label>
          <input value={scopes} onChange={(e) => setScopes(e.target.value)} />
          <div className="help">Space-separated; must include <code>openid</code>.</div>
        </div>
        <div className="field">
          <label>Button label</label>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Continue with SSO (OIDC)"
            maxLength={100}
          />
        </div>

        {test && (
          <div className={`alert ${test.ok ? "success" : "error"}`}>
            {test.ok
              ? `Discovery document found${test.issuer ? ` for ${test.issuer}` : ""}. The client ID and secret are checked on the first real sign-in.`
              : `Test failed: ${test.error}`}
          </div>
        )}

        <div className="row">
          <button className="btn" disabled={busy}>Save</button>
          <button
            type="button"
            className="btn secondary"
            onClick={runTest}
            disabled={busy || !discoveryUrl}
          >
            Test discovery URL
          </button>
          {stored && (
            <button type="button" className="btn danger" onClick={remove} disabled={busy}>
              Remove saved settings
            </button>
          )}
        </div>
        {stored && (
          <div className="muted" style={{ marginTop: 10, fontSize: 13 }}>
            Last saved {new Date(stored.updated_at).toLocaleString()}
            {stored.updated_by ? ` by ${stored.updated_by}` : ""}.
          </div>
        )}
      </form>

      {env && (
        <EnvTable
          ignored={!!stored}
          rows={[
            ["OIDC_ENABLED", env.enabled ? "true" : "false"],
            ["OIDC_DISCOVERY_URL", env.discovery_url],
            ["OIDC_CLIENT_ID", env.client_id],
            ["OIDC_CLIENT_SECRET", env.client_secret_set ? "set" : ""],
            ["OIDC_REDIRECT_URI", env.redirect_uri],
            ["OIDC_SCOPES", env.scopes],
          ]}
        />
      )}
    </div>
  );
}

// ── SAML ──────────────────────────────────────────────────────────────────
function SamlSection() {
  const [status, setStatus] = useState<SamlSettingsStatus | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [metadataUrl, setMetadataUrl] = useState("");
  const [metadataXml, setMetadataXml] = useState("");
  const [entityId, setEntityId] = useState("azuregos");
  const [acsUrl, setAcsUrl] = useState("");
  const [cert, setCert] = useState("");
  const [key, setKey] = useState("");
  const [emailAttr, setEmailAttr] = useState("");
  const [nameAttr, setNameAttr] = useState("");
  const [label, setLabel] = useState("");
  const [test, setTest] = useState<SamlTestResult | null>(null);
  const { error, setError, notice, setNotice, busy, run } = useRunner();

  const apply = (s: SamlSettingsStatus) => {
    setStatus(s);
    const v = s.stored ?? s.environment;
    setEnabled(v.enabled);
    setMetadataUrl(v.metadata_url);
    setMetadataXml(v.metadata_xml);
    setEntityId(v.sp_entity_id || "azuregos");
    setAcsUrl(v.acs_url);
    setCert(v.sp_x509_cert);
    setEmailAttr(v.email_attribute);
    setNameAttr(v.name_attribute);
    setLabel(v.button_label);
    setKey("");
  };

  useEffect(() => {
    api
      .get<SamlSettingsStatus>("/api/sso/saml")
      .then(apply)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load"));
  }, [setError]);

  const payload = () => ({
    enabled,
    metadata_url: metadataUrl,
    metadata_xml: metadataXml,
    sp_entity_id: entityId,
    acs_url: acsUrl,
    sp_x509_cert: cert,
    sp_private_key: key || null,
    email_attribute: emailAttr,
    name_attribute: nameAttr,
    button_label: label,
  });

  const save = (e: FormEvent) => {
    e.preventDefault();
    setTest(null);
    void run(async () => {
      apply(await api.put<SamlSettingsStatus>("/api/sso/saml", payload()));
      setNotice(
        enabled
          ? "SAML settings saved. The sign-in button is now on the login page."
          : "SAML settings saved. SAML sign-in is off.",
      );
    });
  };

  const runTest = () =>
    run(async () => {
      setTest(await api.post<SamlTestResult>("/api/sso/saml/test", payload()));
    });

  const remove = () => {
    if (!confirm("Remove the saved SAML settings? Azuregos will use the SAML_* environment variables.")) return;
    setTest(null);
    void run(async () => {
      await api.del("/api/sso/saml");
      apply(await api.get<SamlSettingsStatus>("/api/sso/saml"));
      setNotice("Saved SAML settings removed.");
    });
  };

  const stored = status?.stored;
  const env = status?.environment;
  // The saved key is kept only while the certificate stays set.
  const keySaved = !!stored?.sp_private_key_set && !!cert;

  return (
    <div className="card">
      <h2 style={{ marginTop: 0 }}>SAML 2.0</h2>
      {error && <div className="alert error">{error}</div>}
      {notice && <div className="alert success">{notice}</div>}
      {status?.error && <div className="alert error">{status.error}</div>}
      {status && <SourceBadge source={status.source} enabled={status.enabled} />}

      {status && (
        <>
          <p className="muted" style={{ marginBottom: 6 }}>Register this with your identity provider:</p>
          <table style={{ marginBottom: 16 }}>
            <tbody>
              <Copyable label="Entity ID (audience)" value={entityId || "azuregos"} />
              <Copyable label="ACS URL (reply URL)" value={acsUrl || status.default_acs_url} />
            </tbody>
          </table>
        </>
      )}

      <form onSubmit={save}>
        <div className="field">
          <EnableToggle checked={enabled} onChange={setEnabled} label="Enable SAML sign-in" />
        </div>
        <div className="field">
          <label>IdP metadata URL</label>
          <input
            type="url"
            value={metadataUrl}
            onChange={(e) => setMetadataUrl(e.target.value)}
            placeholder="https://login.microsoftonline.com/<tenant>/federationmetadata/2007-06/federationmetadata.xml"
          />
        </div>
        <div className="field">
          <label>IdP metadata XML</label>
          <textarea
            rows={4}
            value={metadataXml}
            onChange={(e) => setMetadataXml(e.target.value)}
            placeholder="<md:EntityDescriptor …>"
            className="mono"
          />
          <div className="help">
            Paste the metadata instead of a URL when the IdP doesn't publish one. The URL wins
            when both are set.
          </div>
        </div>
        <div className="field">
          <label>SP entity ID</label>
          <input value={entityId} onChange={(e) => setEntityId(e.target.value)} />
        </div>
        <div className="field">
          <label>ACS URL</label>
          <input
            type="url"
            value={acsUrl}
            onChange={(e) => setAcsUrl(e.target.value)}
            placeholder={status?.default_acs_url}
          />
          <div className="help">Leave blank to use the default shown above.</div>
        </div>
        <div className="field">
          <label>Email attribute</label>
          <input
            value={emailAttr}
            onChange={(e) => setEmailAttr(e.target.value)}
            placeholder="email, the emailaddress claim, else the NameID"
          />
        </div>
        <div className="field">
          <label>Display name attribute</label>
          <input
            value={nameAttr}
            onChange={(e) => setNameAttr(e.target.value)}
            placeholder="displayName, else the name claim"
          />
        </div>
        <details style={{ marginBottom: 16 }}>
          <summary style={{ cursor: "pointer" }}>Request signing (optional)</summary>
          <div className="field" style={{ marginTop: 10 }}>
            <label>SP certificate (PEM)</label>
            <textarea
              rows={4}
              value={cert}
              onChange={(e) => setCert(e.target.value)}
              className="mono"
              placeholder="-----BEGIN CERTIFICATE-----"
            />
          </div>
          <div className="field">
            <label>SP private key (PEM)</label>
            <textarea
              rows={4}
              value={key}
              onChange={(e) => setKey(e.target.value)}
              className="mono"
              placeholder={keySaved ? "Saved. Leave blank to keep it." : "-----BEGIN PRIVATE KEY-----"}
            />
            <div className="help">
              With both set, sign-in requests are signed. The key is stored encrypted and never
              shown again; clearing the certificate removes it.
            </div>
          </div>
        </details>
        <div className="field">
          <label>Button label</label>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Continue with SSO (SAML)"
            maxLength={100}
          />
        </div>

        {test && (
          <div className={`alert ${test.ok ? "success" : "error"}`}>
            {test.ok
              ? `Metadata read. IdP ${test.idp_entity_id}, sign-on URL ${test.sso_url}.`
              : `Test failed: ${test.error}`}
          </div>
        )}

        <div className="row">
          <button className="btn" disabled={busy}>Save</button>
          <button
            type="button"
            className="btn secondary"
            onClick={runTest}
            disabled={busy || (!metadataUrl && !metadataXml.trim())}
          >
            Test metadata
          </button>
          {stored && (
            <button type="button" className="btn danger" onClick={remove} disabled={busy}>
              Remove saved settings
            </button>
          )}
        </div>
        {stored && (
          <div className="muted" style={{ marginTop: 10, fontSize: 13 }}>
            Last saved {new Date(stored.updated_at).toLocaleString()}
            {stored.updated_by ? ` by ${stored.updated_by}` : ""}.
          </div>
        )}
      </form>

      {env && (
        <EnvTable
          ignored={!!stored}
          rows={[
            ["SAML_ENABLED", env.enabled ? "true" : "false"],
            ["SAML_METADATA_URL", env.metadata_url],
            ["SAML_SP_ENTITY_ID", env.sp_entity_id],
            ["SAML_ACS_URL", env.acs_url],
          ]}
        />
      )}
    </div>
  );
}
