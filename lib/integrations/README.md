# Integrations

Place external API and sponsor-service integrations here.

Each integration should:
- keep secrets server-side
- expose a small typed interface
- handle upstream errors explicitly
- avoid leaking raw provider responses into UI components
- keep provider-specific logic isolated

Example structure:

lib/integrations/
  sponsor/
    client.ts
    types.ts
  ai/
    client.ts
    types.ts