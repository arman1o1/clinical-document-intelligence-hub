// Builds the 5-slide summary deck in the structure fixed by the POC brief.
const pptxgen = require("pptxgenjs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const OUT = process.argv[2] || path.join(ROOT, "Arman_Clinical_Document_Intelligence_Hub.pptx");

// Palette: clinical petrol/teal, with the amber + red that the product itself
// uses for "withheld" and "critical". The deck's colours mean what the app's mean.
const INK = "0B3C49", TEAL = "12786E", AMBER = "C26401", RED = "B3261E",
      MUTED = "5B6B7C", LIGHT = "F4F7F8", WHITE = "FFFFFF", MINT = "E9F5F3",
      SAND = "FDF3E7", PALE = "EDF3F5";

const HEAD = "Cambria", BODY = "Calibri", MONO = "Courier New";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";           // 13.3 x 7.5 -- set BEFORE adding slides
pres.author = "Arman";
pres.title = "Clinical Document Intelligence Hub";

const card = (s, x, y, w, h, fill) =>
  s.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, fill: { color: fill }, rectRadius: 0.09,
    line: { color: fill, width: 0 },
  });

const title = (s, text, sub) => {
  s.addText(text, {
    x: 0.55, y: 0.34, w: 12.2, h: 0.62, fontFace: HEAD, fontSize: 30,
    bold: true, color: INK, margin: 0,
  });
  if (sub) s.addText(sub, {
    x: 0.55, y: 0.99, w: 12.2, h: 0.34, fontFace: BODY, fontSize: 13.5,
    color: MUTED, italic: true, margin: 0,
  });
};

// ───────────────────────────────── slide 1 ─────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: INK };

  s.addText("Problem Understanding and Objective", {
    x: 0.7, y: 0.62, w: 8.6, h: 0.86, fontFace: HEAD, fontSize: 32,
    bold: true, color: WHITE, margin: 0,
  });
  s.addText("Clinical Document Intelligence Hub   \u00b7   Arman", {
    x: 0.7, y: 1.48, w: 8.6, h: 0.4, fontFace: BODY, fontSize: 15,
    color: "9CC2CB", italic: true, margin: 0,
  });

  s.addText(
    [
      { text: "The brief.  ", options: { bold: true, color: WHITE } },
      { text: "Clinical and administrative staff read intake forms, discharge summaries, lab reports and physician notes by hand to pull out the same handful of facts. It is slow, inconsistent, and error-prone.", options: { color: "D6E4E8" } },
    ],
    { x: 0.7, y: 2.15, w: 7.5, h: 0.95, fontFace: BODY, fontSize: 13.5, margin: 0, lineSpacing: 20 }
  );

  s.addText(
    [
      { text: "Where I think the real problem sits.  ", options: { bold: true, color: WHITE } },
      { text: "Extraction accuracy is not the hard part. Trust is. A structured field with no provenance still forces the reviewer to re-read the document to check it — which is exactly the manual work we claimed to remove. And a field that is confidently wrong is worse than one that is missing.", options: { color: "D6E4E8" } },
    ],
    { x: 0.7, y: 3.2, w: 7.5, h: 1.5, fontFace: BODY, fontSize: 13.5, margin: 0, lineSpacing: 20 }
  );

  s.addText(
    [
      { text: "Objective.  ", options: { bold: true, color: WHITE } },
      { text: "Document → verified structured record → triaged action. Every field carries a confidence and the source span it came from. Anything that cannot be verified is withheld and routed to a human, never displayed as though it were checked.", options: { color: "D6E4E8" } },
    ],
    { x: 0.7, y: 4.85, w: 7.5, h: 1.3, fontFace: BODY, fontSize: 13.5, margin: 0, lineSpacing: 20 }
  );

  const stats = [
    ["18", "fields extracted\nper document"],
    ["4", "document types\nsupported"],
    ["32", "document corpus,\nexact gold labels"],
    ["21", "clinical rules,\nevery flag traceable"],
  ];
  stats.forEach(([n, lbl], i) => {
    const y = 2.15 + i * 1.12;
    s.addShape(pres.ShapeType.roundRect, {
      x: 9.05, y, w: 3.55, h: 0.96, fill: { color: "10495A" }, rectRadius: 0.08,
      line: { color: "10495A", width: 0 },
    });
    s.addText(n, {
      x: 9.25, y: y + 0.06, w: 1.0, h: 0.84, fontFace: HEAD, fontSize: 32,
      bold: true, color: i === 3 ? AMBER : "6FD3C4", align: "center", margin: 0, valign: "middle",
    });
    s.addText(lbl, {
      x: 10.25, y: y + 0.1, w: 2.2, h: 0.76, fontFace: BODY, fontSize: 11,
      color: "C9DDE2", margin: 0, valign: "middle", lineSpacing: 14,
    });
  });

  s.addText("Firstsource Proof of Concept submission", {
    x: 0.7, y: 6.66, w: 8.0, h: 0.34, fontFace: BODY, fontSize: 11.5,
    color: "7FA6B0", margin: 0,
  });

  s.addNotes(
    "The brief asks for extraction from clinical documents. I want to flag the framing I chose up front: " +
    "I treated this as a trust problem rather than an accuracy problem. If a reviewer can't check a field " +
    "without re-reading the source, the automation hasn't removed the work. That single decision drives the " +
    "whole architecture you'll see on the next slide."
  );
}

