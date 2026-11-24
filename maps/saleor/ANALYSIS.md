# Analysis: Saleor Commerce

Computed from the map (2,120 boxes, 2,763 connections; 2,742 excluding tests and documentation links). Generated with `pipeline/analyze.py`; it reflects the mapping, so verify anything you act on in the code.

## 1. How the applications connect

Connections from one application to another (tests and documentation links excluded), then the parts of the target each one depends on: its integration surface. Parts known only from documents or still unfinished are contract risks: confirm them before building on them.

**Saleor Dashboard → Saleor API**: 294 connections (http 237, calls 51, reads 4, configures 2); 204 parts of Saleor API used.

| Part of Saleor API | Kind | Known from | Status | Used by |
|---|---|---|---|---|
| POST /graphql/ | endpoint | code |  | Catalog and configuration (18), App shell and GraphQL client (5), Orders, customers and promotions (2) |
| App schema | module | code |  | Apps and extensions (7), Catalog and configuration (1) |
| Bulk deletes and stock mutations | module | code |  | Catalog and configuration (6) |
| GraphQL API and platform | group | code |  | Catalog and configuration (5), Orders, customers and promotions (1) |
| accountUpdate (AccountUpdate) | class | code |  | App shell and GraphQL client (3), Apps and extensions (2), Catalog and configuration (1) |
| ShopQueries | class | code |  | App shell and GraphQL client (4), Catalog and configuration (1), Orders, customers and promotions (1) |
| Product schema root | module | code |  | Catalog and configuration (4), App shell and GraphQL client (1) |
| ProductQueries.resolve_products() | function | code |  | App shell and GraphQL client (4), Catalog and configuration (1) |
| ShopSettingsUpdate | class | code |  | Catalog and configuration (2), Orders, customers and promotions (2), App shell and GraphQL client (1) |
| Account schema | module | code |  | Catalog and configuration (2), App shell and GraphQL client (2) |
| ChannelUpdate | class | code |  | Catalog and configuration (2), Orders, customers and promotions (1) |
| Order resolvers | module | code |  | Orders, customers and promotions (3) |
| Voucher mutations | module | code |  | Orders, customers and promotions (3) |
| UpdateMetadata | class | code |  | Orders, customers and promotions (2), App shell and GraphQL client (1) |
| AttributeCreate | class | code |  | Catalog and configuration (1), Orders, customers and promotions (1) |

… and 189 more parts.

**Saleor API → Saleor Apps**: 57 connections (http 57); 41 parts of Saleor Apps used.

| Part of Saleor Apps | Kind | Known from | Status | Used by |
|---|---|---|---|---|
| POST /api/webhooks/order-calculate-taxes | endpoint | code | live | Apps, webhooks and plugins (1), Checkout, payments and tax (1), Orders and fulfilment (1) |
| Saleor Apps | app | code |  | Apps, webhooks and plugins (3) |
| POST /api/webhooks/checkout-calculate-taxes | endpoint | code | live | Apps, webhooks and plugins (1), Checkout, payments and tax (1) |
| POST /api/webhooks/order-confirmed | endpoint | code | live | Apps, webhooks and plugins (1), Orders and fulfilment (1) |
| POST /api/webhooks/order-cancelled | endpoint | code | live | Apps, webhooks and plugins (1), Orders and fulfilment (1) |
| POST /api/webhooks/order-created | endpoint | code | live | Apps, webhooks and plugins (2) |
| POST /api/webhooks/order-fulfilled | endpoint | code | live | Apps, webhooks and plugins (1), Orders and fulfilment (1) |
| POST /api/webhooks/invoice-sent | endpoint | code | live | Apps, webhooks and plugins (1), Orders and fulfilment (1) |
| POST .../saleor/transaction-initialize-session | endpoint | code |  | Apps, webhooks and plugins (1), Checkout, payments and tax (1) |
| POST .../payment-gateway-initialize-session | endpoint | code |  | Apps, webhooks and plugins (1), Checkout, payments and tax (1) |
| POST .../saleor/transaction-process-session | endpoint | code |  | Apps, webhooks and plugins (1), Checkout, payments and tax (1) |
| POST .../saleor/transaction-charge-requested | endpoint | code |  | Apps, webhooks and plugins (1), Checkout, payments and tax (1) |
| POST .../saleor/transaction-refund-requested | endpoint | code |  | Apps, webhooks and plugins (1), Checkout, payments and tax (1) |
| POST .../transaction-cancelation-requested | endpoint | code |  | Apps, webhooks and plugins (1), Checkout, payments and tax (1) |
| POST /api/webhooks/notify | endpoint | code | live | Apps, webhooks and plugins (1) |

