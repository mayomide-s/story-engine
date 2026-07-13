import type { ReactNode } from "react";
import { Link } from "react-router-dom";

type PublicLayoutProps = {
  eyebrow: string;
  title: string;
  intro: string;
  children: ReactNode;
  draftNotice?: boolean;
};

const PUBLIC_NAV_ITEMS = [
  { href: "/", label: "Home" },
  { href: "/privacy", label: "Privacy Policy" },
  { href: "/terms", label: "Terms of Service" },
  { href: "/data-deletion", label: "Data Deletion" },
];

function PublicLayout({ eyebrow, title, intro, children, draftNotice = false }: PublicLayoutProps) {
  return (
    <div className="public-shell">
      <header className="public-header">
        <div className="public-header-inner">
          <div className="public-brand">
            <p className="eyebrow">Story Engine</p>
            <Link className="public-brand-link" to="/">
              Story Engine
            </Link>
            <p className="subtle">Operated by Mayo Soremekun</p>
          </div>
          <nav className="public-nav" aria-label="Public pages">
            {PUBLIC_NAV_ITEMS.map((item) => (
              <Link key={item.href} to={item.href}>
                {item.label}
              </Link>
            ))}
            <Link className="public-app-link" to="/app">
              Open Story Engine
            </Link>
          </nav>
        </div>
      </header>

      <main className="public-main">
        <section className="public-hero panel">
          <p className="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
          <p className="public-intro">{intro}</p>
          {draftNotice ? (
            <div className="notice-card warning public-draft-notice">
              <strong>Operational draft</strong>
              <p>
                Operational draft {"\u2014"} pending legal review. This page is provided
                for operational transparency and is not legal advice.
              </p>
            </div>
          ) : null}
        </section>

        <div className="public-content">{children}</div>
      </main>

      <footer className="public-footer">
        <div className="public-footer-grid">
          <div className="public-footer-block">
            <strong>Story Engine</strong>
            <p>Operated by Mayo Soremekun</p>
            <p>
              Support and security contact:{" "}
              <a href="mailto:mayomide.sore@outlook.com">mayomide.sore@outlook.com</a>
            </p>
          </div>
          <div className="public-footer-block">
            <strong>Public pages</strong>
            <div className="public-footer-links">
              {PUBLIC_NAV_ITEMS.map((item) => (
                <Link key={item.href} to={item.href}>
                  {item.label}
                </Link>
              ))}
            </div>
          </div>
          <div className="public-footer-block">
            <strong>Application</strong>
            <p>Story Engine is intended to be publicly available to paying customers.</p>
            {draftNotice ? (
              <p>Operational draft {"\u2014"} pending legal review.</p>
            ) : (
              <p>Users approve publishing actions directly in the app.</p>
            )}
          </div>
        </div>
      </footer>
    </div>
  );
}

function PublicSection({
  heading,
  children,
}: {
  heading: string;
  children: ReactNode;
}) {
  return (
    <section className="panel public-panel">
      <h2>{heading}</h2>
      <div className="public-copy">{children}</div>
    </section>
  );
}

export function PublicHomePage() {
  return (
    <PublicLayout
      eyebrow="Public overview"
      title="Create, review, and approve short-form videos before they publish."
      intro="Story Engine helps users create, review, and publish approved short-form video content to connected social channels while keeping the user in control of each publishing action."
    >
      <PublicSection heading="What Story Engine does">
        <p>
          Story Engine is a self-hosted workflow for preparing short-form videos,
          reviewing the exact final asset, and publishing approved content to
          connected channels such as YouTube.
        </p>
        <p>
          Connected YouTube access is used only for approved actions. Users review
          the exact video, choose the target connection, approve the publication
          step, and can later disconnect YouTube from within Story Engine.
        </p>
      </PublicSection>

      <PublicSection heading="Key points">
        <ul className="public-list">
          <li>Users remain in control of publishing and must explicitly approve publication actions.</li>
          <li>Story Engine is intended to be publicly available to paying customers.</li>
          <li>The current pricing concept is a planned or indicative {"\u00A3"}159 per month, not a live billing flow.</li>
          <li>Users can disconnect connected accounts, and local encrypted OAuth tokens are removed on disconnect.</li>
          <li>Users can delete their Story Engine account in Settings, but already-uploaded YouTube videos remain under the user's control on YouTube.</li>
        </ul>
      </PublicSection>

      <PublicSection heading="Publishing controls">
        <p>
          Story Engine helps users connect YouTube through OAuth, review
          platform-specific publication details, and approve the exact publication
          action before upload. Story Engine does not claim unattended publishing
          approval on behalf of the user.
        </p>
        <p>
          Users may also revoke Story Engine access separately through their Google
          account if they no longer want the application to retain that connection.
        </p>
      </PublicSection>

      <section className="panel public-panel">
        <h2>Links</h2>
        <div className="public-link-grid">
          <Link className="public-cta" to="/app">
            Open Story Engine
          </Link>
          <Link className="public-cta" to="/privacy">
            Privacy Policy
          </Link>
          <Link className="public-cta" to="/terms">
            Terms of Service
          </Link>
          <Link className="public-cta" to="/data-deletion">
            Data Deletion
          </Link>
          <a className="public-cta" href="mailto:mayomide.sore@outlook.com">
            Contact Support
          </a>
        </div>
      </section>
    </PublicLayout>
  );
}

