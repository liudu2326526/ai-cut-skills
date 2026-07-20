import {defineTransition} from '@vysmo/transitions';

/**
 * WebGL2 page curl with a padded render surface.
 *
 * The curling page occupies an inner rectangle while a transparent plane
 * fills the complete canvas. The padding prevents the deformed mesh from
 * being clipped at the original image bounds.
 */
export const pageCurlTransition = defineTransition({
  name: 'video-motion-effects-page-curl',
  mesh: {subdivisions: [128, 32], instances: 2},
  defaults: {
    tilt: 0.1,
    backColor: [1, 0.995, 0.975] as const,
    backTextureStrength: 0.92,
    pageScale: [1, 1] as const,
    pageOffset: [0, 0] as const,
    shadowStrength: 0.34,
  },
  vertex: `
uniform float uTilt;
uniform vec2 uPageScale;
uniform vec2 uPageOffset;
const float uRadius = 0.5;

out float vLight;
out float vAlpha;
flat out int vInstance;

#define PI 3.14159265359

vec2 pageToCanvas(vec2 pagePosition) {
  return pagePosition * uPageScale + uPageOffset;
}

void main() {
  vInstance = gl_InstanceID;
  vUv = aUv;

  if (gl_InstanceID == 0) {
    gl_Position = vec4(aPosition, 0.99, 1.0);
    vLight = 1.0;
    vAlpha = 1.0;
    return;
  }

  vec2 sweepDir = vec2(cos(uTilt), sin(uTilt));
  vec2 hingeDir = vec2(-sweepDir.y, sweepDir.x);

  float s = dot(aPosition, sweepDir);
  float h = dot(aPosition, hingeDir);
  float maxExtent = abs(sweepDir.x) + abs(sweepDir.y);
  float hingePos = mix(
    maxExtent + uRadius,
    -maxExtent - 2.0 * uRadius,
    uProgress
  );
  float d = s - hingePos;

  if (d <= 0.0) {
    gl_Position = vec4(pageToCanvas(aPosition), 0.0, 1.0);
    vLight = 1.0;
    vAlpha = 1.0;
    return;
  }

  float totalTravel = 2.0 * maxExtent + 3.0 * uRadius;
  float traveled = maxExtent + uRadius - hingePos;
  float rEff = uRadius * (0.18 + 0.82 * sqrt(traveled / totalTravel));
  float theta = d / rEff;
  float newS = hingePos + rEff * sin(theta);
  float newZ = rEff * (cos(theta) - 1.0);

  vec2 newPagePosition = newS * sweepDir + h * hingeDir;
  gl_Position = vec4(pageToCanvas(newPagePosition), newZ, 1.0);

  vec3 normal = vec3(sin(theta) * sweepDir, -cos(theta));
  vec3 lightDir = normalize(vec3(0.35, 0.55, -1.0));
  vLight = clamp(0.5 + 0.55 * dot(normal, lightDir), 0.3, 1.0);
  vAlpha = 1.0 - smoothstep(PI, PI * 2.0, theta);
}
`,
  glsl: `
uniform float uTilt;
uniform vec3 uBackColor;
uniform float uBackTextureStrength;
uniform vec2 uPageScale;
uniform vec2 uPageOffset;
uniform float uShadowStrength;
const float uRadius = 0.5;

in float vLight;
in float vAlpha;
flat in int vInstance;

vec4 transition(vec2 uv) {
  if (vInstance == 0) {
    vec2 canvasPosition = uv * 2.0 - 1.0;
    vec2 pagePosition = (canvasPosition - uPageOffset) / uPageScale;
    vec2 sweepDir = vec2(cos(uTilt), sin(uTilt));
    float maxExtent = abs(sweepDir.x) + abs(sweepDir.y);
    float hingePos = mix(
      maxExtent + uRadius,
      -maxExtent - 2.0 * uRadius,
      uProgress
    );
    float s = dot(pagePosition, sweepDir);
    float d = s - hingePos;
    float totalTravel = 2.0 * maxExtent + 3.0 * uRadius;
    float traveled = max(maxExtent + uRadius - hingePos, 0.0);
    float rEff = uRadius * (0.18 + 0.82 * sqrt(traveled / totalTravel));
    float distPastHinge = max(d, 0.0);
    float shadow = 1.0 - smoothstep(0.0, 3.2 * rEff, distPastHinge);
    float verticalMask = 1.0 - smoothstep(1.0, 1.35, abs(pagePosition.y));
    float horizontalMask = 1.0 - smoothstep(1.0, 1.18, abs(pagePosition.x));
    float envelope = 4.0 * uProgress * (1.0 - uProgress);
    float shadowAlpha =
      shadow * verticalMask * horizontalMask * uShadowStrength * envelope;

    // The destination plane stays transparent. Composite renders reveal the
    // underlying video, while alpha renders preserve only the curl and shadow.
    return vec4(0.0, 0.0, 0.0, shadowAlpha);
  }

  if (vAlpha < 0.01) discard;

  if (gl_FrontFacing) {
    vec4 front = getFromColor(uv);
    return vec4(front.rgb * vLight, front.a * vAlpha);
  }

  // Sampling the original UVs on reverse-facing triangles naturally shows
  // the source image mirrored on the back of the physical page.
  vec4 backTexture = getFromColor(uv);
  vec3 printedBack = mix(
    uBackColor,
    backTexture.rgb,
    uBackTextureStrength
  );
  float backLight = 0.965 + 0.035 * vLight;
  return vec4(printedBack * backLight, backTexture.a);
}
`,
});