// ───────────────────────────────── slide 2 ─────────────────────────────────
{
  const s = pres.addSlide();
  title(s, "Solution Architecture and Design Flow",
        "The LLM extracts. Verification gates. Rules decide. Each stage does only what it is actually reliable at.");

  s.addImage({
    path: path.join(ROOT, "assets", "architecture_bare.png"),
    x: 0.72, y: 1.5, w: 11.86, h: 5.69,
  });

  const div = [
    ["Reading prose → fields", "LLM", TEAL],
    ["Trusting a value", "Verification", AMBER],
    ["Escalating a patient", "Rules", RED],
  ];
  div.forEach(([what, who, col], i) => {
    const x = 0.9 + i * 3.9;
    s.addText(
      [
        { text: who + "   ", options: { bold: true, color: col, fontSize: 12 } },
        { text: what, options: { color: MUTED, fontSize: 11 } },
      ],
      { x, y: 7.05, w: 3.8, h: 0.34, fontFace: BODY, margin: 0, align: "center" }
    );
  });

  s.addNotes(
    "Three stages, deliberately separated by what each is reliable at. The LLM does reading comprehension — " +
    "turning prose into fields — because regex cannot do that on a narrative note. The verification layer decides " +
    "whether to believe the result, using checkable signals rather than the model's own opinion of itself. " +
    "And triage is deterministic rules, not the LLM: deciding a potassium of 5.9 needs escalation is clinical " +
    "policy, and policy has to be auditable and versionable. The LLM's failure mode there would be a " +
    "plausible-sounding wrong urgency, which is the one that hurts patients."
  );
}

