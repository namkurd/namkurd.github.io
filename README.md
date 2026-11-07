# Rumble Hub (the DTF Club hub)

Rumble Hub is the home-screen app for the DTF Club fantasy football league, served at https://namkurd.github.io/.

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

Icons: `shell/icons/` holds the split-flap "R" from the Rumble Central tool. Regenerate them with `tools/icons/` (see the header of `mklogo.py`).

## Home data

The Home screen reads three small files at the root. Nothing in the tool repos has to change for them.

| File | Built by | What it holds |
|---|---|---|
| `league.json` | `tools/build_feed.py` (hourly, `.github/workflows/feed.yml`) | Season, week and key dates (trade deadline, playoffs, championship) taken from the Sleeper league settings. `league_id` here is the one place to change at season rollover. |
| `feed.json` | `tools/build_feed.py` | Top 3 matchups, trades, waiver claims and free-agent pickups of the season, each linking into its tool. Reads the tools' public data (`rumbles_history.json`, `SleeperTradeNodes/data.json`, `FAB-Management/data.json`). |
| `slack.json` | `tools/build_slack.py` (every 8 hours, `.github/workflows/slack.yml`) | The three busiest conversations in the league Slack this week: a short neutral title, channel, message count and a link into Slack. |
| `champions/cards.json` | `tools/build_champion_cards.py --src /home/user` (run by hand) | Each champion's and sacko's finals-week Rumble card (team, logo, regular-season record, starters) shown in the expanded Champions & Sackos rows. Re-run after each season's playoffs or when a new row is added to `champions/data.json`. |

How the picks are made: **matchups** use Rumble Central's own best-matchups ranking (closeness, lead changes, late comebacks, one big swing, and a 1.25x boost for head-to-heads). That ranking lives in the page and rests on its win-probability model, so `tools/build_matchups.py` opens the real page in a headless browser, reads each finished week's scores (the page publishes them as `data-it`, `data-flips` and so on on every Best card) into `data/matchups.json`, and `build_feed.py` takes the season's top 3. Finished weeks never change, so only new weeks are scraped. **Trades** ranked by total value moved, with the winner taken from the Trade Network's own **Net** column (lineup gain for one side minus the other's; no lineup data yet shows Even); **waivers / free agents** by points above replacement (PAR) while started.

### Turning on the Slack topics

The seeded `slack.json` is a one-time snapshot. For it to update by itself:

1. Create a Slack app (api.slack.com/apps) in the DTF Club workspace with the bot scopes `channels:read` and `channels:history` (add `channels:join` only if you want it to join public channels by itself, and set `autoJoin` in `tools/slack_config.json`). Install it and copy the **Bot User OAuth Token**.
2. Add it to this repo as the Actions secret `SLACK_BOT_TOKEN` (Settings, Secrets and variables, Actions). Invite the bot to the channels it should read, or enable `autoJoin`.
3. Summaries need no setup: the job asks GitHub Models (with its own token) for a one-sentence summary of each conversation. Optionally add `ANTHROPIC_API_KEY` as a secret and a Claude model writes them instead. Either way the conversation text is sent to that service to write the sentence.

Each topic is a one-sentence summary of the conversation. The job writes it with Claude if `ANTHROPIC_API_KEY` is set (model `claude-haiku-5-5`, override with `SLACK_TOPIC_MODEL`), otherwise with GitHub Models (`openai/gpt-4.1-mini`, override with `GITHUB_MODELS_MODEL`; needs the workflow's `models: read` permission). If neither works, a conversation keeps whatever summary it already has, and a new one falls back to its first message.

Only **public** channels are read. This repo and site are public, so what ends up in `slack.json` is public: a short title, the channel name, counts and a link (the link needs a Slack login). Edit `tools/slack_config.json` to exclude channels. Delete `slack.json`'s topics (or the file) to hide the Slack tab.

### Who are you?

`managers.json` lists the people in this season's league (name as every tool spells it, roster, Sleeper user); `tools/build_feed.py` refreshes it with the feed. The picker (Home chip, or League menu > "You") stores your choice on your phone as `dtf.me` = `{"id": "ben", "name": "Ben"}`. Every tool on this site can read it: `DTF.me()` (id), `DTF.meName()`, `DTF.setMe(...)`, and a `dtf:me` event when it changes. Rumble Central uses it for its own Me tab and writes it back when you pick there, so you are asked once. On Home it marks the feed rows about you and shows your standing. Add `aliases` in `managers.json` for nicknames or former members.

## Champions & Sackos (`/champions/`)

`champions/data.json` has one entry per season (champion + team name, sacko). Add the new season at the top each year. Photos go in `champions/photos/` and are listed under `champion.photos` / `sacko.photos` as `{"src": "/champions/photos/2025-champion.jpg", "caption": "..."}`; the first one is the big photo, and a year with photos expands to show them all. The Home screen shows a wide tile with the latest champion and sacko. Sacko years before 2013 are not recorded.

## IR eligibility on Home

The hourly feed job checks out `namkurd/FAB-Management`, runs its `ir_check.py --json` (Sleeper API only) and `tools/build_feed.py` stores the result as `ir` in `feed.json`. Home shows a one-line status (green = nobody on IR illegally; red = on IR but not eligible; amber = hurt but can't go on IR until next week); tap it to expand the names. Outside the regular season the check can't run and the last status is kept.

## Credits

The Rulebook logo is the "whistle" icon from [Material Design Icons](https://pictogrammers.com/library/mdi/) (Pictogrammers, Apache License 2.0), recoloured.