… and 26 more parts.

**Saleor Apps → Saleor API**: 44 connections (http 42, calls 2); 16 parts of Saleor API used.

| Part of Saleor API | Kind | Known from | Status | Used by |
|---|---|---|---|---|
| POST /graphql/ | endpoint | code |  | AvaTax tax app (5), Search app (5), SMTP email app (4), Stripe payments app (3) |
| UpdatePrivateMetadata | class | code |  | AvaTax tax app (1), SMTP email app (1), Search app (1) |
| appProblemCreate mutation | class | code |  | AvaTax tax app (1), Search app (1), Shared packages (1) |
| webhookUpdate mutation | class | code |  | Search app (2), Shared packages (1) |
| UpdateMetadata | class | code |  | AvaTax tax app (2) |
| GraphQL API and platform | group | code |  | AvaTax tax app (2) |
| webhookCreate mutation | class | code |  | SMTP email app (1), Shared packages (1) |
| webhookDelete mutation | class | code |  | SMTP email app (1), Shared packages (1) |
| OrderNoteAdd (orderNoteAdd) | class | code |  | AvaTax tax app (1) |
| DeletePrivateMetadata | class | code |  | AvaTax tax app (1) |
| appDeactivate mutation | class | code |  | Search app (1) |
| Channel schema root | module | code |  | Stripe payments app (1) |
| App schema | module | code |  | Stripe payments app (1) |
| TransactionEventReport | class | code |  | Stripe payments app (1) |
| appProblemDismiss mutation | class | code |  | Shared packages (1) |

… and 1 more parts.

**Saleor Dashboard → Saleor Apps**: 4 connections (http 3, configures 1); 2 parts of Saleor Apps used.

| Part of Saleor Apps | Kind | Known from | Status | Used by |
|---|---|---|---|---|
| Saleor Apps | app | code |  | Apps and extensions (3) |
| AvaTax tax app | group | code |  | Catalog and configuration (1) |

## 2. Integration contracts

Every part of one application that another calls, configures or reads, checked against how the target is known. "Not served" means the caller names something the target's code does not declare (the mapping marks such boxes inferred, status unknown); "documents only" means only documents vouch for it. Both fail at run time or are skipped silently, so confirm them first.

Call sites by verdict: served 399.


**Contracts shared by several applications.** Changing one of these breaks more than one caller:

- [POST /graphql/](dist/index.html#nui0jsn) (Saleor API): used by Saleor Apps, Saleor Dashboard, 44 call sites
- [App schema](dist/index.html#n3w97sn) (Saleor API): used by Saleor Apps, Saleor Dashboard, 9 call sites
- [GraphQL API and platform](dist/index.html#n16ps480) (Saleor API): used by Saleor Apps, Saleor Dashboard, 8 call sites
- [Saleor Apps](dist/index.html#n1qq7mly) (Saleor Apps): used by Saleor API, Saleor Dashboard, 6 call sites
- [UpdateMetadata](dist/index.html#ngnzhvd) (Saleor API): used by Saleor Apps, Saleor Dashboard, 5 call sites
- [UpdatePrivateMetadata](dist/index.html#nfj9iqa) (Saleor API): used by Saleor Apps, Saleor Dashboard, 4 call sites
- [webhookUpdate mutation](dist/index.html#n1e6brzd) (Saleor API): used by Saleor Apps, Saleor Dashboard, 4 call sites
- [webhookCreate mutation](dist/index.html#n5dfnsr) (Saleor API): used by Saleor Apps, Saleor Dashboard, 3 call sites
- [webhookDelete mutation](dist/index.html#n10rncj9) (Saleor API): used by Saleor Apps, Saleor Dashboard, 3 call sites
- [OrderNoteAdd (orderNoteAdd)](dist/index.html#n1hxfnmp) (Saleor API): used by Saleor Apps, Saleor Dashboard, 2 call sites
- [appDeactivate mutation](dist/index.html#ngrwif9) (Saleor API): used by Saleor Apps, Saleor Dashboard, 2 call sites
- [Channel schema root](dist/index.html#n1wmc7cv) (Saleor API): used by Saleor Apps, Saleor Dashboard, 2 call sites
- [appProblemDismiss mutation](dist/index.html#n1pe8x3w) (Saleor API): used by Saleor Apps, Saleor Dashboard, 2 call sites

## 3. Capabilities duplicated across applications

Two signals. First, applications that each make their own network calls to the same application or outside service (hosting and databases left out: every application has its own). Second, parts in different applications whose names and summaries describe the same job. Both point at a shared implementation; the second is a text match, so read both boxes before acting.

**Their own client for the same target:**

- **Saleor API**: Saleor Apps through [Encrypted settings manager](dist/index.html#n1iw5eqt), [Webhook GraphQL operations](dist/index.html#n1m0k52i), [Webhook GraphQL operations](dist/index.html#ncelj2g) and 27 more; Saleor Dashboard through [Order GraphQL mutations](dist/index.html#nenf0p1), [Translation GraphQL documents](dist/index.html#nwcvpda), [Shipping GraphQL documents](dist/index.html#n1mhsn1o) and 87 more
- **Saleor Apps**: Saleor API through [Asynchronous webhook transport](dist/index.html#n1pjq6pm), [Synchronous webhook transport](dist/index.html#nck0o2z), [App installation logic](dist/index.html#n15b12vi) and 9 more; Saleor Dashboard through [AppIFrame](dist/index.html#n1v2bkny), [postToExtension()](dist/index.html#nfhhg0o), [New-tab extension actions](dist/index.html#n1007enq)
- **Avalara AvaTax**: Saleor API through [AvaTax request building](dist/index.html#n1eia2kp); Saleor Apps through [AvaTax client](dist/index.html#nuzbqsn), [AvataxEntityTypeMatcher.match()](dist/index.html#n1su9wm9), [Transaction details fetcher](dist/index.html#n1455ke7)
- **Stripe**: Saleor API through [Stripe client calls](dist/index.html#n1rkgf91); Saleor Apps through [StripePaymentIntentsApi](dist/index.html#n19h6wz5), [StripeRefundsApi](dist/index.html#n16u3cx8), [StripeWebhookManager](dist/index.html#nfgbv7j) and 2 more
- **OpenID Connect provider**: Saleor API through [OpenID Connect plugin](dist/index.html#n1gsf355), [OpenID Connect helpers](dist/index.html#n16o2upp); Saleor Dashboard through [Sign-in view](dist/index.html#nd8mzx0)
- **SMTP server**: Saleor API through [send_email()](dist/index.html#nhzmqn5); Saleor Apps through [SmtpEmailSender.sendEmailWithSmtp()](dist/index.html#n1ro0kx4)

**Similar parts in different applications** (text similarity of name and summary):

| Part | Application | Part | Application | Similarity |
|---|---|---|---|---:|
| [Channel mutations](dist/index.html#n16o4z5p) | Saleor API | [Channel GraphQL documents](dist/index.html#nr09h3q) | Saleor Dashboard | 0.56 |
| [Tax configuration and calculation](dist/index.html#n1iptxf5) | Saleor API | [Taxes](dist/index.html#n1y1spro) | Saleor Dashboard | 0.52 |
| [Monorepo root and decisions](dist/index.html#n107c4yr) | Saleor Apps | [Contributor docs and decisions](dist/index.html#n1kmw0sl) | Saleor API | 0.51 |
| [Shipping zones and methods](dist/index.html#nk72tt5) | Saleor API | [Shipping zones and rates](dist/index.html#n15folsx) | Saleor Dashboard | 0.50 |
| [Fulfilment and return mutations](dist/index.html#n4atspf) | Saleor API | [Fulfilment card](dist/index.html#nd2oxal) | Saleor Dashboard | 0.49 |
| [Contributor docs and decisions](dist/index.html#n1kmw0sl) | Saleor API | [Docs and agent guides](dist/index.html#npgkvv7) | Saleor Dashboard | 0.48 |
| [Channel GraphQL documents](dist/index.html#nr09h3q) | Saleor Dashboard | [Channel schema root](dist/index.html#n1wmc7cv) | Saleor API | 0.47 |
| [Monorepo root and decisions](dist/index.html#n107c4yr) | Saleor Apps | [Docs and agent guides](dist/index.html#npgkvv7) | Saleor Dashboard | 0.46 |
| [Email plugins and notifications](dist/index.html#n16af2qh) | Saleor API | [Notifications hub](dist/index.html#nwc7szj) | Saleor Dashboard | 0.45 |
| [Order payment and refund mutations](dist/index.html#n1wu9eqa) | Saleor API | [Placed order sub-view](dist/index.html#nzhnkqp) | Saleor Dashboard | 0.45 |
| [Other variant mutations](dist/index.html#nh1d907) | Saleor API | [Product type GraphQL documents](dist/index.html#n19temkq) | Saleor Dashboard | 0.45 |
| [Discount GraphQL API](dist/index.html#n1plvqkk) | Saleor API | [Discount GraphQL mutations](dist/index.html#n5ybbra) | Saleor Dashboard | 0.45 |
| [Promotions and vouchers](dist/index.html#n1ausfta) | Saleor API | [Discount GraphQL mutations](dist/index.html#n5ybbra) | Saleor Dashboard | 0.44 |
| [Configuration per channel and event](dist/index.html#nhvfaqv) | Saleor Apps | [Email plugins and notifications](dist/index.html#n16af2qh) | Saleor API | 0.44 |
| [Promotions and vouchers](dist/index.html#n1ausfta) | Saleor API | [Discounts and vouchers](dist/index.html#n1yzbcy6) | Saleor Dashboard | 0.43 |

## 4. Coupling between subsystems

Connections from one subsystem to another (tests and documentation links excluded). Two-way pairs depend on each other, which makes them harder to change or deploy separately.

| From | To | Connections | Kinds | Two-way |
|---|---|---:|---|---|
| GraphQL API and platform | Orders and fulfilment | 68 | calls 64, triggers 4 | yes (2 back) |
| Catalog and configuration | Catalog, channels and pricing | 49 | http 49 |  |
| GraphQL API and platform | Apps, webhooks and plugins | 48 | calls 41, triggers 4, reads 3 | yes (29 back) |
| Catalog and configuration | GraphQL API and platform | 45 | http 44, reads 1 |  |
| Orders, customers and promotions | Orders and fulfilment | 39 | http 39 |  |
| GraphQL API and platform | Catalog, channels and pricing | 35 | triggers 14, calls 11, configures 10 | yes (20 back) |
| Apps, webhooks and plugins | GraphQL API and platform | 29 | calls 15, writes 10, reads 4 | yes (48 back) |
| Accounts and authentication | Apps, webhooks and plugins | 27 | calls 27 | yes (5 back) |
| Accounts and authentication | GraphQL API and platform | 25 | calls 22, triggers 3 | yes (13 back) |
| Apps and extensions | Apps, webhooks and plugins | 24 | calls 22, reads 2 |  |
| Checkout, payments and tax | Apps, webhooks and plugins | 23 | calls 17, http 6 | yes (2 back) |
| Stripe payments app | Shared packages | 21 | calls 19, configures 1, reads 1 | yes (2 back) |
| Orders, customers and promotions | Checkout, payments and tax | 21 | http 21 |  |
| Catalog, channels and pricing | GraphQL API and platform | 20 | calls 18, http 1, writes 1 | yes (35 back) |
| Catalog, channels and pricing | Apps, webhooks and plugins | 19 | calls 19 |  |
| GraphQL API and platform | Data and queues | 17 | writes 7, reads 6, configures 3 |  |
| GraphQL API and platform | Checkout, payments and tax | 17 | calls 10, triggers 6, reads 1 | yes (3 back) |
| Orders, customers and promotions | Accounts and authentication | 17 | http 17 |  |
| Orders, customers and promotions | Catalog, channels and pricing | 17 | http 17 |  |
| Checkout, payments and tax | Orders and fulfilment | 16 | calls 8, reads 3, writes 3 | yes (11 back) |
| Orders and fulfilment | Apps, webhooks and plugins | 16 | calls 16 |  |
| Catalog and configuration | Orders and fulfilment | 16 | http 16 |  |
| Apps, webhooks and plugins | Search app | 15 | http 15 | yes (4 back) |
| Orders, customers and promotions | GraphQL API and platform | 14 | http 13, calls 1 |  |
| GraphQL API and platform | Accounts and authentication | 13 | calls 10, configures 1, triggers 1 | yes (25 back) |

## 5. Hubs

Module-level boxes with the most incoming connections (most depended on: changes here ripple) and outgoing connections (depend on the most: hardest to test in isolation).

| Most depended on | In | | Depends on the most | Out |
|---|---:|---|---|---:|
| PluginsManager module | 78 | | POST /graphql/ | 85 |
| POST /graphql/ | 45 | | Asynchronous webhook transport | 56 |
| App mutations | 34 | | Schema root (api.py) | 44 |
| GraphQL API and platform | 22 | | Django settings | 41 |
| Account data model | 22 | | Order GraphQL mutations | 41 |
| Order actions | 21 | | Dashboard entry point | 31 |
| Order GraphQL mutations | 19 | | Order actions | 27 |
| Catalog data model | 18 | | Synchronous webhook transport | 24 |
| Warehouse and stock models | 18 | | Checkout to order conversion | 24 |
| Algolia search provider | 17 | | Account schema | 19 |
| Checkout models | 17 | | GraphQL view | 16 |
| Gift card models | 17 | | Product schema root | 16 |
| Webhook mutations | 16 | | Catalog Celery tasks | 16 |
| Order helpers | 16 | | App mutations | 16 |
| Checkout editing helpers | 16 | | Transaction processing | 15 |

## 6. Outside services

Which subsystems touch each service. A service many subsystems rely on is a single point of failure worth isolating behind one adapter.

| Service | Connections | Subsystems using it |
|---|---:|---|
| PostgreSQL | 30 | GraphQL API and platform (10), Catalog, channels and pricing (5), Accounts and authentication (4), Checkout, payments and tax (4), Apps, webhooks and plugins (4), Orders and fulfilment (3) |
| Amazon DynamoDB | 15 | Stripe payments app (7), AvaTax tax app (3), Shared packages (3), SMTP email app (1), Search app (1) |
| Celery broker | 13 | GraphQL API and platform (4), Catalog, channels and pricing (3), Checkout, payments and tax (2), Apps, webhooks and plugins (2), Accounts and authentication (1), Orders and fulfilment (1) |
| Object storage | 13 | Catalog, channels and pricing (7), GraphQL API and platform (4), Accounts and authentication (1), Apps, webhooks and plugins (1) |
| Redis | 11 | Apps, webhooks and plugins (5), GraphQL API and platform (3), Accounts and authentication (2), Checkout, payments and tax (1) |
| Sentry | 9 | App shell and GraphQL client (2), AvaTax tax app (1), SMTP email app (1), Search app (1), Shared packages (1), Stripe payments app (1) |
| Stripe | 9 | Stripe payments app (6), Checkout, payments and tax (2), GraphQL API and platform (1) |
| Store staff | 8 | AvaTax tax app (2), Orders, customers and promotions (2), SMTP email app (1), Search app (1), GraphQL API and platform (1), App shell and GraphQL client (1) |
| Vercel | 7 | SMTP email app (3), AvaTax tax app (2), Search app (1), Stripe payments app (1) |
| Avalara AvaTax | 7 | AvaTax tax app (6), Checkout, payments and tax (1) |
| OpenID Connect provider | 6 | Accounts and authentication (5), App shell and GraphQL client (1) |
| OpenTelemetry collector | 5 | Apps, webhooks and plugins (2), AvaTax tax app (1), Shared packages (1), GraphQL API and platform (1) |
| Algolia | 4 | Search app (4) |
| SMTP server | 3 | SMTP email app (1), Apps, webhooks and plugins (1), Catalog and configuration (1) |
| Storefronts | 2 | GraphQL API and platform (2) |

## 7. Delivery status by subsystem

Status labels recorded while mapping (only where there was evidence). Partial, stub and planned parts are where build-out work sits.

| Subsystem | live | built | partial | stub | planned |
|---|---:|---:|---:|---:|---:|
| GraphQL API and platform |  |  | 1 |  |  |
| Apps, webhooks and plugins | 20 | 1 | 4 |  |  |
| App shell and GraphQL client | 17 |  |  |  |  |
| AvaTax tax app | 18 |  |  |  |  |
| SMTP email app | 22 |  |  |  |  |
| Search app | 27 |  |  |  |  |
| Apps and extensions | 8 |  |  |  |  |

## 8. Test coverage (from test-to-code connections)

Modules with at least one test file pointing at them or at something inside them. A proxy, not line coverage.

| Subsystem | Modules | With tests | Untested hubs |
|---|---:|---:|---|
| Checkout, payments and tax | 47 | 0 | Gift card mutations, Payment gateway facade, Transaction processing, Checkout events and payment hooks, Checkout editing helpers |
| GraphQL API and platform | 44 | 0 | Core base models, JSON Web Token helpers |
| Apps, webhooks and plugins | 47 | 0 | Plugin HTTP views, PluginsManager module, App schema, App models, Webhook selection queries |
| Catalog, channels and pricing | 58 | 0 | Voucher mutations, Promotion mutations, Promotion engine, Discount data model, Channel mutations |
| Catalog and configuration | 121 | 0 |  |
| Orders and fulfilment | 34 | 0 | Stock management, Order helpers, Order actions |
| Orders, customers and promotions | 103 | 0 | Order GraphQL mutations, Order GraphQL queries |
| Stripe payments app | 36 | 0 |  |
| Accounts and authentication | 28 | 0 | Account notification payloads, Account schema, Permission scope helpers, Shared account mutation bases, Account helpers |
| App shell and GraphQL client | 69 | 0 | User context provider |
| AvaTax tax app | 32 | 0 |  |
| SMTP email app | 15 | 0 | Send-event-messages use case |
| Search app | 13 | 0 | Algolia search provider |
| Apps and extensions | 22 | 0 |  |
| Shared packages | 10 | 0 |  |

## 9. Knowledge gaps

- **Saleor API**: 1150 boxes; 6 known only from documents, 0 inferred. Mapped from source · November 2026
- **Saleor Dashboard**: 511 boxes; 8 known only from documents, 0 inferred. Mapped from source · November 2026
- **Saleor Apps**: 435 boxes; 6 known only from documents, 0 inferred. Mapped from source · November 2026
- **Outside services and people**: 20 boxes; 0 known only from documents, 0 inferred. 

## 10. Findings recorded while mapping (79)

Sentences in the map that describe gaps, drift between documents and code, or likely defects. Picked by keyword, so some are benign; verify before acting.


**Stripe payments app** (13)

- *Transaction recording*: a missing item is an error, not a null, because it means the business flow broke.
- *PaymentGatewayInitializeSessionUseCase.execute()*: A missing configuration answers 400 App is not configured, a storage error 500.
- *OrderCreatedUseCase.execute()*: id equals the app ID) whose pspReference starts with pi_, loads the channel configuration (skips quietly when none) and calls paymentIntents.
- *Stripe webhook route*: Missing header or invalid parameters answer 400 Malformed request before any lookup.
- *Stripe webhook route*: 400 responses: malformed request, app not configured, transaction missing
- *StripeWebhookUseCase.execute()*: Steps: APL lookup by saleorApiUrl (missing answers 400).
- *StripeWebhookManager*: the signing secret is only returned on creation, so a missing one is treated as a panic.
- *saveNewStripeConfig procedure*: Generates a configuration ID, validates the model with placeholder webhook values, calls StripeAuthValidator, then StripeWebhookManager.
- *protectedClientProcedure*: attachAppToken reads saleorApiUrl from the request header and the app token from the APL (401 when missing).
- *OrderSyncInstaller*: a missing permission is always checked again because staff can grant it at any moment.
- *orderSync tRPC router*: enable builds the webhook manifest from APP_API_BASE_URL or the request Origin and maps a missing permission to PRECONDITION_FAILED.
- *Environment schema*: Secret key rotation and stale cleanup variables are merged in from shared schemas (newSecretKeyServerSchema, staleInstallationsCleanupServerSchema).
- … and 1 more

**AvaTax tax app** (9)

- *Committing and voiding transactions*: a missing document maps to a dedicated error.
- *Configuration in Saleor app metadata*: AppMetadataCache keeps the payload's metadata in AsyncLocalStorage for the request so nested reads skip a round trip.
- *Runtime: auth storage, telemetry, problems*: The problem reporter turns recurring failures (invalid credentials, suspicious zero tax, missing channel configuration, invalid address) into Saleor app problems through the shared app-problems package.
- *GraphQL documents, build and docs*: json schedules the stale-installation cron at 03:00 daily and pins regions dub1 and iad1.
- *POST /api/webhooks/checkout-calculate-taxes*: The handler checks the subscription payload for GraphQL errors, extracts the app configuration from the recipient's private metadata (400 if broken), then calls CalculateTaxesUseCase.
- *POST /api/webhooks/order-cancelled*: broken or missing configuration answers 400.
- *ResponseLinesTransformer.transform()*: Missing numeric fields throw TaxBadPayloadError.
- *getAppConfig()*: Entries matching neither, such as the tax-code map, are ignored.
- *App problem reporter*: Keys include invalid credentials, forbidden access, company inactive or not found, entity not found, suspicious zero tax, tax-code permission, channel configuration missing and invalid address.

**Checkout, payments and tax** (9)

- *CheckoutShippingAddressUpdate*: Because tax and shipping depend on the address, it marks deliveries stale, calls invalidate_checkout and sends CHECKOUT_UPDATED.
- *CheckoutDeliveryMethodUpdate*: A shipping method must match a valid CheckoutDelivery row (fetched again if stale);
- *Checkout.is_checkout_locked()*: seconds, which ignores whole days, so a completion that started more than a day ago and never cleared can look locked again for a few minutes each day.
- *Checkout problems*: get_checkout_problems adds checkout-level problems: the assigned delivery is stale or no longer valid.
- *Checkout price calculation*: Results are written in a transaction that locks the checkout and compares last_change, so a concurrent edit wins over a stale calculation.
- *Tax configuration resolution*: A missing strategy falls back to FLAT_RATES;
- *Tax webhook dispatch*: a missing app or webhook rejects with TaxDataError.
- *AvaTax plugin hooks*: Each price hook skips when the plugin is inactive, the strategy is FLAT_RATES, or tax_app_id names something else.
- *api_post_request()*: Its error branch tests whether the text error is in the requests Response object rather than in the decoded JSON, so that branch never runs and error replies are returned without the intended log line.

**Orders, customers and promotions** (7)

- *Send refund for granted refund*: If the granted refund is already tied to a transaction, the server ignores the transaction identifier sent here.
- *Order details toasts*: Fulfilment approve skips the toast when every error is INSUFFICIENT_STOCK, because the dialog itself offers to exceed stock.
- *Draft orders*: Finalize errors are filtered so missing-address or missing-shipping errors disappear once the data is filled in.
- *Grant refund view (older page)*: Skips the call when no line, no amount and no shipping were chosen.
- *submitOrderSettingsForm()*: Skips the shop update when nothing changed or the user lacks MANAGE_SETTINGS, and channel updates when the user cannot update channels.
- *Issue gift card dialog*: Ignores close while the mutation runs, and shows the generated code on success so staff can copy it.
- *toAPI() and mapAPIRuleToForm()*: the code notes a parsing schema is still missing.

**Catalog and configuration** (6)

- *Product setup and availability diagnostics*: The setup card turns form drafts and channel diagnostics into a readiness record (channel, category, price, stock, published) and deep-links to the missing step.
- *getProductSetupReadiness()*: Missing diagnostics never block.
- *fetchPublicApiProductCheck()*: A missing product on the first page means it is not visible in that channel;
- *Variants*: The generator builds every combination of chosen selection attribute values, skips existing ones and stages them as bulk create inputs.
- *buildChannelCreateInput()*: A duplicate copies those settings and the warehouse and zone assignments, but not the catalog or tax configuration, and sets isActive false so the copy is not live by accident.
- *useBulkPublishToChannelSubmit()*: Loads the products in one query (at most 50), skips any without a category when publishing, then sends productChannelListingUpdate with the chosen published, visible and purchasable flags.

**Accounts and authentication** (5)

- *store_user_address()*: Skips silently when the user already has MAX_USER_ADDRESSES addresses (default 100).
- *Address validation mixin*: SKIP_ADDRESS_VALIDATION_PERMISSION_MAP names mutations across areas (customer, order, warehouse, shop, checkout and account) and the permissions required to skip validation for each.
- *requestPasswordReset*: A missing or invalid channel is ignored for the same reason.
- *userBulkSetActive*: Needs only MANAGE_USERS and does not distinguish staff from customers, so it skips the MANAGE_STAFF scope and last-manager checks staffUpdate applies.
- *create_permissions()*: auth is an empty placeholder kept for migrations.

**Apps, webhooks and plugins** (5)

- *Immediate subscription deliveries*: Skips a delivery when the pre-save payload equals the new one and ENABLE_LIMITING_WEBHOOKS_FOR_IDENTICAL_PAYLOADS is on
- *generate_deferred_payloads task*: deliveries missing while others are present are re-queued separately.
- *Transaction answer schemas*: TransactionBaseSchema defines the common fields: psp reference, amount, time (defaults to now), external URL, message and actions, with lenient defaults for missing values.
- *Stored payment method schemas*: Schemas for stored payment methods carry id, supported flows, type, name, data and optional credit card details, and skip individual invalid methods with a logged message instead of rejecting the list.
- *BasePlugin*: Hooks are declared as annotations, not methods, so a plugin implements only what it needs and the manager skips the rest.

**SMTP email app** (4)

- *POST /api/cron/cleanup-stale-installations*: It passes the main DynamoDB table so stale records are deleted there.
- *Send-event-messages use case*: ClientError covers template compilation, missing sender and token rejection;
- *SMTP configuration service*: A rejected app token is surfaced as AppTokenRejectedError so the webhook does not retry a broken installation.
- *App configuration router*: The appPermissions query fetches the app's granted permissions from Saleor so the pages can warn when a permission is missing.

**Search app** (4)

- *createWebhookContext()*: A missing appConfig throws AppNotConfiguredError, which the handlers turn into a 400.
- *AlgoliaSearchProvider.#saveProductVariant()*: The guard if (staleIndices) tests an array, which is always truthy, so a delete call is issued even when there is nothing stale (an empty batch).
- *productAndVariantToAlgolia()*: A comment marked BUG in the code notes that variant pricing is null in webhook payloads (no channel context), so webhook updates empty the pricing fields that a bulk import filled.
- *Environment schema*: MANIFEST_APP_ID is declared but never read

**GraphQL API and platform** (4)

- *load_user_from_request()*: Third-party access tokens issued for apps and app extensions skip the password login restriction.
- *Patched Site.objects.get_current()*: The cache is cleared only by clear_cache(), so values can be stale after a save in the same process, as AGENTS.
- *SENTRY_INIT()*: Graphql executor loggers are ignored
- *Database expressions and fields*: py adds search vector expressions that skip Django's validation for speed.

**App shell and GraphQL client** (4)

- *Error tracking*: The Sentry adapter ignores three noisy browser and editor errors, samples 10 percent of traces and sets the user name to the API hostname so events group per store.
- *App layout*: The fullSize prop is declared and passed from the routes but never read.
- *Selected channel context*: When it is missing or not in the user's accessibleChannels it is reset to the first accessible channel.
- *Home page*: While extensions load and no non-empty snapshot exists it renders a blank box, so the empty state never doubles as a placeholder.

**Catalog, channels and pricing** (3)

- *Discounted price calculator*: Changed rows are bulk-updated, listing-to-rule rows created or updated, stale ones deleted, and a list of price changes is returned for webhooks.
- *Move attribute files command*: missing objects are logged and skipped.
- *Attribute input assignment*: save runs pre_save_values to create missing AttributeValue rows in bulk, associates them with the instance, clears assignments for attributes sent with no values and deletes values owned only by this instance (for example rich text) that are no longer used.

**Shared packages** (2)

- *@saleor/webhook-utils*: Webhooks are matched by name: manifests with no existing webhook are created, matches are updated, existing ones missing from the manifest list are removed.
- *cleanupStaleInstallations()*: Returns HTTP-style status and body for the route: 201 Not configured when variables are missing, 502 when Saleor Cloud cannot be asked, 500 when every checked installation would be deleted (a sign SALEOR_CLOUD_API_URL is wrong), 200 with counts otherwise.

**Orders and fulfilment** (2)

- *Order status and event constants*: StockUpdatePolicy (skip, update, force) controls stock handling in bulk order import.
- *Stock domain*: py cleans up allocations and reservations and repairs quantity_allocated drift.

**Apps and extensions** (2)

- *Installation tracker*: Pending installations found on the server but missing locally are added, so installs started elsewhere are tracked too.
- *useAppActions()*: actionId (for example from browser extensions) are ignored.

## 11. Build-out candidates

Ranked by how much of the system leans on them. These are prompts for a review, not decisions; `BUILDOUT.md` turns them, with the contract and duplication findings above, into a draft plan.

**Unfinished parts with the most dependents** (partial, stub or planned):

- Legacy payload generators (partial, 3 incoming): Hand-built JSON payloads for webhooks without a subscription query, plus sample payloads and transaction request payloads.
- Legacy payment answer parsers (partial, 2 incoming): Parses answers to the legacy payment webhooks: the gateway list for PAYMENT_LIST_GATEWAYS and gateway responses for authorize, capture and refund.
- BaseMutation.check_metadata_permissions() (partial, 1 incoming): Looks up the metadata permission function for the object's type, raising NotImplementedError for an unknown type.
- WebhookPlugin.__run_payment_webhook() (partial, 0 incoming): Legacy payment flow: sends authorize, capture, refund, void, confirm or process to the gateway's app and parses the gateway response.
- WebhookPlugin.get_payment_gateways() (partial, 0 incoming): Calls every app's PAYMENT_LIST_GATEWAYS webhook and collects the gateways it returns, with app-prefixed gateway ids.

**Two-way dependencies between subsystems** (candidates for a clearer interface):

- GraphQL API and platform ↔ Apps, webhooks and plugins: 48 one way, 29 back
- GraphQL API and platform ↔ Orders and fulfilment: 68 one way, 2 back
- GraphQL API and platform ↔ Catalog, channels and pricing: 35 one way, 20 back
- Accounts and authentication ↔ GraphQL API and platform: 25 one way, 13 back
- Accounts and authentication ↔ Apps, webhooks and plugins: 27 one way, 5 back
- Checkout, payments and tax ↔ Orders and fulfilment: 16 one way, 11 back
- Checkout, payments and tax ↔ Apps, webhooks and plugins: 23 one way, 2 back
- Shared packages ↔ Stripe payments app: 2 one way, 21 back
- GraphQL API and platform ↔ Checkout, payments and tax: 17 one way, 3 back
- Search app ↔ Apps, webhooks and plugins: 4 one way, 15 back

**Heavily used modules with no test pointing at them:**

- PluginsManager module (78 incoming)
- Account data model (22 incoming)
- Order actions (21 incoming)
- Order GraphQL mutations (19 incoming)
- Catalog data model (18 incoming)
- Algolia search provider (17 incoming)
- Order helpers (16 incoming)
- Checkout editing helpers (16 incoming)
- Discount data model (15 incoming)
- Promotion engine (15 incoming)