// ───────────────────────────────── slide 3 ─────────────────────────────────
{
  const s = pres.addSlide();
  title(s, "Implementation Highlights",
        "Confidence is computed from measurable signals, never asked for — verbalised LLM confidence is poorly calibrated.");

  card(s, 0.55, 1.5, 6.3, 2.62, MINT);
  s.addText("Four signals behind every field", {
    x: 0.85, y: 1.68, w: 5.8, h: 0.3, fontFace: BODY, fontSize: 13.5, bold: true, color: INK, margin: 0,
  });
  const sig = [
    ["g", "grounding", "is the evidence quote really in the document?"],
    ["d", "presence", "is the value in the document, independent of its quote?"],
    ["v", "support", "is the value inside the quote it cites?"],
    ["a", "agreement", "do k independent samples return the same value?"],
  ];
  sig.forEach(([k, n, d], i) => {
    const y = 2.06 + i * 0.42;
    s.addText(k, {
      x: 0.88, y, w: 0.3, h: 0.3, fontFace: MONO, fontSize: 13, bold: true, color: TEAL, margin: 0,
    });
    s.addText(
      [
        { text: n + " — ", options: { bold: true, color: INK } },
        { text: d, options: { color: MUTED } },
      ],
      { x: 1.2, y, w: 5.5, h: 0.3, fontFace: BODY, fontSize: 11, margin: 0 }
    );
  });
  s.addText("confidence = 0.30·g + 0.25·d + 0.15·v + 0.30·a", {
    x: 0.88, y: 3.78, w: 5.8, h: 0.28, fontFace: MONO, fontSize: 11.5, bold: true, color: INK, margin: 0,
  });

  card(s, 0.55, 4.28, 6.3, 2.62, SAND);
  s.addText("The gate that does the work", {
    x: 0.85, y: 4.46, w: 5.8, h: 0.3, fontFace: BODY, fontSize: 13.5, bold: true, color: INK, margin: 0,
  });
  s.addText(
    "Named entities — patient, diagnosis, drug, allergen — hard-gate on presence. " +
    "A name that is not in the text is an invention, full stop.\n\n" +
    "Numerics deliberately do not: 37.6 °C correctly extracts as 99.7 °F, and " +
    "“one hundred and twelve” as 112. Neither literal appears in the document. " +
    "Hard-gating those would punish the model for doing the conversion the schema asked for.\n\n" +
    "Lists are filtered per item. A medication list that is 4/5 correct is not 80% safe — " +
    "the phantom fifth entry is the entire risk.",
    { x: 0.85, y: 4.82, w: 5.75, h: 1.9, fontFace: BODY, fontSize: 11, color: "4A4034", margin: 0, lineSpacing: 15 }
  );

  card(s, 7.15, 1.5, 5.6, 2.62, PALE);
  s.addText("Measured, not asserted", {
    x: 7.45, y: 1.68, w: 5.0, h: 0.3, fontFace: BODY, fontSize: 13.5, bold: true, color: INK, margin: 0,
  });
  const met = [
    ["96.2%", "fabrications caught", "under fault injection (50 / 52)", TEAL],
    ["0.0%", "false block rate", "0 of 143 clean fields withheld", TEAL],
    ["14.0%", "baseline silent error", "regex control arm, for comparison", AMBER],
  ];
  met.forEach(([v, l, d, col], i) => {
    const y = 2.08 + i * 0.66;
    s.addText(v, {
      x: 7.45, y, w: 1.35, h: 0.5, fontFace: HEAD, fontSize: 21, bold: true, color: col, margin: 0, valign: "middle",
    });
    s.addText(
      [
        { text: l + "\n", options: { bold: true, color: INK, fontSize: 11 } },
        { text: d, options: { color: MUTED, fontSize: 9.5 } },
      ],
      { x: 8.85, y, w: 3.7, h: 0.5, fontFace: BODY, margin: 0, valign: "middle", lineSpacing: 12 }
    );
  });

  card(s, 7.15, 4.28, 5.6, 2.62, "0E323D");
  s.addText("cdi/verify.py", {
    x: 7.45, y: 4.4, w: 5.0, h: 0.24, fontFace: MONO, fontSize: 9.5, color: "7FB3BE", margin: 0,
  });
  s.addText(
    "g = grounding_score(quote, doc)\n" +
    "d = presence_score(value, doc)\n" +
    "v = support_score(value, quote)\n" +
    "a = agreement_score(samples)\n\n" +
    "fabricated = (g < GATE) or (\n" +
    "    d < GATE and not is_numeric(value))\n\n" +
    "if fabricated:  UNGROUNDED  # withhold\n" +
    "elif dropped:   ABSTAINED   # list invention\n" +
    "elif conf < T:  ABSTAINED   # low confidence\n" +
    "else:           EXTRACTED   # show it",
    { x: 7.45, y: 4.72, w: 5.1, h: 2.0, fontFace: MONO, fontSize: 9.0, color: "CFE6EA", margin: 0, lineSpacing: 11.4 }
  );

  s.addNotes(
    "Two things worth pausing on. First, the model is never asked how confident it is — verbalised confidence " +
    "is badly calibrated, so confidence here is computed from four things I can actually check. Second, the " +
    "gate is asymmetric on purpose. For names and drugs, a value that isn't in the document is fabrication and " +
    "gets blocked outright. For numbers it can't be, because a correct Celsius-to-Fahrenheit conversion produces " +
    "a value that never appears in the text. Getting that wrong was one of my actual bugs — I'll cover it next."
  );
}

