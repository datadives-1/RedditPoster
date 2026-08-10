# Daily Domain Reddit Poster (GitHub Actions + AWS Bedrock)

Posts up to 5x/day, at pseudo-randomized times, to a rotating list of
subreddits. Content is generated with an Amazon Nova model via AWS Bedrock.
No hosting provider, no external database — GitHub Actions runs it, and the
repo itself stores post history for deduplication (and tracks which "angle"
each post used, so the same style — question / hot-take / story / client-
project pitch / etc. — doesn't repeat back-to-back either).

**Important (2026):** Reddit now gates all new API access behind the
Responsible Builder Policy — you can no longer self-register an app at
`reddit.com/prefs/apps`, and personal auto-posting bots are almost never
approved. So this repo ships **two modes**:

- **`draft.py` — semi-automatic (recommended, works today, no API approval).**
  Generates the post, notifies you on Telegram with a ready-to-post link, and
  opens a prefilled Reddit submit tab — you review and click Post.
- **`main.py` — fully automatic (API mode).** Uses PRAW + a refresh token.
  Works only if you have API credentials (pre-Nov-2025 app, or an approval).

**Note:** Bedrock still requires AWS credentials (`AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY`) — these are functionally an API key, just AWS's
version. There's no way to call any LLM, including Nova, without some
credential. What this setup avoids is a server/hosting bill, not credentials
entirely.

## 0. Quick start (semi-automatic mode — no Reddit API needed)

1. Set the LLM provider — **simplest is Google Gemini (free)**: get an API key
   at aistudio.google.com → `LLM_PROVIDER=gemini`, `LLM_API_KEY=<key>`,
   `LLM_MODEL=gemini-flash-latest`. Or use any OpenAI-compatible endpoint
   (`LLM_PROVIDER=openai`, `LLM_API_KEY`, optional `LLM_API_URL`, `LLM_MODEL`),
   or AWS Bedrock (`LLM_PROVIDER=bedrock`, `AWS_*` + `BEDROCK_MODEL_ID`).
2. Set `SUBREDDITS` and `DOMAIN_DESCRIPTION`.
3. (Optional) Create a Telegram bot via @BotFather → get `TELEGRAM_BOT_TOKEN`
   and your `TELEGRAM_CHAT_ID` → set them as env vars.
4. Run:

   ```
   python draft.py            # generates 1 post, notifies Telegram, opens the submit tab
   python draft.py --count 5  # 5 unique drafts in a row
   ```

   You review each draft and click **Post** in the opened tab. Each draft is
   recorded in `history.json`, so nothing repeats across days even between
   modes.

5. For 5 posts/day, schedule it, e.g. on Windows:

   ```
   schtasks /Create /TN "RedditDraft1" /TR "python C:\path\to\draft.py --no-open" /SC DAILY /ST 08:45
   schtasks /Create /TN "RedditDraft2" /TR "python C:\path\to\draft.py --no-open" /SC DAILY /ST 11:50
   schtasks /Create /TN "RedditDraft3" /TR "python C:\path\to\draft.py --no-open" /SC DAILY /ST 15:30
   schtasks /Create /TN "RedditDraft4" /TR "python C:\path\to\draft.py --no-open" /SC DAILY /ST 19:45
   schtasks /Create /TN "RedditDraft5" /TR "python C:\path\to\draft.py --no-open" /SC DAILY /ST 23:00
   ```

   (Note: the browser can't auto-open from a scheduled task; use `--no-open`
   and rely on the Telegram link, or keep the `--count 5` morning run manual.)

## 1. Reddit API access — one-time OAuth setup (no password stored)

1. Go to https://www.reddit.com/prefs/apps → "create another app" → choose
   **web app** (not "script" — that type requires a stored password).
   Set the redirect URI to exactly `http://localhost:8080`.
2. Note the client ID (under the app name) and client secret.
3. As of Reddit's Responsible Builder Policy (late 2025), new API access
   requires approval — apply and wait for confirmation before your first run.
4. On your own machine (not in CI):
   ```
   pip install praw
   export REDDIT_CLIENT_ID=<your client id>
   export REDDIT_CLIENT_SECRET=<your client secret>
   python get_refresh_token.py
   ```
5. It prints a URL — open it in your browser, log in as the bot account,
   click **Allow**. The script catches the redirect and prints a
   `refresh_token`. Save that as the `REDDIT_REFRESH_TOKEN` secret in step 4
   below. You only ever do this once — the token doesn't expire unless you
   revoke access or it goes unused for a year.

Your Reddit password is never entered into any script, env var, or secret
after this point — only the client ID/secret + refresh token are used.

## 2. AWS Bedrock access

1. In the AWS Console → Bedrock → **Model access** → request access to
   Amazon Nova (Micro/Lite/Pro). Approval is usually instant.
2. Create an IAM user with only `bedrock:InvokeModel` / `bedrock:Converse`
   permission (don't reuse broad admin keys), and generate an access key pair.
3. Note: Bedrock is pay-per-token, not free — but Nova Micro/Lite are very
   cheap; 2 short posts/day costs a small fraction of a cent typically. Check
   current pricing at https://aws.amazon.com/bedrock/pricing/ since this
   changes over time.

## 3. Push this folder to a new GitHub repo

```
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

Repo can be private — the workflow still runs fine, but it counts against
your 2,000 free Actions minutes/month, and Actions bills by **wall-clock job
time, not CPU time**. Every minute of jitter sleep is a billed minute, so the
default `MAX_JITTER_MINUTES` is 15 (average ~7.5 min sleep × 3 runs/day × 30
days ≈ 680 min/month, comfortably inside the free tier). If you raise it,
do the math before you hit the 2,000-minute cap.

## 4. Add repo Secrets

GitHub repo → Settings → Secrets and variables → Actions → New repository secret.
Add each of:

- `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_REFRESH_TOKEN`, `REDDIT_USER_AGENT`
- `SUBREDDITS` (comma-separated, e.g. `webdev,design,FrontendDev`)
- `DOMAIN_DESCRIPTION`
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`
- `BEDROCK_MODEL_ID` (e.g. `amazon.nova-lite-v1:0`)
- `SUBREDDIT_FLAIRS` (optional) — comma-separated `subreddit:flair` pairs for
  subs that require a specific link flair, e.g. `webdev:Question,design:Critique`.
  If unset, the bot posts without a flair and auto-picks the first available
  one only if the sub rejects the post for missing flair.
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (optional) — post/draft notifications
  (also used by `draft.py` locally; there they're regular env vars, not secrets)

## 5. Test it

Actions tab → "Daily Reddit Poster" → **Run workflow** (this uses the
`workflow_dispatch` trigger) to fire a test run immediately instead of
waiting for the schedule.

## 6. It's live

The five `cron` lines in `.github/workflows/post.yml` control roughly when
each day's posts fire; edit them to match your preferred windows (they're in
UTC — comments show the IST equivalent). Each run adds its own random jitter
on top before actually posting.

## Why there's no link in the post body

Reddit's spam filters and most mods flag self-promotional links from
new/automated-looking accounts almost immediately — this is the single
biggest reason accounts get banned or shadowbanned, regardless of how the
content was generated. Posting without a link and building some genuine
karma/history first is what keeps the account alive long enough to be
useful. Put your portfolio in your Reddit profile's "About" section instead
— much lower risk than in every post.

## Realistic expectations

- New/low-karma accounts get caught by spam filters more often no matter how
  good the content is — consider warming the account up with real comments
  and upvotes for a week or two before relying on this.
- Some subreddits ban all bots/automation outright, even well-disguised
  ones — check each subreddit's rules before adding it to `SUBREDDITS`.
- Reddit can detect account age, posting regularity, and engagement patterns
  well beyond what this script randomizes. This reduces risk; it doesn't
  eliminate it.

## Concrete steps that actually reduce ban risk (do these, not just code changes)

1. **List at least 6-8 subreddits**, not 3-4. At 3 posts/day, a short
   `SUBREDDITS` list means the same sub gets hit every day or two regardless
   of the anti-repeat logic — that pattern alone gets noticed by mods.
2. **Reply to comments on your own posts.** A bot that posts and never
   engages back is the clearest tell. This script doesn't automate replies
   on purpose — that part should be you.
3. **Occasionally comment on other people's posts** in the same subreddits,
   unrelated to your own posts. Real accounts have a comment history, not
   just a submission history.
4. **Watch your account's status** after each post for the first couple of
   weeks — if a post isn't showing up in the subreddit's "new" feed when
   viewed logged-out, that's a shadowban signal, not just bad luck.
5. **Read each subreddit's rules before adding it.** Many relevant dev/design
   subs explicitly restrict frequency of self-posts per user per week —
   3x/day to the same set of subs will violate those even with unique
   content.
