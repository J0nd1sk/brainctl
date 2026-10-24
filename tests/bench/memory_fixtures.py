"""Deterministic fixtures for the memory-quality suites.

Three small, hand-readable fixture sets, one per suite in
``tests.bench.memory_quality``:

* ``DEDUP_PAIRS``   — (first, second) memory writes. ``kind`` says whether the
  second write is a duplicate of the first (``exact`` / ``surface`` /
  ``paraphrase``) or a ``near_miss``: lexically close, but differing in a key
  fact (number, date, entity, polarity, qualifier). Near-miss pairs are both
  true at the same time, so both must stay active after the second write.
* ``TEMPORAL_FACTS`` — a fact written once and then updated one or more
  times. ``versions[-1]`` is the current value; everything before it is stale.
* ``ABSTENTION_CORPUS`` + ``ABSTENTION_QUERIES`` — a small corpus plus queries
  that are either answerable from it (``gold`` set) or not (``gold`` is None).
  Unanswerable queries are deliberately near-topic: they share vocabulary
  with the corpus, so a lexical retriever will still return something.

Like ``fixtures.py`` this module imports nothing from agentmemory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Suite 1 — dedup / pattern separation
# ---------------------------------------------------------------------------

DUPLICATE_KINDS = ("exact", "surface", "paraphrase")
NEAR_MISS_KIND = "near_miss"


@dataclass
class DedupPair:
    key: str
    kind: str          # exact | surface | paraphrase | near_miss
    category: str
    first: str
    second: str
    note: str = ""     # for near_miss: which key fact differs


DEDUP_PAIRS: List[DedupPair] = [
    # --- exact: byte-identical second write ---------------------------------
    DedupPair("exact-uv-lock", "exact", "convention",
              "All Python services pin dependencies with uv lock files checked into the repo",
              "All Python services pin dependencies with uv lock files checked into the repo"),
    DedupPair("exact-ci-image", "exact", "environment",
              "The CI runners use Ubuntu 22.04 with Python 3.11 preinstalled",
              "The CI runners use Ubuntu 22.04 with Python 3.11 preinstalled"),
    DedupPair("exact-review-batching", "exact", "preference",
              "Alice prefers code review comments to be batched into a single pass",
              "Alice prefers code review comments to be batched into a single pass"),
    DedupPair("exact-sentry-route", "exact", "integration",
              "Sentry alerts for the billing service route to the billing-oncall Slack channel",
              "Sentry alerts for the billing service route to the billing-oncall Slack channel"),
    DedupPair("exact-warehouse-db", "exact", "decision",
              "We chose Postgres over MySQL for the analytics warehouse because of JSONB support",
              "We chose Postgres over MySQL for the analytics warehouse because of JSONB support"),
    DedupPair("exact-release-train", "exact", "project",
              "The mobile app release train ships every second Thursday",
              "The mobile app release train ships every second Thursday"),

    # --- surface: same text modulo case / punctuation / whitespace ----------
    DedupPair("surface-redis-case", "surface", "environment",
              "Redis is used as the session cache for the web tier.",
              "redis is used as the session cache for the web tier"),
    DedupPair("surface-flags-punct", "surface", "convention",
              "Feature flags are managed in LaunchDarkly, not in config files",
              "Feature flags are managed in LaunchDarkly -- not in config files!"),
    DedupPair("surface-recon-period", "surface", "project",
              "Bob owns the payments reconciliation job",
              "Bob owns the payments reconciliation job."),
    DedupPair("surface-lint-comma", "surface", "convention",
              "Use ruff for linting and black for formatting",
              "Use ruff for linting, and black for formatting."),
    DedupPair("surface-vpn-caps", "surface", "environment",
              "The VPN must be connected before accessing the internal wiki",
              "THE VPN MUST BE CONNECTED BEFORE ACCESSING THE INTERNAL WIKI"),
    DedupPair("surface-loki-space", "surface", "environment",
              "Logs are retained for 30 days in Loki",
              "Logs are retained  for 30 days in Loki ."),

    # --- paraphrase: same fact, different wording ---------------------------
    DedupPair("para-api-host", "paraphrase", "environment",
              "The deploy target for the API is fly.io",
              "We deploy the API on fly.io"),
    DedupPair("para-search-lead", "paraphrase", "project",
              "Carol is the tech lead for the search team",
              "The search team's tech lead is Carol"),
    DedupPair("para-force-push", "paraphrase", "convention",
              "Never force-push to the main branch",
              "Force-pushing to main is forbidden"),
    DedupPair("para-staging-refresh", "paraphrase", "environment",
              "The staging database is refreshed from a production snapshot every Sunday night",
              "Every Sunday night we refresh the staging database using a snapshot of production"),
    DedupPair("para-dark-mode", "paraphrase", "preference",
              "Dave prefers dark mode in every editor",
              "Dark mode is the theme Dave prefers in all of his editors"),
    DedupPair("para-token-ttl", "paraphrase", "integration",
              "API tokens expire after 24 hours",
              "API tokens are valid for one day before they expire"),
    DedupPair("para-docker-tests", "paraphrase", "environment",
              "Integration tests require Docker to be running locally",
              "You need a local Docker daemon running to run the integration tests"),
    DedupPair("para-frontend-stack", "paraphrase", "project",
              "The frontend is built with Next.js and deployed to Vercel",
              "Our frontend uses Next.js and is hosted on Vercel"),

    # --- near_miss: lexically close, different (co-existing) fact -----------
    DedupPair("near-deploy-target", "near_miss", "environment",
              "The staging deploy target is fly.io",
              "The production deploy target is render",
              note="entity+value"),
    DedupPair("near-rate-limit", "near_miss", "integration",
              "The free plan API rate limit is 100 requests per minute",
              "The pro plan API rate limit is 1000 requests per minute",
              note="entity+number"),
    DedupPair("near-disk-alert", "near_miss", "environment",
              "Page the on-call engineer when disk usage on the database hosts exceeds 80 percent",
              "Page the on-call engineer when disk usage on the database hosts exceeds 95 percent",
              note="number"),
    DedupPair("near-freeze-date", "near_miss", "project",
              "The code freeze for the 4.2 release starts on June 3",
              "The code freeze for the 4.3 release starts on September 9",
              note="date+version"),
    DedupPair("near-retro-day", "near_miss", "project",
              "The platform team runs its sprint retro on Monday afternoons",
              "The data team runs its sprint retro on Friday afternoons",
              note="entity+date"),
    DedupPair("near-oncall-service", "near_miss", "project",
              "Erin is the on-call engineer for the payments service this week",
              "Erin is the on-call engineer for the search service this week",
              note="entity"),
    DedupPair("near-owner", "near_miss", "project",
              "The ingestion pipeline is owned by the data platform team",
              "The ingestion pipeline is owned by the analytics team",
              note="entity"),
    DedupPair("near-timeout", "near_miss", "environment",
              "The default HTTP client timeout in the gateway is 30 seconds",
              "The default HTTP client timeout in the gateway is 30 milliseconds",
              note="unit"),
    DedupPair("near-ledger-polarity", "near_miss", "convention",
              "The payments service should never call the ledger API directly from the request path",
              "The payments service should call the ledger API directly from the request path",
              note="polarity (second is a token subset of the first)"),
    DedupPair("near-eu-polarity", "near_miss", "convention",
              "Customer data from EU accounts must be stored only in the Frankfurt region and never replicated to US regions",
              "Customer data from EU accounts must be stored only in the Frankfurt region and replicated to US regions",
              note="polarity (second is a token subset of the first)"),
    DedupPair("near-backup-qualifier", "near_miss", "convention",
              "Run the database migrations only after the nightly backup job has finished and the restore test has passed",
              "Run the database migrations only after the nightly backup job has finished",
              note="qualifier dropped (second is a token subset of the first)"),
    DedupPair("near-admin-qualifier", "near_miss", "convention",
              "Only admins in the security group can rotate the production signing keys for the release pipeline",
              "Only admins can rotate the production signing keys for the release pipeline",
              note="qualifier dropped (second is a token subset of the first)"),
]


# ---------------------------------------------------------------------------
# Suite 2 — temporal / knowledge update
# ---------------------------------------------------------------------------

@dataclass
class TemporalFact:
    key: str
    category: str
    versions: List[str]               # oldest -> newest; versions[-1] is current
    queries: List[str] = field(default_factory=list)


TEMPORAL_FACTS: List[TemporalFact] = [
    TemporalFact("api-host", "environment",
                 ["The API deploy target is Heroku",
                  "The API deploy target is fly.io",
                  "The API deploy target is Render"],
                 ["Where is the API deployed?", "API deploy target"]),
    TemporalFact("python-version", "environment",
                 ["The backend runs on Python 3.9",
                  "The backend runs on Python 3.11",
                  "The backend runs on Python 3.12"],
                 ["What Python version does the backend run on?"]),
    TemporalFact("primary-datastore", "decision",
                 ["The primary datastore is MySQL",
                  "The primary datastore is Postgres"],
                 ["What is the primary datastore?"]),
    TemporalFact("payments-oncall", "project",
                 ["Alice is the payments on-call engineer",
                  "Bob is the payments on-call engineer",
                  "Carol is the payments on-call engineer"],
                 ["Who is the payments on-call engineer?", "payments on-call"]),
    TemporalFact("v3-launch", "project",
                 ["The v3 launch is scheduled for March 3",
                  "The v3 launch is scheduled for April 14"],
                 ["When is the v3 launch?"]),
    TemporalFact("rate-limit", "integration",
                 ["The public API rate limit is 60 requests per minute",
                  "The public API rate limit is 120 requests per minute"],
                 ["What is the public API rate limit?"]),
    TemporalFact("ci-provider", "environment",
                 ["Continuous integration runs on Travis",
                  "Continuous integration runs on GitHub Actions",
                  "Continuous integration runs on Buildkite"],
                 ["Which continuous integration system do we use?"]),
    TemporalFact("offsite-city", "project",
                 ["The team offsite will be held in Lisbon",
                  "The team offsite will be held in Porto"],
                 ["Where will the team offsite be held?"]),
    TemporalFact("default-branch", "convention",
                 ["The default git branch is master",
                  "The default git branch is main"],
                 ["What is the default git branch?"]),
    TemporalFact("upload-limit", "environment",
                 ["The maximum upload size is 10 MB",
                  "The maximum upload size is 25 MB",
                  "The maximum upload size is 50 MB"],
                 ["What is the maximum upload size?", "upload size limit"]),
    TemporalFact("dana-contact", "preference",
                 ["Dana prefers Slack for urgent questions",
                  "Dana prefers phone calls for urgent questions"],
                 ["How does Dana prefer to get urgent questions?"]),
    TemporalFact("log-retention", "environment",
                 ["Application logs are retained for 14 days",
                  "Application logs are retained for 30 days"],
                 ["How long are application logs retained?"]),
]

# Unrelated background memories so the temporal corpus isn't only the facts.
TEMPORAL_DISTRACTORS: List[tuple] = [
    ("convention", "Pull requests need one approving review before merge"),
    ("environment", "The analytics cluster runs Spark on Kubernetes"),
    ("project", "The onboarding redesign is tracked in the growth roadmap"),
    ("preference", "Frank likes design docs to start with a one-paragraph summary"),
    ("integration", "Stripe webhooks are verified with the signing secret"),
    ("decision", "We picked Grafana over Datadog for dashboards to control cost"),
]


# ---------------------------------------------------------------------------
# Suite 3 — abstention
# ---------------------------------------------------------------------------

@dataclass
class AbstentionQuery:
    text: str
    gold: Optional[str]               # corpus key that answers it, or None
    kind: str                         # answerable | near_topic | off_topic


ABSTENTION_CORPUS: List[tuple] = [
    # (key, category, content)
    ("staging-db-host", "environment", "The staging database host is db-staging.internal on port 5433"),
    ("prod-secrets", "convention", "Production secrets are stored in AWS Secrets Manager under the prod prefix"),
    ("search-standup", "project", "The search team holds standup at 9:30 every weekday"),
    ("frank-typescript", "preference", "Frank prefers TypeScript over plain JavaScript for new frontend code"),
    ("billing-go", "project", "The billing service is written in Go and owned by the payments team"),
    ("backup-bucket", "environment", "Nightly backups of the primary database are written to the S3 bucket acme-db-backups"),
    ("design-system", "project", "The design system lives in the packages/ui directory of the monorepo"),
    ("grace-pm", "project", "Grace is the product manager for the onboarding flow"),
    ("mobile-stack", "project", "The mobile app uses React Native with Expo"),
    ("k8s-terraform", "environment", "Kubernetes clusters are provisioned with Terraform modules in the infra repo"),
    ("checkout-slo", "decision", "The error budget for the checkout API is 99.9 percent monthly availability"),
    ("vite-approval", "decision", "Henry approved the migration from Webpack to Vite in the Q2 planning review"),
    ("zendesk-triage", "integration", "Customer support tickets are triaged in Zendesk by the support rotation"),
    ("warehouse", "environment", "The data warehouse is Snowflake and dbt models run hourly"),
    ("feature-flags", "integration", "Feature flags are managed in LaunchDarkly"),
    ("vpn", "environment", "The company VPN uses WireGuard"),
]

ABSTENTION_QUERIES: List[AbstentionQuery] = [
    # --- answerable ---------------------------------------------------------
    AbstentionQuery("What is the staging database host?", "staging-db-host", "answerable"),
    AbstentionQuery("Where are production secrets stored?", "prod-secrets", "answerable"),
    AbstentionQuery("When does the search team hold standup?", "search-standup", "answerable"),
    AbstentionQuery("Does Frank prefer TypeScript or JavaScript?", "frank-typescript", "answerable"),
    AbstentionQuery("What language is the billing service written in?", "billing-go", "answerable"),
    AbstentionQuery("Which S3 bucket holds the nightly database backups?", "backup-bucket", "answerable"),
    AbstentionQuery("Where does the design system live?", "design-system", "answerable"),
    AbstentionQuery("Who is the product manager for onboarding?", "grace-pm", "answerable"),
    AbstentionQuery("What framework does the mobile app use?", "mobile-stack", "answerable"),
    AbstentionQuery("How are Kubernetes clusters provisioned?", "k8s-terraform", "answerable"),
    AbstentionQuery("What is the error budget for the checkout API?", "checkout-slo", "answerable"),
    AbstentionQuery("Who approved the move to Vite?", "vite-approval", "answerable"),
    AbstentionQuery("What data warehouse do we use?", "warehouse", "answerable"),
    AbstentionQuery("Which tool manages feature flags?", "feature-flags", "answerable"),

    # --- unanswerable, near-topic (shares vocabulary with the corpus) ------
    AbstentionQuery("What is the staging database password?", None, "near_topic"),
    AbstentionQuery("Who is the on-call engineer for the billing service?", None, "near_topic"),
    AbstentionQuery("When does the payments team hold standup?", None, "near_topic"),
    AbstentionQuery("Does Frank prefer tabs or spaces?", None, "near_topic"),
    AbstentionQuery("What port does the production database listen on?", None, "near_topic"),
    AbstentionQuery("How long are nightly backups retained?", None, "near_topic"),
    AbstentionQuery("Who owns the design system's icon set?", None, "near_topic"),
    AbstentionQuery("What analytics SDK does the mobile app use?", None, "near_topic"),
    AbstentionQuery("Which cloud region hosts the Kubernetes clusters?", None, "near_topic"),
    AbstentionQuery("What is the error budget for the search API?", None, "near_topic"),
    AbstentionQuery("Who approved the migration from Jenkins?", None, "near_topic"),
    AbstentionQuery("What is Grace's phone number?", None, "near_topic"),
    AbstentionQuery("How much does the Snowflake contract cost per year?", None, "near_topic"),
    AbstentionQuery("Which Slack channel receives Zendesk escalations?", None, "near_topic"),

    # --- unanswerable, off-topic (control: should be the easy case) -------
    AbstentionQuery("What is the capital of Australia?", None, "off_topic"),
    AbstentionQuery("How do I bake sourdough bread?", None, "off_topic"),
]