// ───────────────────────────────── slide 4 ─────────────────────────────────
{
  const s = pres.addSlide();
  title(s, "Challenges and Learnings",
        "Three of these were my own bugs, found by measurement rather than by reading the code again.");

  const items = [
    ["My corpus was marking its own homework",
     "The first eval gave the regex baseline 99.4%. I had written both the templates and the regexes, so they matched by construction. I added 15 free-prose narrative documents — spelled-out numbers, Celsius, no field labels. The baseline fell to 86% and missed 177 fields. A benchmark you author yourself flatters you until you deliberately attack it.",
     RED],
    ["The grounding gate had a hole",
     "A fabricated patient name passed verification: the quote “Patient Name : <wrong name>” fuzzy-matched the real line because the boilerplate prefix carried the score. Checking the quote is not the same as checking the value. Adding a direct value-in-document test is what actually catches invention.",
     AMBER],
    ["Correct answers were being rejected",
     "Hard-gating numerics on presence punished the model for doing the unit conversion the schema asked for. The fix was to make the gate asymmetric — hard for named entities, soft for numerics — and to match spelled-out numbers and Celsius equivalents explicitly.",
     AMBER],
    ["You cannot measure a hallucination-catcher with an extractor that cannot hallucinate",
     "The regex baseline only copies or fails, so it showed the verification layer doing nothing. Rather than assert the layer works, I injected synthetic hallucinations at a known rate — real quote, subtly wrong value — and measured a 96.2% catch rate with zero false blocks. No API key needed to reproduce it.",
     TEAL],
  ];

  items.forEach(([h, b, col], i) => {
    const y = 1.52 + i * 1.34;
    card(s, 0.55, y, 12.2, 1.2, i % 2 === 0 ? LIGHT : WHITE);
    s.addShape(pres.ShapeType.ellipse, {
      x: 0.78, y: y + 0.36, w: 0.46, h: 0.46, fill: { color: col },
      line: { color: col, width: 0 },
    });
    s.addText(String(i + 1), {
      x: 0.78, y: y + 0.36, w: 0.46, h: 0.46, fontFace: BODY, fontSize: 13,
      bold: true, color: WHITE, align: "center", valign: "middle", margin: 0,
    });
    s.addText(h, {
      x: 1.42, y: y + 0.14, w: 11.1, h: 0.3, fontFace: BODY, fontSize: 13,
      bold: true, color: INK, margin: 0,
    });
    s.addText(b, {
      x: 1.42, y: y + 0.44, w: 11.1, h: 0.7, fontFace: BODY, fontSize: 10.5,
      color: MUTED, margin: 0, lineSpacing: 13.5,
    });
  });

  s.addText(
    [
      { text: "The learning that changed the most:  ", options: { bold: true, color: INK } },
      { text: "picking silent error rate over accuracy as the headline metric reshaped the system more than any model choice did. Once the number you optimise punishes confident wrongness rather than silence, abstention stops being a failure and becomes a feature.", options: { color: MUTED } },
    ],
    { x: 0.55, y: 6.92, w: 12.2, h: 0.42, fontFace: BODY, fontSize: 11, margin: 0, italic: true }
  );

  s.addNotes(
    "I'd rather show the bugs than a clean story. The first one is the one I'd want a reviewer to push on: " +
    "if you generate your own evaluation data, you will flatter yourself, and the only defence is to " +
    "deliberately build the part of the corpus your approach is worst at. The narrative documents exist " +
    "precisely because regex handles them badly and I needed the comparison to be honest."
  );
}