export function PublicPrivacyPage() {
  return (
    <PublicLayout
      eyebrow="Privacy policy"
      title="Story Engine Privacy Policy"
      intro="This operational privacy draft explains how Story Engine handles account, connection, publishing, and deletion data based on the system currently implemented."
      draftNotice
    >
      <PublicSection heading="Operator and scope">
        <p>
          Story Engine is operated by Mayo Soremekun. This policy applies to Story
          Engine account access, connected social channels, publication records,
          and related operational data handled by the application.
        </p>
        <p>
          It covers Story Engine itself and does not replace the terms or policies
          of connected third-party providers such as Google or YouTube.
        </p>
      </PublicSection>

      <PublicSection heading="Data users provide">
        <p>
          Users may provide account details, publishing metadata, video content,
          captions, titles, descriptions, hashtags, operational settings, and
          support correspondence.
        </p>
        <p>
          Story Engine also stores publication records, audit events, and other
          workflow metadata needed to execute, recover, review, and explain
          publishing activity.
        </p>
      </PublicSection>

      <PublicSection heading="Google and YouTube account data">
        <p>
          When a user connects YouTube, Story Engine stores connection details and
          locally stored OAuth tokens needed to refresh access and perform approved
          publishing actions.
        </p>
        <p>
          OAuth tokens are encrypted at rest. Story Engine uses connected YouTube
          access only for approved actions supported by the application's
          implemented publishing flow.
        </p>
      </PublicSection>

      <PublicSection heading="How data is used">
        <p>
          Story Engine uses account, media, and publishing data to prepare videos,
          support user review, execute approved publication actions, recover safely
          from interrupted publication attempts, and provide operational
          auditability.
        </p>
        <p>
          Users remain responsible for approving publishing actions. Story Engine
          does not claim that connected access gives it broad permission to publish
          without a user's approval inside the product workflow.
        </p>
      </PublicSection>

      <PublicSection heading="Disconnecting YouTube and revoking access">
        <p>
          Users can disconnect YouTube from Story Engine. When a YouTube
          connection is disconnected, the locally stored encrypted OAuth tokens are
          removed from Story Engine and the connection is disabled for future
          refresh or publishing.
        </p>
        <p>
          Users may also revoke Story Engine access through Google. Google-side
          revocation is separate from Story Engine's local disconnection flow.
        </p>
      </PublicSection>

      <PublicSection heading="Account deletion">
        <p>
          Users can delete their Story Engine account through Settings. Account
          deletion removes or anonymises account-owned data, disables account
          access, disconnects social connections, and clears locally stored
          encrypted OAuth tokens.
        </p>
        <p>
          Account deletion does not automatically delete videos already uploaded to
          YouTube. Users must remove those videos on YouTube separately if they
          want them taken down.
        </p>
      </PublicSection>

      <PublicSection heading="Data retention">
        <p>
          Personal and operational data is generally retained for no longer than
          12 months after it is no longer required.
        </p>
        <p>
          Limited records may be retained temporarily where genuinely needed for
          security, fraud prevention, payment disputes, or legal obligations.
          Story Engine does not promise a fixed incident-response time.
        </p>
      </PublicSection>

      <PublicSection heading="Third-party services, sharing, and international processing">
        <p>
          Story Engine may rely on third-party infrastructure or connected
          platforms to provide storage, publishing, or authentication
          capabilities. Data shared with those systems is limited to what is
          needed for the implemented workflow.
        </p>
        <p>
          Story Engine does not claim broad legal compliance beyond the
          implemented operational controls described here, and international
          processing implications remain subject to later legal review.
        </p>
      </PublicSection>

      <PublicSection heading="Security, rights, and updates">
        <p>
          Story Engine uses local access controls, encrypted token storage, and
          operational logging to protect connected publishing data. No fixed
          incident-response time is promised.
        </p>
        <p>
          Users can contact the operator regarding privacy questions, request
          disconnection, and request account deletion. This policy may be updated
          as the product evolves or after legal review.
        </p>
        <p>
          Contact:{" "}
          <a href="mailto:mayomide.sore@outlook.com">mayomide.sore@outlook.com</a>
        </p>
      </PublicSection>
    </PublicLayout>
  );
}

