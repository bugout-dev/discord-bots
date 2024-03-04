# leaderboard bot

Run discord bot, set `LEADERBOARD_DISCORD_BOT_DEBUG=true` environment variable if debug log required:

```bash
leaderboard discord run
```

## CLI

List Discord server configurations from Brood resources:

```bash
leaderboard configs list
```

Example of server configuration:

```json
{
	"resources": [
		{
			"id": "f817ffd7-a535-4645-86f0-2e129b758bed",
			"application_id": "190e3bd3-b345-4173-a2cc-2d8ccf44e228",
			"resource_data": {
				"type": "discord-bot-leaderboard-config",
				"commands": [
					{
						"origin": "rank",
						"renamed": "status"
					}
				],
				"leaderboards": [
					{
						"short_name": "Breaking Ground",
						"channel_ids": [751874414798231336],
						"leaderboard_id": "80636bfe-4541-4e7c-a4ad-eea8f4a39aa3",
						"leaderboard_info": {
							"id": "80636bfe-4541-4e7c-a4ad-eea8f4a39aa3",
							"title": "Mission 4 - Breaking Ground",
							"description": "Mine at least 10k tonnes of any raw materials.",
							"users_count": 4,
							"last_updated_at": "2024-02-22T10:08:23.751642+00:00"
						}
					}
				],
				"thumbnail_url": "https://s3.amazonaws.com/static.simiotics.com/moonstream/assets/discord-transparent.png",
				"discord_server_id": 751874414798231312,
				"discord_auth_roles": [
					{
						"id": 1202992653213417301,
						"name": "admin"
					}
				]
			},
			"created_at": "2024-02-13T11:35:22.451606+00:00",
			"updated_at": "2024-03-04T11:23:18.071603+00:00"
		}
	]
}
```

Example of user identity:

```json
{
	"resources": [
		{
			"id": "194baa90-478c-482a-8e57-e56d148b76b3",
			"application_id": "190e3bd3-b345-4173-a2cc-2d8ccf44e228",
			"resource_data": {
				"name": "First crew",
				"type": "discord-bot-leaderboard-user-identity",
				"identifier": "1",
				"discord_user_id": 214576833186238191
			},
			"created_at": "2024-02-19T09:15:26.134556+00:00",
			"updated_at": "2024-02-19T09:15:26.134556+00:00"
		}
	]
}
```

Set Discord server ID environment variable to work with:

```bash
export MOONSTREAM_DISCORD_SERVER_ID=751874414798231312
```

Specify thumbnail url for Discord server:

```bash
leaderboard configs set-thumbnail-url --discord-server-id "${MOONSTREAM_DISCORD_SERVER_ID}" --thumbnail-url "https://s3.amazonaws.com/static.simiotics.com/moonstream/assets/discord-transparent.png"
```

Modify default command name for specified server:

```bash
leaderboard configs set-commands --discord-server-id "${MOONSTREAM_DISCORD_SERVER_ID}" --commands '[{"origin": "rank","renamed": "status"}]'
```