// ───────────────────────────────── slide 5 ─────────────────────────────────
{
  const s = pres.addSlide();
  s.background = { color: INK };

  s.addText("Demo Summary and Next Steps", {
    x: 0.7, y: 0.46, w: 11.9, h: 0.7, fontFace: HEAD, fontSize: 30,
    bold: true, color: WHITE, margin: 0,
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 0.7, y: 1.35, w: 6.0, h: 2.9, fill: { color: "10495A" }, rectRadius: 0.09,
    line: { color: "10495A", width: 0 },
  });
  s.addText("Worked example — one discharge summary", {
    x: 0.98, y: 1.52, w: 5.5, h: 0.3, fontFace: BODY, fontSize: 13,
    bold: true, color: WHITE, margin: 0,
  });
  s.addText(
    "Four traps in the source document, all handled: prior-visit vitals ignored · " +
    "family-history condition excluded · discontinued drug excluded · 10 risk flags raised",
    { x: 0.98, y: 1.86, w: 5.5, h: 0.6, fontFace: BODY, fontSize: 10.5,
      color: "C9DDE2", margin: 0, lineSpacing: 13.5 }
  );
  const findings = [
    ["CRITICAL", "Amoxicillin prescribed against a documented penicillin allergy"],
    ["CRITICAL", "Metformin contraindicated at eGFR 24"],
    ["HIGH", "Discharged with no follow-up, on a high-risk diagnosis"],
  ];
  findings.forEach(([sev, txt], i) => {
    s.addText(
      [
        { text: sev + "  ", options: { bold: true, color: sev === "CRITICAL" ? "FF9E8A" : "FFC978" } },
        { text: txt, options: { color: "C9DDE2" } },
      ],
      { x: 0.98, y: 2.52 + i * 0.42, w: 5.5, h: 0.4, fontFace: BODY, fontSize: 10.5,
        margin: 0, lineSpacing: 13 }
    );
  });
  s.addText("→ Routed: IMMEDIATE CLINICAL REVIEW, urgency 100/100", {
    x: 0.98, y: 3.82, w: 5.5, h: 0.3, fontFace: BODY, fontSize: 10.5,
    bold: true, color: WHITE, margin: 0,
  });

  s.addShape(pres.ShapeType.roundRect, {
    x: 7.0, y: 1.35, w: 5.6, h: 2.9, fill: { color: "10495A" }, rectRadius: 0.09,
    line: { color: "10495A", width: 0 },
  });
  s.addText("What runs today", {
    x: 7.28, y: 1.52, w: 5.0, h: 0.3, fontFace: BODY, fontSize: 13,
    bold: true, color: WHITE, margin: 0,
  });
  s.addText(
    "streamlit run app.py\n" +
    "python -m cdi.summarize <document>\n" +
    "python run_eval.py\n" +
    "python run_eval.py --arm anthropic --k 3",
    { x: 7.28, y: 1.92, w: 5.1, h: 1.0, fontFace: MONO, fontSize: 10,
      color: "9FD8CE", margin: 0, lineSpacing: 15 }
  );
  s.addText(
    [
      { text: "The baseline arm, the full evaluation harness and the UI all run with no API key. ", options: { color: "C9DDE2" } },
      { text: "The fault-injection result is reproducible on any machine in one command.", options: { color: WHITE, bold: true } },
    ],
    { x: 7.28, y: 2.98, w: 5.1, h: 1.1, fontFace: BODY, fontSize: 10.5, margin: 0, lineSpacing: 14 }
  );

  s.addText("If I had another week", {
    x: 0.7, y: 4.52, w: 11.9, h: 0.32, fontFace: BODY, fontSize: 14,
    bold: true, color: WHITE, margin: 0,
  });
  const next = [
    ["Set the threshold, don't pick it", "Fit abstention against an explicit cost ratio for a missed field vs. a wrong one, rather than a hand-chosen 0.70."],
    ["Field-level escalation", "Route only the low-confidence fields to a stronger model instead of re-running the whole document."],
    ["A corpus I didn't write", "Re-measure on a public de-identified set and report the delta honestly — my numbers are on synthetic data."],
    ["Cross-document reconciliation", "Compare an intake form against its discharge summary and flag contradictions between them."],
  ];
  next.forEach(([h, b], i) => {
    const x = 0.7 + (i % 2) * 6.05;
    const y = 4.95 + Math.floor(i / 2) * 1.02;
    s.addText(h, {
      x, y, w: 5.7, h: 0.26, fontFace: BODY, fontSize: 11.5, bold: true, color: "6FD3C4", margin: 0,
    });
    s.addText(b, {
      x, y: y + 0.25, w: 5.7, h: 0.62, fontFace: BODY, fontSize: 10, color: "AFC9D0", margin: 0, lineSpacing: 12.5,
    });
  });

  s.addText("Arman   ·   README, evaluation report and full source in the submitted repository", {
    x: 0.7, y: 7.02, w: 11.9, h: 0.3, fontFace: BODY, fontSize: 10,
    color: "7FA6B0", margin: 0,
  });

  s.addNotes(
    "The worked example on the left is the case for the system: both critical findings are plainly visible in " +
    "the source document, and neither is visible to a human skimming four pages under time pressure. " +
    "On next steps, the one I'd actually do first is the threshold — 0.70 is currently a judgement call, and " +
    "it should be derived from what the organisation decides a missed field costs relative to a wrong one."
  );
}

pres.writeFile({ fileName: OUT }).then(() => console.log("wrote", OUT));
