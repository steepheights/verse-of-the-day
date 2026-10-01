# Verse of the day

Posts one Bible verse to Instagram every morning at 07:30 Perth time, as a clean text card with the verse in the caption. Runs on GitHub Actions, so it posts even when your PC is off.

Personal project, not Allevic work.

## Why the Berean Standard Bible and not the NIV

The plan started with the NIV. It changed because you want to be able to monetise the account:

- The NIV is copyrighted by Biblica. API.Bible offers it for non-commercial use only, and a monetised account would need a written commercial licence from Biblica. There is no legal way to download the full NIV and keep it here.
- The Berean Standard Bible (BSB) is modern English, reads much like the NIV, and was placed in the public domain on 30 April 2023. Its publisher says "Licensing is not required for any use", commercial use included.

So the full BSB text sits in `data/bsb.txt`, a copy of `raw/2026-10-01-berean-standard-bible.txt`, and the script reads verses straight from that file. There is no Bible API, no key and no monthly fee.

## How it works

| File | Purpose |
|---|---|
| `verses.csv` | The curated list: reference, theme, and (for some Psalms) the heading to strip. Day 1 is `start_date` in `config.json`; after the last row it starts again. |
| `data/bsb.txt` | The full BSB, one verse per line. |
| `post.py` | `check` confirms every reference exists. `render` draws `posts/<date>.jpg` and writes the caption. `publish` posts it through the Instagram API with Facebook Login, the same business portfolio Meta Business Suite uses. |
| `config.json` | Handle, colours, fonts, hashtags, attribution line, start date. |
| `.github/workflows/daily.yml` | The daily run. |

Each day the workflow renders the card, commits it to `posts/` so Instagram can fetch it from a public link, publishes it, and records a `posts/<date>.posted` marker so a re-run never double-posts.

## Setup (you do these; Claude can't create accounts or handle credentials)

This uses the Meta Business Suite route: the Instagram account is linked to a Facebook Page in a business portfolio, and the script posts with a **system user** token that does not expire.

### 1. Instagram account and Facebook Page
1. Create the Instagram account in the app and choose the handle.
2. Settings → Account type and tools → switch to a **Professional account** (Creator or Business).
3. Create a Facebook Page for the account (it can be minimal).
4. In Meta Business Suite (business.facebook.com), create or pick a business portfolio, then add the Page and the Instagram account to it, and link the Instagram account to the Page.
5. Put the handle in `config.json` under `"handle"` (or tell Claude the handle).

### 2. Meta developer app
1. Go to developers.facebook.com and create an app of type **Business**, connected to the same business portfolio.
2. Add the **Instagram** product and choose **API setup with Facebook login**.
3. Posting to accounts your own business owns should work with the app in development mode, without app review.

### 3. System user token (never expires)
1. In Meta Business Suite: Settings (Business settings) → Users → **System users** → Add. Choose an **Admin** system user and name it, for example `verse-bot`.
2. **Assign assets** to it: the Facebook Page and the Instagram account, with full control, and the app from step 2.
3. Click **Generate new token**, choose the app, set expiry to **Never**, and tick these permissions: `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`, `business_management`.
4. Copy the token straight into GitHub in the next step. Don't save it in this folder or send it in chat.

### 4. GitHub
1. Create a **public** repository (the images must be publicly reachable for Instagram to fetch them).
2. Upload everything in this `verse-of-the-day` folder to it, keeping the folder structure (the `.github` folder included).
3. In the repo: Settings → Secrets and variables → Actions → New repository secret:
   - `IG_ACCESS_TOKEN`: the system user token from step 3.
   - `IG_USER_ID`: the Instagram account's ID. If you don't know it, leave it out for the first publish run: it will fail and the log will list the ID next to your handle. Add it as the secret and run again.

### 5. Test run
1. Repo → Actions → **Daily verse** → Run workflow. Untick "Publish" for a dry run, then look at the image it commits in `posts/`.
2. Run it again with "Publish" ticked to post for real.
3. From then on it runs every day at 07:30. GitHub's scheduler can run a few minutes late at busy times. Each post also shows up in Meta Business Suite.

## Monetising later

- The BSB text puts no limits on commercial use. Attribution is optional; the caption credits it anyway.
- Instagram's own money features (subscriptions, gifts, branded content, affiliate links) each have eligibility rules set by Meta, such as follower count and professional account type. Check them once the account has grown.
- Paid partnerships must be labelled with Instagram's paid-partnership tag.

## Changing things

- **Different verses:** edit `verses.csv`. Use the BSB's book names (`Psalm`, `Song of Solomon`, `1 John`) and ranges within one chapter (`Romans 8:38-39`). Run `python post.py check`, or let the workflow check it.
- **Look:** colours and fonts are in `config.json`.
- **Time:** change the `cron` line in the workflow. It is in UTC; Perth is UTC+8.
