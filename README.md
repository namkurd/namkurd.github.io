# Rumble Central (the DTF Club hub)

Rumble Central is the home-screen app for the DTF Club fantasy football league, served at https://namkurd.github.io/.

It ties together the league's tools. Each tool lives in its own repo and is served on the same origin at `/<Repo>/`:

- Rumble Central
- Lifetime
- Trade Network
- FAB & Sit/Start
- Record Book
- Head-to-Head
- Auction Archive
- Rulebook

The plan and the contracts (`tools.json`, `summary.json`, `shell/nav.js`) are in **[docs/PLAN.md](docs/PLAN.md)**.

Icons: `shell/icons/` holds the Rumble Central split-flap "R". Regenerate them with `tools/icons/` (see the header of `mklogo.py`).

## Home data

The Home screen reads three small files at the root. Nothing in the tool repos has to change for them.

| File | Built by | What it holds |
|---|---|---|
| `league.json` | `tools/build_feed.py` (hourly, `.github/workflows/feed.yml`) | Season, week and key dates (trade deadline, playoffs, championship) taken from the Sleeper league settings. `league_id` here is the one place to change at season rollover. |
| `feed.json` | `tools/build_feed.py` | Top 3 matchups, trades, waiver claims and free-agent pickups of the season, each linking into its tool. Reads the tools' public data (`rumbles_history.json`, `SleeperTradeNodes/data.json`, `FAB-Management/data.json`). |
| `slack.json` | `tools/build_slack.py` (daily, `.github/workflows/slack.yml`) | The three busiest conversations in the league Slack this week: a short neutral title, channel, message count and a link into Slack. |

How the picks are made: **matchups** use Rumble Central's own best-matchups ranking (closeness, lead changes, late comebacks, one big swing, and a 1.25x boost for head-to-heads). That ranking lives in the page and rests on its win-probability model, so `tools/build_matchups.py` opens the real page in a headless browser, reads each finished week's scores (the page publishes them as `data-it`, `data-flips` and so on on every Best card) into `data/matchups.json`, and `build_feed.py` takes the season's top 3. Finished weeks never change, so only new weeks are scraped. **Trades** by total value moved; **waivers / free agents** by points above replacement (PAR) while started.

### Turning on the Slack topics

The seeded `slack.json` is a one-time snapshot. For it to update by itself:

1. Create a Slack app (api.slack.com/apps) in the DTF Club workspace with the bot scopes `channels:read` and `channels:history` (add `channels:join` only if you want it to join public channels by itself, and set `autoJoin` in `tools/slack_config.json`). Install it and copy the **Bot User OAuth Token**.
2. Add it to this repo as the Actions secret `SLACK_BOT_TOKEN` (Settings, Secrets and variables, Actions). Invite the bot to the channels it should read, or enable `autoJoin`.
3. Optional: add `ANTHROPIC_API_KEY` as a secret so a Claude model writes the topic titles. Without it the title is the first message, cut short. With it, the conversation text is sent to Anthropic to write the title.

Only **public** channels are read. This repo and site are public, so what ends up in `slack.json` is public: a short title, the channel name, counts and a link (the link needs a Slack login). Edit `tools/slack_config.json` to exclude channels. Delete `slack.json`'s topics (or the file) to hide the Slack tab.

### Who are you?

`managers.json` lists the people in this season's league (name as every tool spells it, roster, Sleeper user); `tools/build_feed.py` refreshes it with the feed. The picker (Home chip, or League menu > "You") stores your choice on your phone as `dtf.me` = `{"id": "ben", "name": "Ben"}`. Every tool on this site can read it: `DTF.me()` (id), `DTF.meName()`, `DTF.setMe(...)`, and a `dtf:me` event when it changes. Rumble Central uses it for its own Me tab and writes it back when you pick there, so you are asked once. On Home it marks the feed rows about you and shows your standing. Add `aliases` in `managers.json` for nicknames or former members.
