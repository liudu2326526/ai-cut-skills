# Troubleshooting

Use this guide for remote API users.

## Cannot Connect

Check:

- `baseUrl` is the server root, not a local project path.
- The API path is `{baseUrl}/api/v1/pre-roll/tasks`.
- Network, VPN, firewall, and HTTPS certificate settings.
- `Authorization: Bearer ...` is present if the deployment requires it.

## 400 Response

The body is usually missing one of:

- `scriptText`
- `promptText`
- `copyTemplateType`

For simple use, send `scriptText`.

## Auth Or Billing User Failure

If the task fails near `submit_seedance_video` with messages such as:

- `current user is not linked to wecom user id`
- `BillingUserNotLinked`
- `userId="default"` or another placeholder user

Then the request used a non-real user. Real Seedance generation needs a backend user record with `wx_userid`.

Fix it by using one of these paths:

- Log in with `--login-account` and `--login-password`; the script will use the returned `user.id`.
- Pass a valid `--auth-token`; the script can derive `userId` from a JWT `sub` or `user_id` claim.
- Ask the backend owner to provision or link the account to a WeCom user ID.

Do not retry real generation with `default`, `anonymous`, or `pre-roll-anon-*`; it will fail again at billing/Seedance.

## Task Stays Pending

The backend may not have a worker running. Ask the backend owner to check the `pre_roll` Celery queue and Redis.

## Task Fails During Generated Video

The server may be missing Seedance/Ark credentials or the external provider rejected the prompt. Try `assetStrategy: scraped` with explicit `scrapedVideoUrl` or `scrapedVideoUrls`, or ask the backend owner to inspect provider logs.

## Task Fails During Generated Image

The server may be missing image provider credentials. Try `assetStrategy: generated` or `scraped`, or ask the backend owner to inspect image provider settings.

## Task Completes But No Downloadable URL

Look for:

- `resultData.outputs.finalVideoUrl`
- `resultData.outputs.finalVideoObsUrl`
- `resultData.outputs.obsUrl`
- `resultData.outputs.finalVideoPath`

If only `finalVideoPath` exists, the backend produced a local server file but did not expose/upload it. External users need a remote URL from the backend.

## Subtitle Problems

If subtitles are missing, confirm `generateSubtitle: true`.

If subtitles overflow or touch the edge, adjust:

- `subtitleConfig.fontSize`
- `subtitleConfig.maxLines`
- `subtitleConfig.safeMarginRatio`
- `subtitleConfig.bottomMarginRatio`

Use `lower_center` for the main subtitle and `bottom_right` for the small disclaimer.

If subtitles appear before the voice starts, standalone mode now detects leading silence automatically with `subtitleAudioSync: "auto"`. Check the output JSON under `steps.subtitleSync.offsetSeconds`.

If subtitles still feel early or late for a specific voice, set `subtitleOffsetSeconds`, for example `0.25` to delay subtitles by 0.25 seconds or `-0.15` to show them earlier.
