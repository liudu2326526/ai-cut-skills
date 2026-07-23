# API Contract

This skill is for users who do not have the backend project locally. Treat the AIVideoEditor backend as a remote service.

## Required Connection Inputs

- `baseUrl`: Server root, for example `https://example.com`. Do not include a trailing slash.
- `userId`: Query parameter required by the current API. For real generation this must be an existing backend user ID, and that user must be linked to a WeCom user ID for Seedance/billing.
- `authToken`: Bearer token from a real login. The bundled script can derive `userId` from a JWT `sub`/`user_id` claim, or from the login response.

Do not use `default`, `anonymous`, or a generated local string as `userId` for real submission. Those values can create the task shell but will fail when the worker reaches Seedance/billing.

Recommended environment variables:

- `AIVIDEOEDITOR_API_BASE_URL`
- `AIVIDEOEDITOR_LOGIN_ACCOUNT` and `AIVIDEOEDITOR_LOGIN_PASSWORD` for password login
- `AIVIDEOEDITOR_AUTH_TOKEN`
- `AIVIDEOEDITOR_USER_ID` only when you already know a real backend user ID

## Auth Endpoints

Password login:

```text
POST {baseUrl}/api/v1/auth/password/login
Content-Type: application/json

{"account":"your-account","password":"your-password"}
```

Enterprise WeChat login:

```text
POST {baseUrl}/api/v1/auth/wechat/login
Content-Type: application/json

{"code":"oauth-code"}
```

Consume a one-time browser login token:

```text
POST {baseUrl}/api/v1/auth/browser-login/consume
Content-Type: application/json

{"token":"browser-login-token"}
```

Login responses are wrapped in `data` and contain `data.token` and `data.user.id`. Use `data.user.id` as `userId`.

## Endpoints

Create a task:

```text
POST {baseUrl}/api/v1/pre-roll/tasks?userId={userId}
Content-Type: application/json
Authorization: Bearer {token}   # optional
```

List tasks:

```text
GET {baseUrl}/api/v1/pre-roll/tasks?userId={userId}&limit=50&offset=0
```

Get one task:

```text
GET {baseUrl}/api/v1/pre-roll/tasks/{taskId}?userId={userId}
```

## Minimal Create Body

```json
{
  "scriptText": "每天听歌15分钟，你的余额就会一直涨",
  "visualTemplateId": "decompression",
  "assetStrategy": "generated",
  "ratio": "9:16",
  "duration": 8,
  "voiceCandidates": [
    "zh_male_jieshuoxiaoming_moon_bigtts",
    "zh_female_shuangkuaisisi_moon_bigtts"
  ],
  "generateDubbing": true,
  "generateSubtitle": true,
  "subtitleConfig": {
    "position": "lower_center",
    "fontName": "FZLanTingHeiS-DB1-GB",
    "brandFontName": "Soda Font",
    "brandPrimaryColor": "&H0042FD3B",
    "brandOutlineColor": "&H00000000",
    "brandFontScale": 1.18,
    "fontSize": 46,
    "maxLines": 2,
    "safeMarginRatio": 0.12,
    "bottomMarginRatio": 0.22
  },
  "includeDisclaimerSubtitle": true,
  "disclaimerText": "本视频为广告创意\n具体奖励金额以实际情况为准",
  "disclaimerConfig": {
    "position": "bottom_right",
    "fontSize": 22,
    "fontName": "Microsoft YaHei",
    "primaryColor": "&H00FFFFFF",
    "outlineColor": "&H00000000",
    "backColor": "&H00000000",
    "outline": 1.4,
    "shadow": 0
  },
  "brandOverlay": {
    "logoLightPath": "D:\\path\\to\\汽水logo-白色竖版.png",
    "logoDarkPath": "D:\\path\\to\\汽水logo-黑色竖版.png",
    "logoLumaThreshold": 0.56
  }
}
```

## Status Values

Common values are `pending`, `processing`, `completed`, and `failed`.

Poll until the task reaches `completed` or `failed`. Use exponential or fixed backoff; 5 seconds is a reasonable default.

## Important Response Fields

- `id`: Task ID.
- `status`: Current task status.
- `progress`: 0 to 1.
- `currentStep`: Current workflow step.
- `errorMessage`: Failure reason.
- `resultData.inputs`: Effective inputs saved by the backend.
- `resultData.outputs.finalVideoUrl`: Preferred remote final video URL when available.
- `resultData.outputs.finalVideoPath`: Local server path; not directly downloadable by external users.
- `resultData.outputs.finalVideoObsUrl`: Remote storage URL when available.
- `resultData.outputs.voiceType`: Actual TTS voice used when voice candidates were provided.
- `resultData.outputs.brandOverlaySelection`: Logo variant chosen from background brightness.
- `resultData.outputs.subtitlePath`: Main subtitle artifact.
- `resultData.outputs.composedSubtitlePath`: Subtitle file after disclaimer merge.
- `resultData.outputs.disclaimerSubtitlePath`: Visual-only disclaimer subtitle.
