import assert from "node:assert/strict";
import { test } from "node:test";
import { buildShortlistCsv, safeCsvText } from "../src/shortlistCsv.ts";
import { buildSubmissionCsv } from "../src/csv.ts";
import { candidates } from "./fixtures.ts";

test("shortlist CSV quotes commas, quotes and line breaks without changing the note", () => {
  assert.equal(buildShortlistCsv([{ candidate_id: "F-1", title: 'Engineer, "Platform"', original_rank: 7,
    notes: 'Ask, "why"\nNext line\r\nLast line' }]),
  'candidate_id,title,original_rank,notes\r\n"F-1","Engineer, ""Platform""",7,"Ask, ""why""\nNext line\r\nLast line"');
  assert.equal(buildShortlistCsv([]), "candidate_id,title,original_rank,notes");
});

test("user text formula prefixes are neutralized, including after whitespace or control characters", () => {
  for (const value of ["=1+1", "+SUM(A1)", "-2+3", "@SUM(A1)", "  =1+1", "\t=1+1", "\r=1", "\n@NOW()", "\tPlain text"]) {
    assert.equal(safeCsvText(value), '"\'' + value + '"');
  }
  assert.equal(safeCsvText("Discuss = 1"), '"Discuss = 1"');
  const csv = buildShortlistCsv([{ candidate_id: "=ID()", title: "+Title", original_rank: 1, notes: "@Note" }]);
  assert.equal(csv, 'candidate_id,title,original_rank,notes\r\n"\'=ID()","\'+Title",1,"\'@Note"');
});

test("submission export keeps its existing header, formatting, reasoning substitutions and full input", () => {
  const rows = [{ ...candidates[0], display_score: .99, reasoning: 'Owned, "Java"' },
    { ...candidates[1], display_score: .2, reasoning: "original" }];
  assert.equal(buildSubmissionCsv(rows), 'candidate_id,rank,score,reasoning\nF-1,1,0.99,"Owned; \'Java\'"\nF-2,4,0.2,"original"');
  assert.equal(buildSubmissionCsv([]), "candidate_id,rank,score,reasoning");
});
