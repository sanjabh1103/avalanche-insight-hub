import { assertEquals, assertFalse } from "https://deno.land/std@0.224.0/assert/mod.ts";
import {
  buildIngestPayload,
  isValidEventType,
  isValidGeminiEvent,
  isValidLatitude,
  isValidLongitude,
  isValidSeverity,
  sanitizeArticleText,
} from "./daily_enrichment.ts";

Deno.test("sanitizeArticleText removes newlines and trims", () => {
  assertEquals(sanitizeArticleText("  line1\nline2\r\nline3  "), "line1 line2 line3");
  assertEquals(sanitizeArticleText(null), "");
  assertEquals(sanitizeArticleText(undefined), "");
});

Deno.test("isValidLatitude accepts only finite numbers in [-90, 90]", () => {
  assertEquals(isValidLatitude(45), true);
  assertEquals(isValidLatitude(-90), true);
  assertEquals(isValidLatitude(90), true);
  assertEquals(isValidLatitude(91), false);
  assertEquals(isValidLatitude(-91), false);
  assertEquals(isValidLatitude(NaN), false);
  assertEquals(isValidLatitude("45" as unknown as number), false);
  assertEquals(isValidLatitude(Infinity), false);
});

Deno.test("isValidLongitude accepts only finite numbers in [-180, 180]", () => {
  assertEquals(isValidLongitude(-107), true);
  assertEquals(isValidLongitude(-180), true);
  assertEquals(isValidLongitude(180), true);
  assertEquals(isValidLongitude(181), false);
  assertEquals(isValidLongitude(-181), false);
  assertEquals(isValidLongitude(NaN), false);
  assertEquals(isValidLongitude("-107" as unknown as number), false);
});

Deno.test("isValidSeverity accepts only integers in [1, 5]", () => {
  assertEquals(isValidSeverity(1), true);
  assertEquals(isValidSeverity(5), true);
  assertEquals(isValidSeverity(0), false);
  assertEquals(isValidSeverity(6), false);
  assertEquals(isValidSeverity(3.5), false);
  assertEquals(isValidSeverity("3" as unknown as number), false);
});

Deno.test("isValidEventType accepts only the allowed enum values", () => {
  assertEquals(isValidEventType("slab"), true);
  assertEquals(isValidEventType("unknown"), true);
  assertEquals(isValidEventType("reported"), false);
  assertEquals(isValidEventType(""), false);
  assertEquals(isValidEventType(3 as unknown as string), false);
});

Deno.test("isValidGeminiEvent requires all fields and is_avalanche_event=true", () => {
  assertEquals(
    isValidGeminiEvent({
      is_avalanche_event: true,
      latitude: 46.0,
      longitude: -121.0,
      severity: 3,
      type: "slab",
    }),
    true,
  );
  assertFalse(
    isValidGeminiEvent({
      is_avalanche_event: false,
      latitude: 46.0,
      longitude: -121.0,
      severity: 3,
      type: "slab",
    }),
  );
  assertFalse(
    isValidGeminiEvent({
      is_avalanche_event: true,
      latitude: 91,
      longitude: -121.0,
      severity: 3,
      type: "slab",
    }),
  );
  assertFalse(
    isValidGeminiEvent({
      is_avalanche_event: true,
      latitude: 46.0,
      longitude: -181.0,
      severity: 3,
      type: "slab",
    }),
  );
  assertFalse(
    isValidGeminiEvent({
      is_avalanche_event: true,
      latitude: 46.0,
      longitude: -121.0,
      severity: 6,
      type: "slab",
    }),
  );
  assertFalse(
    isValidGeminiEvent({
      is_avalanche_event: true,
      latitude: 46.0,
      longitude: -121.0,
      severity: 3,
      type: "reported",
    }),
  );
});

Deno.test("buildIngestPayload quarantines machine-extracted events", () => {
  const payload = buildIngestPayload(
    {
      is_avalanche_event: true,
      latitude: 46.0,
      longitude: -121.0,
      severity: 3,
      type: "slab",
      description: "Slide near pass",
    },
    {
      article_id: "a1",
      link: "https://example.com/a1",
      title: "Avalanche near pass",
      source_id: "example-news",
      pubDate: "2026-04-24T00:00:00Z",
    },
    "avalanche",
    "Test Pass",
  );

  assertEquals(payload.lat, 46.0);
  assertEquals(payload.lng, -121.0);
  assertEquals(payload.severity, 3);
  assertEquals(payload.event_type, "slab");
  assertEquals(payload.source, "gemini_news");
  assertEquals(payload.fusion_source, "newsdata_gemini");
  assertEquals(payload.training_eligible, false);
  assertEquals(payload.label_role, "display_only");
  assertEquals(payload.training_eligible_reason, "machine_extracted_news_unreviewed");
  const metadata = payload.metadata as Record<string, unknown>;
  assertEquals(metadata.corroboration_sources, ["gemini_news"]);
  assertEquals(
    metadata.machine_candidate_reason,
    "gemini_extracted_news_unreviewed",
  );
});

Deno.test("buildIngestPayload maps unknown type to reported", () => {
  const payload = buildIngestPayload(
    {
      is_avalanche_event: true,
      latitude: 46.0,
      longitude: -121.0,
      severity: 3,
      type: "unknown",
    },
    { title: "Avalanche" },
    "avalanche",
    "",
  );
  assertEquals(payload.event_type, "unknown");
});

Deno.test("buildIngestPayload clamps severity to [1, 5]", () => {
  const payload = buildIngestPayload(
    {
      is_avalanche_event: true,
      latitude: 46.0,
      longitude: -121.0,
      severity: 8,
      type: "slab",
    },
    { title: "Avalanche" },
    "avalanche",
    "",
  );
  assertEquals(payload.severity, 5);
});
