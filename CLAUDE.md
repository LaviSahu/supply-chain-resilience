# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

## 5. Ground Every Claim in Reality

**Don't invent. Verify the code you're calling actually exists.**

Most broken LLM code comes from confidently using things that aren't there.
- Before calling a function, method, or import - confirm it exists with that exact signature. Don't guess a plausible-looking API.
- Read the file before you edit it. Edit the real contents, not what you assume they contain.
- Don't cite a file path, config key, or env var you haven't confirmed.
- If you can't verify something, say so - "I'm assuming `X` exists" beats a silent guess that breaks at runtime.

The test: Could you point to the line that proves each API you used is real?

## 6. Honest Verification

**Run it. Don't fake green. Report what actually happened.**

Section 4 says loop until verified - this guards the verification itself.
- Actually run the test/build/command. Don't claim "tests pass" from reading the code.
- Never make a check pass by cheating it: don't weaken an assertion, hardcode the expected value, mock away the thing under test, or bury a failure in a silent `try/except`.
- If it fails, show the failure. "3 of 5 pass, here are the 2 failing" is a real status; a premature "done" costs more than the truth.
- A green *new* test on top of a broken *existing* suite is a failure, not a success - run the whole suite and watch for regressions.

The test: If the user re-ran your verification themselves, would they see the same result you reported?

## 7. Know When to Stop

**Stuck? Stop and surface it - don't thrash.**

Flailing makes the diff worse and buries the original problem.
- After ~2-3 failed attempts at the same fix, stop. Report what you tried, what happened, and your best hypothesis.
- Don't stack speculative changes on a change that isn't working - revert to a known-good state first.
- Escalating scope to "fix" a small failure (rewriting a module to kill one bug) is itself the signal to stop and ask.
- "Here's exactly where I'm blocked and why" beats a large, uncertain change.

The test: If you're adding code to work around your *own* previous change, should you undo it instead?

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, clarifying questions come before implementation rather than after mistakes, fewer "it works" claims that don't survive a re-run, and less code written to paper over earlier code.