export function PublicTermsPage() {
  return (
    <PublicLayout
      eyebrow="Terms of service"
      title="Story Engine Terms of Service"
      intro="These operational draft terms describe the current service expectations for Story Engine. They are provided for review readiness and are not legal advice."
      draftNotice
    >
      <PublicSection heading="Service description and operator">
        <p>
          Story Engine is operated by Mayo Soremekun. It helps users create,
          review, and publish approved short-form videos to connected social
          channels such as YouTube.
        </p>
        <p>
          The product is intended to become publicly available to paying customers,
          but pricing, billing, and refund mechanics are not yet implemented in
          the live application.
        </p>
      </PublicSection>

      <PublicSection heading="Eligibility and account responsibility">
        <p>
          Users are responsible for the security of their Story Engine account,
          for the accuracy of the data they provide, and for controlling access to
          connected third-party services.
        </p>
        <p>
          Users are also responsible for ensuring they have the rights,
          permissions, and platform authority needed to upload, publish, and
          distribute their content.
        </p>
      </PublicSection>

      <PublicSection heading="Connected third-party services and publishing authorisation">
        <p>
          Story Engine may connect to YouTube and other supported services through
          official provider flows. Users approve publishing actions inside Story
          Engine before the application submits the requested upload.
        </p>
        <p>
          Users can disconnect YouTube through Story Engine. Local encrypted OAuth
          tokens are removed on disconnect, and users may also revoke Story Engine
          access through Google separately.
        </p>
      </PublicSection>

      <PublicSection heading="Content, permissions, and prohibited use">
        <p>
          Users retain responsibility for the content they create, upload, or
          publish through Story Engine, including compliance with platform rules,
          laws, and third-party rights.
        </p>
        <p>
          Users must not use Story Engine to submit unlawful, deceptive, abusive,
          infringing, or unauthorised content, or to circumvent provider
          restrictions, quotas, or API rules.
        </p>
      </PublicSection>

      <PublicSection heading="Availability, interruptions, and suspension">
        <p>
          Story Engine may experience errors, interruptions, delayed processing,
          or connected-provider failures. Story Engine does not promise
          uninterrupted availability.
        </p>
        <p>
          The operator may suspend or limit access where necessary to protect the
          service, investigate misuse, respond to provider restrictions, or
          address security concerns.
        </p>
      </PublicSection>

      <PublicSection heading="Disconnection, deletion, and termination">
        <p>
          Users may disconnect a connected YouTube account or delete their Story
          Engine account. Account deletion removes or anonymises account-owned
          Story Engine data and prevents automatic account restoration.
        </p>
        <p>
          Deleting a Story Engine account does not automatically delete YouTube
          videos that were already uploaded. Those uploads remain under the user's
          control on YouTube.
        </p>
      </PublicSection>

      <PublicSection heading="Planned paid access, refunds, and legal review">
        <p>
          Story Engine is being prepared for paying customers, but billing and
          refunds are not yet implemented in the live product.
        </p>
        <p>
          Any limitation-of-liability, disclaimer, or refund wording remains
          pending legal review and should not be treated as final legal text yet.
        </p>
      </PublicSection>

      <PublicSection heading="Governing law and contact">
        <p>
          Governing-law wording for the Federal Republic of Nigeria is pending
          legal review and may change before production launch.
        </p>
        <p>
          Contact:{" "}
          <a href="mailto:mayomide.sore@outlook.com">mayomide.sore@outlook.com</a>
        </p>
      </PublicSection>
    </PublicLayout>
  );
}

export function PublicDataDeletionPage() {
  return (
    <PublicLayout
      eyebrow="Data deletion"
      title="Account and data deletion instructions"
      intro="This public page explains how a Story Engine user can delete their account, what that deletion does, and what remains under the user's control on YouTube."
    >
      <PublicSection heading="Delete your account in Story Engine">
        <ol className="public-steps">
          <li>Sign in to Story Engine.</li>
          <li>Open Settings.</li>
          <li>Open the danger zone.</li>
          <li>Choose Delete account.</li>
          <li>Review the deletion preview.</li>
          <li>Enter the required password where enabled.</li>
          <li>Type <code>DELETE MY ACCOUNT</code>.</li>
          <li>Acknowledge that uploaded YouTube videos remain online.</li>
          <li>Confirm deletion.</li>
        </ol>
      </PublicSection>

      <PublicSection heading="What deletion does">
        <ul className="public-list">
          <li>Disables Story Engine account access.</li>
          <li>Invalidates active application access.</li>
          <li>Disconnects social accounts.</li>
          <li>Clears locally stored encrypted OAuth tokens.</li>
          <li>Deletes or anonymises account-owned publishing and content data.</li>
          <li>Prevents automatic account restoration.</li>
        </ul>
      </PublicSection>

      <PublicSection heading="What deletion does not do">
        <ul className="public-list">
          <li>It does not automatically delete videos already uploaded to YouTube.</li>
          <li>It does not automatically revoke provider access through Google.</li>
          <li>Users may revoke Story Engine separately from their Google account.</li>
        </ul>
      </PublicSection>

      <PublicSection heading="Manual support route">
        <p>
          If you cannot access your account, you may email{" "}
          <a href="mailto:mayomide.sore@outlook.com">mayomide.sore@outlook.com</a>{" "}
          for help.
        </p>
        <p>
          Identity verification may be required before account-deletion assistance
          is provided. Story Engine does not promise a fixed deletion-response
          deadline.
        </p>
      </PublicSection>
    </PublicLayout>
  );
}
