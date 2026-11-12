# Security Policy

## 1. Purpose and Scope

This repository is used to build agentic AI applications during the Imperial AI Hackathon.

Security is a core engineering requirement, but safeguards should be proportionate to the project's scope and development timeline.

These guidelines apply to all contributors, AI coding agents, API integrations, frontend components, backend services, and deployment environments.

Prioritise vulnerabilities that could expose sensitive information, compromise external systems, enable unauthorised actions, or break critical functionality.

This policy supplements `AGENTS.md` and `docs/COLLABORATION.md`.

## 2. Secrets and Credentials

- Never commit API keys, authentication tokens, passwords, private keys, or `.env.local` files.
- Store secrets in local environment variables or the deployment platform's secret management system.
- Never expose secrets using `NEXT_PUBLIC_*` environment variables.
- Never include credentials in logs, error messages, screenshots, prompts, or AI-generated responses.
- Use the minimum permissions required for each external integration.
- If a credential is exposed, revoke or rotate it immediately. Removing it from the latest commit is not sufficient.

## 3. API and Backend Security

All server-side endpoints must:

- Validate untrusted inputs, including types, structure, size, and permitted values.
- Return appropriate HTTP status codes without exposing internal implementation details.
- Handle malformed requests, unexpected responses, timeouts, and upstream failures.
- Enforce authentication and authorisation where required by the application.
- Apply rate limiting, resource limits, or other abuse protections where justified.
- Never trust client-side validation as a substitute for server-side checks.

External APIs must be called through trusted server-side integrations when credentials are required.

## 4. AI and Agent Security

AI-generated outputs, retrieved documents, external websites, tool responses, and user-supplied instructions must be treated as untrusted.

- Defend against prompt injection, including attempts to override system instructions or manipulate agent behaviour.
- Never interpret retrieved content or model-generated text as authorisation to execute privileged actions.
- Restrict agent tools to the minimum files, services, and operations required.
- Validate tool arguments before execution.
- Require explicit human approval for destructive, irreversible, financially consequential, or externally impactful actions.
- Avoid unrestricted shell execution, arbitrary code execution, and unrestricted filesystem access.
- Never allow model output alone to authorise access to sensitive information.

Where practical, separate AI reasoning, tool execution, and validation into distinct components.

## 5. Data Protection and Privacy

- Collect and retain only the information necessary for the product's functionality.
- Avoid using real sensitive personal information in demonstrations.
- Prefer synthetic, anonymised, or consented test data.
- Do not log access tokens, credentials, private records, or complete sensitive user inputs.
- Protect data in transit using HTTPS for deployed services.
- Configure access controls where persistent storage is introduced.
- Define appropriate deletion and retention behaviour if user data is stored.

## 6. Dependencies and Supply Chain

- Prefer existing project dependencies before introducing new packages.
- Review new dependencies for maintenance, security advisories, and unnecessary functionality.
- Use the committed `package-lock.json` and reproducible installations with `npm ci`.
- Investigate relevant dependency vulnerabilities before deployment.
- Avoid executing untrusted installation scripts or downloaded code without review.

Only the designated repository owner should coordinate dependency changes, consistent with `docs/COLLABORATION.md`.

## 7. GitHub and Collaboration Security

- Develop on feature branches; never push directly to `main`.
- Use pull requests for all changes to protected branches.
- Review code changes and GitHub Actions results before merging.
- Preserve ownership boundaries for shared files and integration contracts.
- Do not force-push shared branches or use destructive Git operations.
- Keep repository, deployment, and third-party permissions limited to what contributors require.
- Never approve or merge a change solely because it was generated or reviewed by AI.

## 8. Deployment Security

Before deploying or demonstrating the application:

- Confirm no secrets are exposed in client bundles or publicly accessible files.
- Configure production environment variables separately from local development.
- Verify that API endpoints enforce appropriate validation and permissions.
- Check external integrations for unexpected behaviour and failure handling.
- Ensure debug endpoints and development-only functionality are not unnecessarily exposed.
- Verify the live application behaves safely when external services fail.

## 9. Security Review Priorities

Codex and human reviewers should prioritise findings using the following severity guidance.

| Severity | Examples | Expected action |
|---|---|---|
| Critical | Exposed production credentials, unauthorised privileged execution, severe data exposure | Block merge; address immediately |
| High | Authentication bypass, exploitable injection, unrestricted dangerous tools, significant sensitive-data leakage | Fix before merge |
| Medium | Missing security-relevant validation, meaningful abuse risks, unsafe error handling, insufficient permissions | Fix before deployment where applicable |
| Low | Minor hardening improvements without a demonstrated meaningful impact | Document or defer appropriately |

Review findings should identify the affected file or code location, explain a plausible impact, and recommend a concrete remediation.

Avoid speculative vulnerabilities, duplicated lint findings, and low-value security warnings.

A passing security review does not guarantee the absence of vulnerabilities.

## 10. Reporting Vulnerabilities

Security concerns should be reported privately to the repository maintainers.

Do not publish exploit details, credentials, or sensitive information in public GitHub Issues.

Where GitHub private vulnerability reporting is enabled, use the repository's private reporting mechanism. Otherwise, contact a maintainer privately through an agreed team communication channel.

The maintainers will assess the report, prioritise remediation according to severity, and coordinate any necessary credential rotation or disclosure.

## 11. Product-Specific Threat Modelling

The final product, sponsor track, APIs, data sources, and agent capabilities will be selected during the hackathon.

Once the architecture is agreed, review:

- Assets and sensitive information that require protection.
- Trust boundaries between the browser, backend, AI model, tools, and external services.
- Potential attackers and misuse scenarios.
- High-risk agent actions and required human approvals.
- Authentication, data storage, and external API risks.
- Practical mitigations and residual risks.

Record a product-specific threat model in `docs/threat-model.md` if the application warrants one.

Until then, this document establishes baseline security expectations without assuming a particular product architecture.

---

**Security principle:** Build quickly, restrict privileges, validate untrusted inputs, protect secrets, and never allow AI-generated instructions to bypass explicit authorisation.
